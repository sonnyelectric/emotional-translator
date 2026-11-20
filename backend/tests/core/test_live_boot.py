"""Hosted health checks: live mode must answer / and /healthz before torch/FunASR finish importing."""

import json
import threading
import time

from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.config import Settings
from backend.app.main import create_app


def test_live_boot_does_not_block_health_checks(monkeypatch):
    release = threading.Event()
    calls = []

    def slow_build(settings):
        calls.append(settings)
        release.wait(timeout=10)  # stands in for a slow torch/FunASR import
        raise RuntimeError("stub runtime")

    monkeypatch.setattr(main_module, "build_live_runtime", slow_build)
    app = create_app(Settings(mode="live"))
    started = time.monotonic()
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert time.monotonic() - started < 3
        assert app.state.live_starting is True

        with client.websocket_connect("/ws/v1/session", headers={"origin": "http://localhost:5173"}) as ws:
            ws.send_text(json.dumps({"schema_version": "1.0", "type": "session.start",
                                     "payload": {"mode": "live"}}))
            codes = []
            for _ in range(4):
                event = json.loads(ws.receive_text())
                if event["type"] == "session.error":
                    codes.append(event["payload"]["code"])
                    break
            assert codes == ["LIVE_STARTING"]
        release.set()
    assert len(calls) == 1
