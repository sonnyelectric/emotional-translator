import asyncio
import base64
import json

import pytest
from fake_scribe_server import FakeScribe, send

from backend.app.adapters.scribe import (
    FATAL_ERRORS,
    TRANSIENT_ERRORS,
    ElevenLabsScribeAdapter,
    ScribeClosedError,
    ScribeSetupError,
    seconds_to_samples,
)

KEY = "test-key-not-real"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 15))


async def collect(stream, n, timeout=5):
    out = []

    async def go():
        async for ev in stream.events():
            out.append(ev)
            if len(out) >= n:
                return

    await asyncio.wait_for(go(), timeout)
    return out


async def drain(stream):
    return [e async for e in stream.events()]


def adapter(fake, vad=0.65):
    return ElevenLabsScribeAdapter(api_key=KEY, vad_silence_secs=vad, url=fake.url)


def test_request_flags_header_and_audio_chunk():
    async def main():
        fake = FakeScribe()
        async with fake.running():
            s = await adapter(fake).open(3)
            pcm = bytes(range(64))
            await s.send_pcm(pcm)
            await s.send_pcm(b"")  # no-op
            for _ in range(50):
                if fake.received:
                    break
                await asyncio.sleep(0.02)
            await s.aclose()
            assert fake.headers["xi-api-key"] == KEY
            assert fake.query == {
                "model_id": "scribe_v3_live",
                "audio_format": "pcm_16000",
                "commit_strategy": "vad",
                "vad_silence_threshold_secs": "0.65",
                "include_timestamps": "true",
            }
            assert len(fake.received) == 1
            msg = fake.received[0]
            assert msg["message_type"] == "input_audio_chunk"
            assert base64.b64decode(msg["audio_base_64"]) == pcm
            assert msg["commit"] is False and msg["sample_rate"] == 16000
            assert "previous_text" not in msg

    run(main())


def test_ordering_partial_dedupe_keepalive_and_delayed_timed():
    async def script(fake, ws):
        await send(ws, message_type="partial_transcript", text="")  # keepalive
        await send(ws, message_type="partial_transcript", text="hel")
        await send(ws, message_type="partial_transcript", text="hel")  # repeat
        await send(ws, message_type="partial_transcript", text="hello wor")
        await send(ws, message_type="committed_transcript", text="Hello world.")
        # a new partial arrives BEFORE the delayed timed commit
        await send(ws, message_type="partial_transcript", text="next")
        await send(ws, message_type="warning", warning="x")
        await send(
            ws,
            message_type="committed_transcript_with_timestamps",
            text="Hello world.",
            language_code="en",
            words=[
                {"text": "Hello", "start": 0.5, "end": 0.9, "type": "word"},
                {"text": " ", "start": 0.9, "end": 0.95, "type": "spacing"},
                {"text": "world.", "start": 1.0, "end": 1.4, "type": "word"},
            ],
        )
        await asyncio.sleep(0.3)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(7)
            evs = await collect(s, 5)
            await s.aclose()
            assert [e.kind for e in evs] == ["partial", "partial", "commit", "partial", "timed"]
            assert [e.text for e in evs] == ["hel", "hello wor", "Hello world.", "next", "Hello world."]
            assert all(e.epoch == 7 for e in evs)
            assert evs[2].provider_commit_key is None
            timed = evs[4]
            assert timed.timestamp_basis == "unknown" and timed.segment_origin_samples is None
            assert timed.language_code == "en"
            assert [(t.text, t.start_sample, t.end_sample) for t in timed.tokens] == [
                ("Hello", 8000, 14400),
                ("world.", 16000, 22400),
            ]

    run(main())


def test_unit_conversion_and_no_fabricated_tokens():
    assert seconds_to_samples(1.0) == 16000
    assert seconds_to_samples(0.0001) == 2
    assert seconds_to_samples(None) is None
    assert seconds_to_samples("1") is None
    assert seconds_to_samples(-1) is None
    assert seconds_to_samples(float("nan")) is None
    assert seconds_to_samples(True) is None

    async def script(fake, ws):
        await send(
            ws,
            message_type="committed_transcript_with_timestamps",
            text="a b c",
            words=[
                {"text": "a", "start": 0.0, "end": 0.1, "type": "word"},
                {"text": "b", "type": "word"},  # no timing: dropped
                {"text": "(laugh)", "start": 0.2, "end": 0.3, "type": "audio_event"},
                {"text": "c", "start": 0.3, "end": 0.4},
            ],
        )
        await send(ws, message_type="committed_transcript_with_timestamps", text="no words")
        await asyncio.sleep(0.2)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(0)
            a, b = await collect(s, 2)
            await s.aclose()
            assert [t.text for t in a.tokens] == ["a", "c"]
            assert b.tokens == ()

    run(main())


