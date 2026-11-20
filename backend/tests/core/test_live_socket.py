"""A-03: live WebSocket boundary, sample clock, lease and lifecycle with fake ports."""

import json

import pytest
from fakes_model import SAD, FakeScorer, FakeWorker
from fakes_scribe import FakeScribeAdapter, Utterance
from fastapi.testclient import TestClient
from live_helpers import (
    FRAME,
    ORIGIN,
    Recorder,
    live_settings,
    command,
    live_client,
    make_runtime,
    send_frames,
)
from starlette.websockets import WebSocketDisconnect

from backend.app.audio.clock import SampleClock, frame_samples, samples_to_ms
from backend.app.config import Settings
from backend.app.main import create_app

PIPELINE = json.loads(
    (__import__("pathlib").Path(__file__).resolve().parents[3] / "shared/fixtures/pipeline_examples.json").read_text())

ANGRY_UTTERANCE = Utterance(
    after_samples=48000,
    text="I am so angry right now.",
    words=[("I", 0.20, 0.40), ("am", 0.45, 0.70), ("so", 0.75, 1.00), ("angry", 1.05, 1.60),
           ("right", 1.65, 1.90), ("now.", 1.95, 2.40)],
)


@pytest.mark.parametrize("case", PIPELINE["binary_frame_cases"], ids=lambda c: str(c["frame_bytes"]))
def test_binary_frame_cases(case):
    samples = frame_samples(b"\x00" * case["frame_bytes"])
    if case["expected"] == "accept":
        assert samples == case["samples"]
    else:
        assert samples is None


def test_sample_clock_is_monotonic_and_counts_only_accepted():
    clock = SampleClock()
    assert clock.accept(640) == (0, 640)
    assert clock.accept(320) == (640, 960)
    assert samples_to_ms(640) == 40 and samples_to_ms(8) == 0.5


def test_end_to_end_session_with_fake_scribe_and_scorer():
    adapter = FakeScribeAdapter(utterances=[ANGRY_UTTERANCE])
    runtime = make_runtime(adapter)
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        assert rec.next()["payload"]["state"] == "connecting"
        listening = rec.until_type("session.status", state="listening")
        assert {k: listening["payload"][k] for k in ("sample_rate_hz", "channels", "sample_format")} == {
            "sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le"}
        send_frames(ws, 125)  # 5 s
        timed = rec.until_type("transcript.timed")
        assert [w["word_id"] for w in timed["payload"]["words"]][:2] == ["seg-1:w0", "seg-1:w1"]
        assert timed["payload"]["words"][0]["start_ms"] == 200  # connection origin is sample 0
        updated = rec.until_type("emotion.updated")
        p = updated["payload"]
        assert (p["primary"], p["shape"], p["color"]) == ("angry", "jagged", "#DC4545")
        assert (p["start_word_id"], p["end_word_id"]) == ("seg-1:w0", "seg-1:w5")
        final = rec.until_type("emotion.finalized")
        assert final["payload"]["annotation_id"] == p["annotation_id"]
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000
    types = rec.types()
    assert types.index("transcript.partial") < types.index("transcript.committed") < types.index("transcript.timed")
    assert adapter.total_samples == 125 * 640
    assert runtime.lease is None


def test_foreign_origin_rejected_before_accept():
    runtime = make_runtime()
    with live_client(runtime) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/ws/v1/session", headers={"origin": "http://evil.example"}):
                pass
        assert rejected.value.code == 1008


def test_audio_before_session_closes_with_policy():
    with live_client(make_runtime()) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        ws.send_bytes(FRAME)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1008


def test_malformed_command_unbound_closes_with_policy():
    with live_client(make_runtime()) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        ws.send_text('{"schema_version":"1.0","type":"session.start","payload":{"mode":"replay"}}')
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1008


