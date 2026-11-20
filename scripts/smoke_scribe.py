#!/usr/bin/env python3
"""Opt-in live smoke test for ElevenLabs Scribe v3 Live. Needs ELEVENLABS_API_KEY.

Streams consented 16 kHz mono PCM at live pace and prints SCRUBBED metadata only:
message types, field names/types, word counts, text lengths, timing numbers and
the observed timestamp basis. Never prints the key, transcript text or audio.

Usage (from repo root):
  .venv/bin/python scripts/smoke_scribe.py --wav /abs/path/consented-16k-mono.wav
  some_pcm_source | .venv/bin/python scripts/smoke_scribe.py --stdin-pcm
Options: --seconds 15  --lead-silence 3.0  --streams 2  --vad-silence 0.65

Protocol: LEAD seconds of digital silence, then the speech, then ~2 s of silence so
VAD commits. If the first word starts near LEAD and later commits never restart near 0,
timestamps are connection-relative; if later commits restart near 0 they are
segment-relative. Use audio with a pause of >= 1.5 s between two phrases.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLE_RATE = 16000
CHUNK_SECS = 0.1
TAIL_SILENCE_SECS = 2.5
GRACE_SECS = 4.0


def load_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        try:
            from dotenv import dotenv_values

            key = (dotenv_values(ROOT / "backend" / ".env").get("ELEVENLABS_API_KEY") or "").strip()
        except ImportError:
            pass
    return key


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            sys.exit("WAV must be 16000 Hz, mono, 16-bit PCM. Convert first, e.g. "
                     "`ffmpeg -i in.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav`.")
        return w.readframes(w.getnframes())


def shape(value):
    """Scrubbed structural description: types and lengths, never string content."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0]), f"x{len(value)}"] if value else []
    if isinstance(value, str):
        return f"str[{len(value)}]"
    return type(value).__name__


async def run_stream(index: int, key: str, pcm: bytes, args) -> dict:
    import websockets

    from backend.app.adapters.scribe import ElevenLabsScribeAdapter

    extra = {"url": args.url} if args.url else {}
    adapter = ElevenLabsScribeAdapter(api_key=key, vad_silence_secs=args.vad_silence, **extra)
    url = f"{adapter._url}?{adapter._query()}"
    lead = bytes(int(args.lead_silence * SAMPLE_RATE) * 2)
    tail = bytes(int(TAIL_SILENCE_SECS * SAMPLE_RATE) * 2)
    audio = lead + pcm[: int(args.seconds * SAMPLE_RATE) * 2] + tail
    log: list[dict] = []
    shapes: dict[str, object] = {}
    t0 = time.monotonic()
    sent_samples = 0

    try:
        ws = await websockets.connect(url, additional_headers={"xi-api-key": key}, open_timeout=10)
    except Exception as exc:  # noqa: BLE001
        status = getattr(getattr(exc, "response", None), "status_code", None)
        sys.exit(f"stream {index}: connect failed ({type(exc).__name__}, http status {status}). "
                 "401/403 = bad key or terms not accepted; 402/429 = quota/rate.")

    async def reader():
        try:
            async for raw in ws:
                now = time.monotonic() - t0
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    log.append({"t": now, "type": "<non-json>"})
                    continue
                mtype = msg.get("message_type", "<missing>")
                shapes.setdefault(mtype, shape({k: v for k, v in msg.items() if k != "message_type"}))
                entry = {"t": now, "type": mtype, "audio_sent_s": sent_samples / SAMPLE_RATE}
                if "text" in msg and isinstance(msg["text"], str):
                    entry["text_len"] = len(msg["text"])
                if mtype == "committed_transcript_with_timestamps":
                    words = msg.get("words") or []
                    entry["item_types"] = sorted({str(w.get("type")) for w in words if isinstance(w, dict)})
                    real = [w for w in words if isinstance(w, dict) and w.get("type", "word") == "word"]
                    entry["n_words"] = len(real)
                    entry["starts"] = [w.get("start") for w in real]
                    entry["ends"] = [w.get("end") for w in real]
                    entry["word_text_lens"] = [len(w.get("text", "")) for w in real]
                    entry["language_code"] = msg.get("language_code")
                log.append(entry)
        except Exception:  # noqa: BLE001
            pass

    rtask = asyncio.ensure_future(reader())
    step = int(CHUNK_SECS * SAMPLE_RATE) * 2
    try:
        for off in range(0, len(audio), step):
            chunk = audio[off : off + step]
            await ws.send(json.dumps({
                "message_type": "input_audio_chunk",
                "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                "commit": False,
                "sample_rate": SAMPLE_RATE,
            }))
            sent_samples += len(chunk) // 2
            await asyncio.sleep(CHUNK_SECS)  # live pace
        await asyncio.sleep(GRACE_SECS)
    finally:
        await ws.close()
        rtask.cancel()
    return {"log": log, "shapes": shapes, "lead": args.lead_silence, "audio_s": len(audio) / (2 * SAMPLE_RATE)}