@pytest.mark.parametrize("kind", sorted(FATAL_ERRORS | TRANSIENT_ERRORS))
def test_error_classification(kind):
    async def script(fake, ws):
        await send(ws, message_type=kind, error="secret detail text")
        await asyncio.sleep(0.2)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(1)
            (ev,) = await collect(s, 1)
            await s.aclose()
            assert ev.kind == ("fatal_error" if kind in FATAL_ERRORS else "transient_error")
            assert ev.code == kind
            assert "secret" not in (ev.message or "")

    run(main())


def test_documented_errors_all_classified():
    assert {"auth_error", "quota_exceeded", "unaccepted_terms"} <= FATAL_ERRORS
    assert not FATAL_ERRORS & TRANSIENT_ERRORS
    assert len(FATAL_ERRORS | TRANSIENT_ERRORS) == 14


def test_fatal_error_ends_stream():
    async def script(fake, ws):
        await send(ws, message_type="auth_error", error="bad")
        await asyncio.sleep(1)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(1)
            assert [e.kind for e in await drain(s)] == ["fatal_error"]
            await s.aclose()

    run(main())


def test_unexpected_upstream_close_is_transient_and_ends():
    async def script(fake, ws):
        await send(ws, message_type="committed_transcript", text="x")
        await ws.close()

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(1)
            evs = await drain(s)
            assert [e.kind for e in evs] == ["commit", "transient_error"]
            assert evs[1].code == "upstream_closed"
            with pytest.raises(ScribeClosedError):
                await s.send_pcm(b"\0\0")
            await s.aclose()

    run(main())


def test_clean_close_cleans_up_without_error_notice():
    async def main():
        fake = FakeScribe()
        async with fake.running():
            s = await adapter(fake).open(1)
            await s.aclose()
            await s.aclose()  # idempotent
            await asyncio.wait_for(fake.closed.wait(), 3)
            assert await drain(s) == []
            assert s._reader.done()
            with pytest.raises(ScribeClosedError):
                await s.send_pcm(b"\0\0")

    run(main())


def test_aclose_while_consumer_waiting_ends_iteration():
    async def main():
        fake = FakeScribe()
        async with fake.running():
            s = await adapter(fake).open(1)
            consumer = asyncio.ensure_future(drain(s))
            await asyncio.sleep(0.1)
            await s.aclose()
            assert await asyncio.wait_for(consumer, 3) == []

    run(main())


def test_odd_length_pcm_rejected():
    async def main():
        fake = FakeScribe()
        async with fake.running():
            s = await adapter(fake).open(1)
            with pytest.raises(ValueError):
                await s.send_pcm(b"\0")
            await s.aclose()

    run(main())


@pytest.mark.parametrize("status,fatal", [(401, True), (403, True), (402, True), (429, False), (503, False)])
def test_open_http_rejection(status, fatal):
    async def main():
        fake = FakeScribe(reject_status=status)
        async with fake.running():
            with pytest.raises(ScribeSetupError) as ei:
                await adapter(fake).open(1)
            assert ei.value.fatal is fatal
            assert KEY not in str(ei.value)

    run(main())


def test_open_connection_refused_is_transient():
    async def main():
        a = ElevenLabsScribeAdapter(api_key=KEY, vad_silence_secs=0.5, url="ws://127.0.0.1:1/x")
        with pytest.raises(ScribeSetupError) as ei:
            await a.open(1)
        assert ei.value.fatal is False

    run(main())


def test_requires_key():
    with pytest.raises(ValueError):
        ElevenLabsScribeAdapter(api_key="", vad_silence_secs=0.5)


def test_malformed_and_binary_frames_ignored():
    async def script(fake, ws):
        await ws.send("not json")
        await ws.send(b"\x00\x01")
        await ws.send(json.dumps([1, 2]))
        await send(ws, message_type="committed_transcript", text="ok")
        await asyncio.sleep(0.2)

    async def main():
        fake = FakeScribe(script)
        async with fake.running():
            s = await adapter(fake).open(1)
            (ev,) = await collect(s, 1)
            await s.aclose()
            assert ev.text == "ok"

    run(main())