def test_unknown_command_ignored_and_bad_frames_rejected():
    adapter = FakeScribeAdapter()
    with live_client(make_runtime(adapter)) as client, client.websocket_connect("/ws/v1/session",
                                                                                 headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(json.dumps({"schema_version": "1.0", "type": "future.command", "payload": {}}))
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        ws.send_bytes(b"\x00" * 638)
        assert rec.until_type("session.warning")["payload"]["code"] == "INVALID_AUDIO_FRAME"
        ws.send_text(command("session.resume"))
        assert rec.until_type("session.warning")["payload"]["code"] == "INVALID_STATE"
        ws.send_text('{"schema_version":"1.0","type":"session.pause","payload":{},"x":1}')
        assert rec.until_type("session.warning")["payload"]["code"] == "INVALID_COMMAND"
        send_frames(ws, 3)
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert adapter.total_samples == 3 * 640  # rejected frame added no time


def test_replay_mode_rejects_live_start_without_provider():
    app = create_app(Settings(mode="replay"))
    with TestClient(app) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        assert rec.next()["payload"]["state"] == "connecting"
        error = rec.next()
        assert error["type"] == "session.error" and error["payload"]["code"] == "LIVE_NOT_CONFIGURED"
        assert rec.next()["payload"]["state"] == "error"
    assert app.state.live_runtime is None


def test_single_live_lease_and_release():
    runtime = make_runtime()
    with live_client(runtime) as client:
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as first:
            rec = Recorder(first)
            first.send_text(command("session.start"))
            rec.until_type("session.status", state="listening")
            with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as second:
                second.send_text(command("session.start"))
                second.receive_json()
                error = second.receive_json()
                assert error["payload"]["code"] == "LIVE_SESSION_BUSY"
                assert error["session_id"] != rec.events[0]["session_id"]
            first.send_text(command("session.stop"))
            rec.until_type("session.status", state="stopped")
        assert runtime.lease is None
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as third:
            third.send_text(command("session.start"))
            assert Recorder(third).until_type("session.status", state="listening")


def test_disconnect_releases_lease():
    runtime = make_runtime()
    with live_client(runtime) as client:
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
            ws.send_text(command("session.start"))
            Recorder(ws).until_type("session.status", state="listening")
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
            ws.send_text(command("session.start"))
            Recorder(ws).until_type("session.status", state="listening")


def test_reset_binds_new_session_then_start_uses_it():
    with live_client(make_runtime()) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        ws.send_text(command("session.reset"))
        reset = ws.receive_json()
        assert (reset["type"], reset["seq"], reset["issued_at_ms"]) == ("session.reset", 1, 0)
        idle = ws.receive_json()
        assert idle["payload"]["state"] == "idle" and idle["session_id"] == reset["session_id"]
        ws.send_text(command("session.start"))
        connecting = ws.receive_json()
        assert connecting["session_id"] == reset["session_id"] and connecting["seq"] == 3


def test_pause_adds_no_time_and_resume_opens_new_epoch():
    second = Utterance(after_samples=40000, text="Still sad here.",
                       words=[("Still", 0.1, 0.5), ("sad", 0.6, 1.0), ("here.", 1.1, 1.5)])
    adapter = FakeScribeAdapter(by_epoch={2: [second]})
    runtime = make_runtime(adapter, worker=FakeWorker(FakeScorer(lambda w: SAD)))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 50)  # 2 s on epoch 1
        ws.send_text(command("session.pause"))
        rec.until_type("session.status", state="paused")
        ws.send_bytes(FRAME)  # forbidden while paused
        assert rec.until_type("session.warning")["payload"]["code"] == "AUDIO_NOT_ACCEPTED"
        ws.send_text(command("session.resume"))
        rec.until_type("session.status", state="connecting")
        rec.until_type("session.status", state="listening")
        send_frames(ws, 100)  # 4 s on epoch 2, origin at sample 32000
        timed = rec.until_type("transcript.timed")
        assert timed["payload"]["words"][0]["start_ms"] == 2000 + 100  # epoch origin 32000 samples
        updated = rec.until_type("emotion.updated")
        assert updated["payload"]["primary"] == "sad"
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert adapter.opened == [1, 2]
    assert adapter.streams[0].received == 50 * 640 and adapter.streams[1].received == 100 * 640


def test_scribe_relay_progresses_while_inference_blocked():
    adapter = FakeScribeAdapter(utterances=[ANGRY_UTTERANCE])
    worker = FakeWorker(FakeScorer())
    runtime = make_runtime(adapter, worker=worker)
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        worker.gate = __import__("asyncio").Event()  # never released: inference blocked
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 250)  # 10 s -> 9 windows, only 1 running + 2 pending kept
        rec.until_type("transcript.timed")
        rec.until(lambda e: e["type"] == "session.warning" and e["payload"]["code"] == "EMOTION_INFERENCE_SLOW")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert adapter.total_samples == 250 * 640
    assert len(worker.pending) <= 2
    assert "emotion.updated" not in rec.types()


@pytest.mark.parametrize("basis,origin,expect_cloud", [("segment", 16000, True), ("unknown", None, False)])
def test_timestamp_basis_through_fake_upstream(basis, origin, expect_cloud):
    utterance = Utterance(after_samples=64000, text="Leave me alone.", basis=basis, segment_origin_samples=origin,
                          words=[("Leave", 0.1, 0.4), ("me", 0.5, 0.7), ("alone.", 0.8, 1.4)])
    with live_client(make_runtime(FakeScribeAdapter(utterances=[utterance]))) as client, \
            client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 150)
        if expect_cloud:
            timed = rec.until_type("transcript.timed")
            assert timed["payload"]["words"][0]["start_ms"] == 1000 + 100  # segment origin added once
            assert rec.until_type("emotion.updated")["payload"]["start_word_id"] == "seg-1:w0"
        else:
            warning = rec.until_type("alignment.warning")
            assert warning["payload"]["code"] == "ALIGNMENT_BASIS_UNKNOWN"
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert bool(rec.of("transcript.timed")) == expect_cloud
    assert bool(rec.of("emotion.updated")) == expect_cloud
    assert [e["payload"]["text"] for e in rec.of("transcript.committed")] == ["Leave me alone."]