def analyse(result: dict) -> str:
    log, lead = result["log"], result["lead"]
    out = [f"audio sent: {result['audio_s']:.1f}s (lead silence {lead}s)", "message types seen:"]
    counts: dict[str, int] = {}
    for e in log:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    for k, v in counts.items():
        out.append(f"  {k}: {v}   fields: {json.dumps(result['shapes'].get(k))}")
    out.append("ordering (type, arrival s, audio sent s, text_len):")
    for e in log:
        if e["type"] in ("session_started",):
            continue
        out.append(f"  {e['type']:<42} t={e['t']:6.2f} sent={e.get('audio_sent_s', 0):6.2f} len={e.get('text_len', '-')}")
    timed = [e for e in log if e["type"] == "committed_transcript_with_timestamps"]
    commits = [e for e in log if e["type"] == "committed_transcript"]
    out.append(f"commits: {len(commits)}  timed commits: {len(timed)}")
    # delay from committed_transcript to its timed event (FIFO pairing)
    for c, t in zip(commits, timed):
        out.append(f"  commit->timed delay: {(t['t'] - c['t']) * 1000:.0f} ms")
    prev_end = None
    verdicts = []
    for i, t in enumerate(timed):
        starts, ends = [s for s in t["starts"] if isinstance(s, (int, float))], [e for e in t["ends"] if isinstance(e, (int, float))]
        if not starts or not ends:
            out.append(f"  timed[{i}]: no numeric word times (item types {t['item_types']})")
            continue
        out.append(f"  timed[{i}]: {t['n_words']} words, first start {starts[0]:.3f}s, last end {ends[-1]:.3f}s, "
                   f"item types {t['item_types']}, arrived when {t['audio_sent_s']:.2f}s audio sent")
        if ends[-1] > t["audio_sent_s"] + 0.5:
            out.append("    WARNING: word end beyond audio sent so far (unit or clock assumption wrong)")
        if i == 0:
            verdicts.append("connection" if starts[0] >= lead * 0.8 else "segment?")
        elif prev_end is not None:
            verdicts.append("connection" if starts[0] >= prev_end - 0.05 else "segment")
        prev_end = ends[-1]
    if not verdicts:
        basis = "unknown (no timed words observed)"
    elif all(v == "connection" for v in verdicts) and len(timed) >= 2:
        basis = "connection-relative (starts continue past lead silence and never restart)"
    elif "segment" in verdicts:
        basis = "segment-relative (a later commit restarted near 0); origin NOT supplied by provider -> keep 'unknown' for A"
    else:
        basis = "ambiguous (need >= 2 timed commits and lead silence); keep 'unknown'"
    out.append(f"OBSERVED TIMESTAMP BASIS: {basis}")
    return "\n".join(out)


async def main_async(args) -> None:
    key = load_key()
    if not key:
        sys.exit("ELEVENLABS_API_KEY is not set. Put it in backend/.env (ELEVENLABS_API_KEY=...) "
                 "or export it, then rerun. Nothing was sent.")
    if args.wav:
        pcm = read_wav(Path(args.wav))
    else:
        pcm = sys.stdin.buffer.read(int(args.seconds * SAMPLE_RATE) * 2)
        if not pcm:
            sys.exit("No PCM on stdin (expect raw 16 kHz mono s16le).")
    pcm = pcm[: len(pcm) // 2 * 2]
    for i in range(1, args.streams + 1):
        print(f"\n=== stream {i} of {args.streams} (fresh connection) ===")
        print(analyse(await run_stream(i, key, pcm, args)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", help="absolute path to consented 16 kHz mono 16-bit WAV")
    src.add_argument("--stdin-pcm", action="store_true", help="read raw s16le 16 kHz mono PCM from stdin")
    p.add_argument("--seconds", type=float, default=15.0, help="max speech seconds to stream (default 15)")
    p.add_argument("--lead-silence", type=float, default=3.0)
    p.add_argument("--streams", type=int, default=2, help="2 = also check a second fresh connection")
    p.add_argument("--vad-silence", type=float, default=0.65)
    p.add_argument("--url", help=argparse.SUPPRESS)  # test hook: fake upstream
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
