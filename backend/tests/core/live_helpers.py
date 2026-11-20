"""Shared helpers for live WebSocket tests (fakes only, no network or model)."""

from __future__ import annotations

import json

import anyio
from starlette.websockets import WebSocketDisconnect
from contextlib import contextmanager

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.replay import StreamValidator
from backend.app.schemas import schema_validator
from backend.app.session import LiveRuntime

from fakes_model import FakePolicy, FakeScheduler, FakeScorer, FakeWorker
from fakes_scribe import FakeScribeAdapter

ORIGIN = {"origin": "http://localhost:5173"}
FRAME = b"\x01\x00" * 640  # 40 ms of 16 kHz s16le


def command(kind: str) -> str:
    payload = {"mode": "live"} if kind == "session.start" else {}
    return json.dumps({"schema_version": "1.0", "type": kind, "payload": payload})


async def no_sleep(_seconds: float) -> None:
    return None


def live_settings(**overrides) -> Settings:
    values = {"mode": "live", "retry_base_ms": 1, "retry_cap_ms": 2, "session_drain_timeout_ms": 400,
              "phrase_pending_timeout_ms": 500, "phrase_lookahead_ms": 100}
    values.update(overrides)
    return Settings(**values)


def make_runtime(adapter: FakeScribeAdapter | None = None, *, worker: FakeWorker | None = None,
                 model: bool = True, settings: Settings | None = None, **worker_kwargs) -> LiveRuntime:
    settings = settings or live_settings()
    adapter = adapter or FakeScribeAdapter()
    if model and worker is None:
        worker = FakeWorker(FakeScorer(), **worker_kwargs)
    return LiveRuntime(settings, scribe_adapter=adapter, worker=worker if model else None,
                       scheduler_factory=FakeScheduler if model else None,
                       policy=FakePolicy() if model else None, sleep=no_sleep)


@contextmanager
def live_client(runtime: LiveRuntime):
    app = create_app(runtime.settings, live_runtime=runtime)
    with TestClient(app) as client:
        yield client


class Recorder:
    """Receives events, schema-checks every one, and applies the stream semantics."""

    def __init__(self, ws):
        self.ws = ws
        self.events: list[dict] = []
        self.validator = StreamValidator()

    def next(self, timeout: float = 10.0) -> dict:
        async def receive():
            with anyio.fail_after(timeout):  # a hung pipeline fails the test instead of CI
                return await self.ws._send_rx.receive()

        message = self.ws.portal.call(receive)
        if message["type"] == "websocket.close":
            raise WebSocketDisconnect(message.get("code", 1000))
        data = json.loads(message["text"])
        schema_validator("server-event.schema.json").validate(data)
        if data["type"] == "session.reset":
            self.validator = StreamValidator()
        assert self.validator.check(data) == "accept", data
        self.events.append(data)
        return data

    def until(self, predicate, limit: int = 500) -> dict:
        for _ in range(limit):
            event = self.next()
            if predicate(event):
                return event
        raise AssertionError("expected event not received")

    def until_type(self, kind: str, **payload) -> dict:
        return self.until(lambda e: e["type"] == kind and all(e["payload"].get(k) == v for k, v in payload.items()))

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]

    def of(self, kind: str) -> list[dict]:
        return [e for e in self.events if e["type"] == kind]


def send_frames(ws, count: int, frame: bytes = FRAME) -> None:
    for _ in range(count):
        ws.send_bytes(frame)
