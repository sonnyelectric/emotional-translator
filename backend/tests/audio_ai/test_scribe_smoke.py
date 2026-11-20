import asyncio
import os
import subprocess
import sys
import wave
from pathlib import Path

from fake_scribe_server import FakeScribe, send

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "smoke_scribe.py"


def _env(**extra):
    env = {k: v for k, v in os.environ.items() if k != "ELEVENLABS_API_KEY"}
    env.update(extra)
    return env


def _wav(path: Path, seconds=1.0):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(bytes(int(seconds * 16000) * 2))


def test_refuses_without_key(tmp_path):
    wav = tmp_path / "a.wav"
    _wav(wav)
    # empty HOME-independent: key is only read from env or backend/.env (absent in worktree)
    r = subprocess.run([sys.executable, str(SCRIPT), "--wav", str(wav)], env=_env(), capture_output=True, text=True)
    if (ROOT / "backend" / ".env").exists():
        return  # a developer key exists locally; refusal path not testable here
    assert r.returncode != 0
    assert "ELEVENLABS_API_KEY is not set" in r.stderr
    assert "Nothing was sent" in r.stderr


def test_smoke_against_fake_upstream_scrubs_and_detects_connection_basis(tmp_path):
    wav = tmp_path / "a.wav"
    _wav(wav, 1.0)
    secret_word = "confidential"

    async def script(fake, ws):
        await asyncio.sleep(0.5)
        for text, s, e in ((secret_word, 0.6, 1.0), ("second", 1.2, 1.6)):
            await send(ws, message_type="partial_transcript", text=text)
            await send(ws, message_type="committed_transcript", text=text)
            await asyncio.sleep(0.05)
            await send(
                ws,
                message_type="committed_transcript_with_timestamps",
                text=text,
                language_code="en",
                words=[
                    {"text": text, "start": s, "end": e, "type": "word"},
                    {"text": " ", "start": e, "end": e, "type": "spacing"},
                ],
            )
        await asyncio.sleep(10)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(SCRIPT), "--wav", str(wav), "--streams", "1", "--lead-silence", "0.5",
                "--url", fake.url,
                env=_env(ELEVENLABS_API_KEY="test-key-not-real"),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), 60)
            return proc.returncode, out.decode(), err.decode()

    code, out, err = asyncio.run(main())
    assert code == 0, err
    assert "committed_transcript_with_timestamps" in out
    assert "OBSERVED TIMESTAMP BASIS: connection-relative" in out
    assert "spacing" in out  # item types reported
    assert secret_word not in out and "second" not in out.replace("second stream", "")
    assert "test-key-not-real" not in out + err
