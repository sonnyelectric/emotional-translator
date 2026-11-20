"""A-05: Scribe retry/backoff, permanent failures, model degradation and bounded drain."""

import time

import pytest
from fakes_model import FakeScorer, FakeWorker
from fakes_scribe import FakeScribeAdapter, FakeSetupError, Utterance
from live_helpers import ORIGIN, Recorder, command, live_client, live_settings, make_runtime, send_frames

from backend.app.audio.relay import backoff_delay, classify_failure

HELLO = Utterance(after_samples=40000, text="Hello there friend.",
                  words=[("Hello", 0.2, 0.6), ("there", 0.7, 1.0), ("friend.", 1.1, 1.6)])


def code_of(rec, kind):
    return [e["payload"]["code"] for e in rec.of(kind)]


def start(ws, rec):
    ws.send_text(command("session.start"))


def test_backoff_schedule_and_jitter():
    assert [backoff_delay(n, 500, 4000, lambda: 1.0) for n in range(1, 6)] == [0.5, 1.0, 2.0, 4.0, 4.0]
    assert backoff_delay(1, 500, 4000, lambda: 0.0) == 0.25


def test_failure_classification():
    seen = set()
    assert classify_failure("auth_error", False, seen) == "SCRIBE_AUTH"
    assert classify_failure("quota_exceeded", False, seen) == "SCRIBE_QUOTA"
    assert classify_failure("unaccepted_terms", False, seen) == "SCRIBE_TERMS"
    assert classify_failure("http_401", True, seen) == "SCRIBE_AUTH"
    assert classify_failure("rate_limited", False, seen) is None
    assert classify_failure("insufficient_audio_activity", False, seen) is None
    assert classify_failure("input_error", False, seen) is None  # transient once
    assert classify_failure("input_error", False, seen) == "SCRIBE_INPUT_REJECTED"  # then fatal
    assert classify_failure("weird", True, set()) == "SCRIBE_FATAL"


def test_permanent_open_failure_does_not_retry():
    adapter = FakeScribeAdapter(open_errors=[FakeSetupError("http_401", True)])
    runtime = make_runtime(adapter)
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        error = rec.until_type("session.error")
        assert error["payload"] == {"code": "SCRIBE_AUTH", "message": error["payload"]["message"],
                                    "recoverable": False}
        status = rec.next()
        assert (status["payload"]["state"], status["payload"]["scribe"]) == ("error", "failed")
    assert adapter.opened == [1] and runtime.lease is None


def test_transient_open_failure_retries_then_listens():
    adapter = FakeScribeAdapter(open_errors=[FakeSetupError("connect_failed_OSError", False)] * 2)
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
    assert len(adapter.opened) == 3


def test_retry_exhaustion_is_fatal():
    adapter = FakeScribeAdapter(open_errors=[FakeSetupError("connect_failed_OSError", False)] * 9)
    runtime = make_runtime(adapter, settings=live_settings(retry_max_attempts=3))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        assert rec.until_type("session.error")["payload"]["code"] == "SCRIBE_RETRY_EXHAUSTED"
    assert len(adapter.opened) == 3


def failing_after(samples, code, times=1):
    fired = []

    def hook(stream):
        if stream.received >= samples and len(fired) < times and stream.epoch not in fired:
            fired.append(stream.epoch)
            stream.push("transient_error", code=code, message="x")
    return hook


def test_midstream_transient_reconnects_new_epoch_and_preserves_text():
    adapter = FakeScribeAdapter(
        by_epoch={1: [Utterance(after_samples=40000, text="Before the drop.",
                                words=[("Before", 0.2, 0.6), ("the", 0.7, 0.9), ("drop.", 1.0, 1.5)]),
                      Utterance(after_samples=44800, text="Lost timing here.", words=[], emit_timed=False)],
                  2: [Utterance(after_samples=40000, text="After the drop.",
                                words=[("After", 0.2, 0.6), ("the", 0.7, 0.9), ("drop.", 1.0, 1.5)])]},
        on_send=failing_after(48000, "rate_limited"))
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 75)  # 3 s on epoch 1; error at 48000 samples
        assert rec.until_type("session.warning")["payload"]["code"] == "SCRIBE_RECONNECTING"
        rec.until(lambda e: e["type"] == "session.status" and e["payload"]["scribe"] == "connected")
        origin = adapter.total_samples  # first sample forwarded on epoch 2 is after these
        send_frames(ws, 100)
        timed = rec.until(lambda e: e["type"] == "transcript.timed" and e["payload"]["segment_id"] == "seg-3")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert adapter.opened == [1, 2]
    committed = [e["payload"]["text"] for e in rec.of("transcript.committed")]
    assert committed == ["Before the drop.", "Lost timing here.", "After the drop."]  # no duplicates
    warning = [e["payload"] for e in rec.of("alignment.warning")]
    assert warning[0]["segment_id"] == "seg-2" and warning[0]["code"] == "ALIGNMENT_TIMESTAMPS_MISSING"
    # Epoch 2 words sit after everything forwarded on epoch 1 (+ any samples received during the outage).
    assert timed["payload"]["words"][0]["start_ms"] >= origin / 16 + 200
    assert adapter.streams[1].received + adapter.streams[0].received <= 175 * 640


