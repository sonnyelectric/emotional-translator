"""Public-endpoint guards: SESSION_MAX_SECONDS auto-stop and LIVE_DAILY_MAX_SECONDS cap (fakes only)."""

import pytest
from live_helpers import ORIGIN, Recorder, command, live_client, live_settings, make_runtime, send_frames
from starlette.websockets import WebSocketDisconnect

from backend.app.config import Settings


def test_defaults():
    settings = Settings()
    assert settings.session_max_seconds == 300
    assert settings.live_daily_max_seconds is None
    assert settings.enable_tune_route is False


def run_until_stopped(client) -> Recorder:
    with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, 5)
        rec.until_type("session.status", state="stopped")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000
    return rec


@pytest.mark.parametrize("paused", [False, True])
def test_session_max_seconds_stops_cleanly_with_warning(paused):
    runtime = make_runtime(settings=live_settings(session_max_seconds=0.5))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        if paused:
            ws.send_text(command("session.pause"))
            rec.until_type("session.status", state="paused")
        warning = rec.until_type("session.warning", code="SESSION_TIME_LIMIT")
        assert warning["payload"]["recoverable"] is True
        rec.until_type("session.status", state="stopping")
        rec.until_type("session.status", state="stopped")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000
    assert "session.error" not in rec.types()
    assert runtime.lease is None


def test_session_stopped_by_user_before_limit_gets_no_warning():
    runtime = make_runtime(settings=live_settings(session_max_seconds=60))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    assert "session.warning" not in rec.types()


def test_daily_cap_stops_running_session_then_refuses_new_ones():
    runtime = make_runtime(settings=live_settings(session_max_seconds=60, live_daily_max_seconds=0.5))
    with live_client(runtime) as client:
        rec = run_until_stopped(client)
        assert rec.of("session.warning")[-1]["payload"]["code"] == "LIVE_DAILY_LIMIT_REACHED"
        assert runtime.daily_remaining() == 0
        with client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
            refused = Recorder(ws)
            ws.send_text(command("session.start"))
            refused.until_type("session.status", state="connecting")
            error = refused.until_type("session.error")
            assert error["payload"]["code"] == "LIVE_DAILY_LIMIT_REACHED"
            assert "Replay still works" in error["payload"]["message"]
            refused.until_type("session.status", state="error")
    assert runtime.lease is None


def test_daily_usage_accumulates_and_resets_each_utc_day():
    now = [1_800_000_000.0]  # 2027-01-15 08:00 UTC
    runtime = make_runtime(settings=live_settings(live_daily_max_seconds=100))
    runtime.wall_clock = lambda: now[0]
    assert runtime.daily_remaining() == 100
    runtime.charge(30)
    runtime.charge(30)
    assert runtime.daily_remaining() == 40
    runtime.charge(70)
    assert runtime.daily_remaining() == 0
    now[0] += 24 * 3600
    assert runtime.daily_remaining() == 100


def test_no_daily_cap_by_default():
    runtime = make_runtime()
    runtime.charge(10_000)
    assert runtime.daily_remaining() is None
