"""Dev tuning route (/ws/dev/tune): model-only scores, never transcript events (fakes only)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.config import Settings
from backend.app.main import create_app

from fakes_model import ANGRY, NEUTRAL, FakeScorer, FakeWorker
from live_helpers import FRAME, ORIGIN, live_client, make_runtime, send_frames


def receive(ws, kind: str, limit: int = 200) -> dict:
    for _ in range(limit):
        message = json.loads(ws.receive_text())
        assert not message["type"].startswith(("transcript", "session", "emotion")), message
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind}")


def wait_ready(runtime) -> None:
    import time

    for _ in range(200):
        if runtime.model_usable:
            return
        time.sleep(0.01)
    raise AssertionError("model never ready")


def test_tune_streams_scores_and_classify_without_transcript():
    runtime = make_runtime(worker=FakeWorker(FakeScorer(lambda w: ANGRY if w.start_sample == 0 else NEUTRAL)))
    with live_client(runtime) as client:
        wait_ready(runtime)
        with client.websocket_connect("/ws/dev/tune", headers=ORIGIN) as ws:
            hello = receive(ws, "tune.hello")
            assert hello["note"].startswith("Tuning mode")
            assert hello["thresholds"]["visible_support"] == runtime.settings.emotion_visible_support
            send_frames(ws, 75)  # 3.0 s -> windows [0, 2 s) and [1 s, 3 s)
            first = receive(ws, "tune.window")
            assert first["kind"] == "scored" and first["start_ms"] == 0 and first["end_ms"] == 2000
            assert set(first["scores"]) == set(ANGRY) and first["scores"] == pytest.approx(ANGRY)
            assert first["top_label"] == "angry"
            assert first["classify"]["primary"] == "angry"
            second = receive(ws, "tune.window")
            assert second["start_ms"] == 1000 and second["top_label"] == "neutral"
            # EMA with the previous window, as in the live phrase engine
            alpha = runtime.settings.emotion_smoothing_alpha
            expected = alpha * NEUTRAL["neutral"] + (1 - alpha) * ANGRY["neutral"]
            assert second["smoothed"]["neutral"] == pytest.approx(expected, rel=0.05)


def test_tune_rejects_foreign_origin_and_bad_frames():
    runtime = make_runtime()
    with live_client(runtime) as client:
        wait_ready(runtime)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/dev/tune", headers={"origin": "http://evil.example"}) as ws:
                ws.receive_text()
        with client.websocket_connect("/ws/dev/tune", headers=ORIGIN) as ws:
            receive(ws, "tune.hello")
            ws.send_bytes(b"\x00")
            assert receive(ws, "tune.warning")["code"] == "INVALID_AUDIO_FRAME"


def test_tune_reports_unavailable_model():
    runtime = make_runtime(model=False)
    with live_client(runtime) as client:
        with client.websocket_connect("/ws/dev/tune", headers=ORIGIN) as ws:
            assert json.loads(ws.receive_text())["code"] == "MODEL_UNAVAILABLE"


def test_tune_route_absent_in_replay_mode():
    app = create_app(Settings(mode="replay"))
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/dev/tune", headers=ORIGIN) as ws:
                ws.receive_text()


def test_tune_frames_before_model_ready_warn_once():
    worker = FakeWorker(FakeScorer())
    runtime = make_runtime(worker=worker)
    runtime.model_state = "loading"
    runtime.start = _no_start  # keep the model in "loading"
    with live_client(runtime) as client:
        with client.websocket_connect("/ws/dev/tune", headers=ORIGIN) as ws:
            receive(ws, "tune.hello")
            send_frames(ws, 3, FRAME)
            assert receive(ws, "tune.warning")["code"] == "MODEL_NOT_READY"
            ws.send_text(json.dumps({"type": "tune.reset"}))
            receive(ws, "tune.reset")  # no second warning arrives before this
    assert worker.offered == 0


async def _no_start() -> None:
    return None