def test_retry_once_codes_become_fatal_on_repeat():
    adapter = FakeScribeAdapter(on_send=failing_after(3200, "input_error", times=2))
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 10)
        rec.until(lambda e: e["type"] == "session.status" and e["payload"]["scribe"] == "connected"
                  and e["seq"] > 3)
        send_frames(ws, 10)
        assert rec.until_type("session.error")["payload"]["code"] == "SCRIBE_INPUT_REJECTED"


def test_insufficient_audio_activity_reconnects_quietly():
    adapter = FakeScribeAdapter(on_send=failing_after(3200, "insufficient_audio_activity"))
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 10)
        rec.until(lambda e: e["type"] == "session.status" and e["payload"]["scribe"] == "reconnecting")
        rec.until(lambda e: e["type"] == "session.status" and e["payload"]["scribe"] == "connected")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert "SCRIBE_RECONNECTING" not in code_of(rec, "session.warning")


def test_model_load_failure_is_text_only():
    adapter = FakeScribeAdapter(utterances=[HELLO])
    runtime = make_runtime(adapter, worker=FakeWorker(FakeScorer(), fail_load=True))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 100)
        rec.until_type("transcript.timed")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert runtime.model_state == "failed"
    assert "EMOTION_MODEL_UNAVAILABLE" in code_of(rec, "session.warning")
    assert not rec.of("emotion.updated")
    assert rec.of("session.status")[-1]["payload"]["emotion_model"] == "failed"


def test_scoring_failures_degrade_and_transcript_continues():
    adapter = FakeScribeAdapter(utterances=[HELLO])
    runtime = make_runtime(adapter, worker=FakeWorker(FakeScorer(), fail_scoring=True))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 150)
        rec.until_type("transcript.timed")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert "EMOTION_MODEL_UNAVAILABLE" in code_of(rec, "session.warning")
    assert runtime.model_state in ("degraded", "failed")
    assert not rec.of("emotion.updated")


def test_stop_drain_is_bounded_with_blocked_inference():
    import asyncio

    adapter = FakeScribeAdapter(utterances=[HELLO])
    worker = FakeWorker(FakeScorer())
    runtime = make_runtime(adapter, worker=worker, settings=live_settings(session_drain_timeout_ms=300))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        worker.gate = asyncio.Event()
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 100)
        rec.until_type("transcript.timed")
        began = time.monotonic()
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
        elapsed = time.monotonic() - began
    assert elapsed < 1.5
    assert ("emotion.updated" in rec.types()) is False  # nothing scored: no phantom cloud
    assert any(d[0] == rec.events[0]["session_id"] for d in worker.discards)
    assert runtime.lease is None


def test_late_results_after_stop_are_quarantined():
    adapter = FakeScribeAdapter(utterances=[HELLO])
    runtime = make_runtime(adapter)
    with live_client(runtime) as client:
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
            rec = Recorder(ws)
            ws.send_text(command("session.start"))
            rec.until_type("session.status", state="listening")
            send_frames(ws, 60)
            ws.send_text(command("session.stop"))
            rec.until_type("session.status", state="stopped")
        session_id = rec.events[0]["session_id"]
        from backend.app.audio_ai_ports import WindowNotice

        before = runtime.metrics.counters.get("window_results_quarantined", 0)
        runtime.worker.out.put_nowait(WindowNotice(session_id, 1, 0, 32000, "dropped", 0.0, 1.0))
        deadline = time.monotonic() + 2
        while runtime.metrics.counters.get("window_results_quarantined", 0) == before:
            assert time.monotonic() < deadline
            time.sleep(0.01)


@pytest.mark.parametrize("code,expected", [("quota_exceeded", "SCRIBE_QUOTA"), ("unaccepted_terms", "SCRIBE_TERMS")])
def test_midstream_permanent_failure_preserves_transcript(code, expected):
    adapter = FakeScribeAdapter(utterances=[HELLO], on_send=failing_after(48000, code))
    adapter.on_send = None

    def hook(stream):
        if stream.received >= 48000 and not getattr(stream, "fired", False):
            stream.fired = True
            stream.queue.put_nowait(__import__("backend.app.audio_ai_ports", fromlist=["x"]).ScribeNotice(
                epoch=stream.epoch, kind="fatal_error", code=code, message="x"))
    adapter.on_send = hook
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 80)
        assert rec.until_type("session.error")["payload"]["code"] == expected
        assert rec.next()["payload"]["state"] == "error"
    assert adapter.opened == [1]
    assert [e["payload"]["text"] for e in rec.of("transcript.committed")] == ["Hello there friend."]


def test_resume_waits_for_pause_cleanup():
    adapter = FakeScribeAdapter()
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 5)
        ws.send_text(command("session.pause"))
        ws.send_text(command("session.resume"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 5)
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert adapter.opened == [1, 2]
    assert adapter.streams[0].closed and adapter.streams[1].received == 5 * 640