def _timing_outcomes(rec):
    return [e for e in rec.events if e["type"] in ("transcript.timed", "alignment.warning")]


def _run_live(adapter, settings, epochs):
    """Start; per epoch send frames and wait for that epoch's timing outcomes; Pause/Resume
    between epochs; stop. `epochs` is a list of (frames, expected cumulative outcomes)."""
    runtime = make_runtime(adapter, settings=settings)
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        for index, (frames, outcomes) in enumerate(epochs):
            if index:
                ws.send_text(command("session.pause"))
                rec.until_type("session.status", state="paused")
                ws.send_text(command("session.resume"))
                rec.until_type("session.status", state="listening")
            send_frames(ws, frames)
            if len(_timing_outcomes(rec)) < outcomes:
                rec.until(lambda e: len(_timing_outcomes(rec)) >= outcomes)
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    return rec


def test_connection_basis_setting_with_loose_text_match_places_cloud():
    # The real adapter reports basis "unknown"; the operator setting supplies "connection".
    # Timed words differ from the commit only in case and punctuation: the cloud still lands.
    utterance = Utterance(after_samples=48000, text="I am SO angry, right now!", basis="unknown",
                          words=[("i", 0.2, 0.4), ("am", 0.45, 0.7), ("so", 0.75, 1.0), ("angry", 1.05, 1.6),
                                 (",", 1.6, 1.6001), ("right", 1.65, 1.9), ("now", 1.95, 2.4)])
    rec = _run_live(FakeScribeAdapter(utterances=[utterance]),
                    live_settings(scribe_timestamp_basis="connection"), [(125, 1)])
    timed = rec.of("transcript.timed")[0]["payload"]
    assert "text" not in timed
    assert [w["text"] for w in timed["words"]] == ["I", "am", "SO", "angry,", "right", "now!"]
    assert timed["words"][0]["start_ms"] == 200
    assert rec.of("emotion.updated") and not rec.of("alignment.warning")


def test_segment_basis_setting_times_first_commit_per_epoch_only():
    # Segment-relative provider times (each segment starts at 0). Plan B places the first
    # segment of each connection at the epoch origin and refuses to guess the second.
    first = Utterance(after_samples=40000, text="Leave me alone.", basis="unknown",
                      words=[("Leave", 0.1, 0.4), ("me", 0.5, 0.7), ("alone.", 0.8, 1.4)])
    second = Utterance(after_samples=72000, text="Go away now.", basis="unknown",
                       words=[("Go", 0.1, 0.4), ("away", 0.5, 0.8), ("now.", 0.9, 1.3)])
    after_resume = Utterance(after_samples=40000, text="Still here.", basis="unknown",
                             words=[("Still", 0.2, 0.6), ("here.", 0.7, 1.2)])
    adapter = FakeScribeAdapter(by_epoch={1: [first, second], 2: [after_resume]})
    rec = _run_live(adapter, live_settings(scribe_timestamp_basis="segment"), [(125, 2), (100, 3)])
    outcomes = [(e["type"], e["payload"]["segment_id"]) for e in _timing_outcomes(rec)]
    assert outcomes == [("transcript.timed", "seg-1"), ("alignment.warning", "seg-2"),
                        ("transcript.timed", "seg-3")]
    assert rec.of("alignment.warning")[0]["payload"]["code"] == "ALIGNMENT_BASIS_UNKNOWN"
    timed = rec.of("transcript.timed")
    assert timed[0]["payload"]["words"][0]["start_ms"] == 100  # epoch 1 origin is sample 0
    assert timed[1]["payload"]["words"][0]["start_ms"] == 5000 + 200  # epoch 2 origin = 125 frames
    assert {e["payload"]["segment_id"] for e in rec.of("emotion.updated")} <= {"seg-1", "seg-3"}


def test_timed_text_revision_reaches_the_client_and_validates():
    utterance = Utterance(after_samples=48000, text="I thought you would call.", basis="unknown",
                          timed_text="I taught you would call.",
                          words=[("I", 0.2, 0.4), ("taught", 0.45, 0.8), ("you", 0.85, 1.0), ("would", 1.05, 1.3),
                                 ("call.", 1.35, 1.9)])
    rec = _run_live(FakeScribeAdapter(utterances=[utterance]),
                    live_settings(scribe_timestamp_basis="connection"), [(125, 1)])
    timed = rec.of("transcript.timed")[0]["payload"]
    assert timed["text"] == "I taught you would call."
    assert rec.validator.segments["seg-1"].text == "I taught you would call."
    assert rec.of("emotion.updated")
