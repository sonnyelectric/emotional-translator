#!/usr/bin/env python3
"""Stream a 16 kHz mono s16le WAV to the dev tuning route and print each window's scores.

Needs a live backend with the model loaded (scripts/demo_live.sh or
scripts/start_backend.sh --live). No API key is used; Scribe is never contacted and no
transcript is produced. Output is the model's real scores, one JSON line per window.

Usage (repo root):
  .venv/bin/python scripts/tune_wav.py --wav ~/model-cache/emotion2vec_plus_large/example/test.wav
Options: --url ws://127.0.0.1:8000/ws/dev/tune  --pace (send at real time)  --tail 3.0
Convert other audio first: ffmpeg -i in.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav
"""

import argparse
import asyncio
import json
import sys
import time
import wave
from pathlib import Path

import websockets

FRAME_SAMPLES = 640  # 40 ms, same as the browser capture


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            sys.exit("WAV must be 16 kHz mono 16-bit (see --help for an ffmpeg command).")
        return w.readframes(w.getnframes())


async def run(args) -> int:
    pcm = read_pcm(Path(args.wav).expanduser())
    step = FRAME_SAMPLES * 2
    total_s = len(pcm) / 32000
    async with websockets.connect(args.url, max_size=2**20) as ws:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "tune.hello":
            print(json.dumps(hello))
            return 1
        print(json.dumps({"hello": hello}))
        for _ in range(200):  # wait for the model (it may still be loading)
            if hello.get("model_state") in ("ready", "degraded"):
                break
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
            except TimeoutError:
                continue
            if msg.get("type") == "tune.model":
                hello["model_state"] = msg["model_state"]
        t0 = time.monotonic()
        usable = len(pcm) // step * step  # whole 40 ms frames only
        for i in range(0, usable, step):
            await ws.send(pcm[i:i + step])
            if args.pace:
                await asyncio.sleep(max(0.0, t0 + (i + step) / 32000 - time.monotonic()))
        expected = max(0, int((usable / 32000 - 2.0) // 1.0) + 1)
        got = 0
        deadline = time.monotonic() + args.tail + 2.0
        while got < expected and time.monotonic() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
            except TimeoutError:
                continue
            if msg.get("type") == "tune.window":
                got += 1
            print(json.dumps(msg))
        print(json.dumps({"summary": {"audio_seconds": round(total_s, 2), "windows_expected": expected,
                                      "windows_received": got}}))
    return 0 if got == expected else 2


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wav", required=True)
    p.add_argument("--url", default="ws://127.0.0.1:8000/ws/dev/tune")
    p.add_argument("--pace", action="store_true")
    p.add_argument("--tail", type=float, default=3.0)
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
