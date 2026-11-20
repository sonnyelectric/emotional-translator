"""Developer tuning route: model-only scores from local PCM, outside the v1 protocol.

`WS /ws/dev/tune` exists only in live mode (registered by create_app) and only serves a
loopback client whose Origin, when present, is the configured local frontend origin.
It accepts the same binary PCM frames as `/ws/v1/session` (16 kHz mono s16le, 20-100 ms),
cuts them into the same 2 s / 1 s-hop windows, scores them with the loaded
emotion2vec+ Large worker, and streams one JSON message per settled window:

    {"type": "tune.window", "kind": "scored", "start_ms", "end_ms", "scores": {9 raw},
     "smoothed": {9}, "classify": {primary, secondary, support, visual_intensity, opacity,
     blend_weight} | null, "top_label", "latency_ms"}

`smoothed` and `classify` use the same policy functions and settings as the live phrase
engine (EMA across consecutive windows, then classify(smoothed, None, settings)).
Silence-gated, dropped and failed windows are reported with their kind and no scores.

It never contacts Scribe and never emits transcript events of any kind: there is no
transcript in tuning mode. Messages use their own `tune.*` types so no v1 client can
mistake them for session events.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import asdict

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .audio.clock import frame_samples, samples_to_ms
from .audio_ai_ports import PcmFrame, WindowNotice
from .config import Settings

log = logging.getLogger(__name__)

POLICY_CLOSE = 1008
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}
LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")
TUNE_NOTE = "Tuning mode - model only, no transcript"


def thresholds(settings: Settings) -> dict[str, float]:
    return {
        "smoothing_alpha": settings.emotion_smoothing_alpha,
        "visible_support": settings.emotion_visible_support,
        "faint_support": settings.emotion_faint_support,
        "neutral_suppress": settings.emotion_neutral_suppress,
        "blend_secondary_min": settings.emotion_blend_secondary_min,
        "blend_gap_max": settings.emotion_blend_gap_max,
        "hysteresis": settings.emotion_hysteresis,
    }


class TuneConnection:
    def __init__(self, websocket: WebSocket, runtime) -> None:
        self.ws = websocket
        self.runtime = runtime
        self.settings: Settings = runtime.settings
        self.session_id = f"tune-{uuid.uuid4().hex[:12]}"
        self.scheduler = runtime.scheduler_factory()
        self.started = False
        self.next_sample = 0
        self.previous: tuple[int, dict[str, float]] | None = None
        self.outbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.windows = 0
        self.warned: set[str] = set()

    def send(self, message: dict) -> None:
        self.outbox.put_nowait(json.dumps(message, separators=(",", ":"), allow_nan=False))

    def hello(self) -> None:
        self.send({"type": "tune.hello", "note": TUNE_NOTE, "model_state": self.runtime.model_state,
                   "model_id": self.settings.emotion_model_id, "thresholds": thresholds(self.settings),
                   "window_ms": 2000, "hop_ms": 1000, "sample_rate": 16000})

    # ---- inbound audio -------------------------------------------------------------
    def on_bytes(self, data: bytes) -> None:
        samples = frame_samples(data)
        if samples is None:
            self.warn_once("INVALID_AUDIO_FRAME")
            return
        if not self.runtime.model_usable:
            self.warn_once("MODEL_NOT_READY")  # frames are dropped until the model is ready
            return
        if not self.started:
            self.scheduler.begin_epoch(self.session_id, 1, 0)
            self.started = True
        start, end = self.next_sample, self.next_sample + samples
        self.next_sample = end
        for window in self.scheduler.push(PcmFrame(self.session_id, 1, start, end, data)):
            self.runtime.worker.offer(window)

    def on_text(self, raw: str) -> None:
        with contextlib.suppress(ValueError):
            if json.loads(raw).get("type") == "tune.reset":
                self.runtime.worker.discard(self.session_id)
                self.started, self.next_sample, self.previous = False, 0, None
                self.send({"type": "tune.reset"})
                return
        self.send({"type": "tune.warning", "code": "UNKNOWN_COMMAND"})

    def warn_once(self, code: str) -> None:
        if code not in self.warned:
            self.warned.add(code)
            self.send({"type": "tune.warning", "code": code, "model_state": self.runtime.model_state})

    def on_model_state(self, state: str) -> None:
        self.warned.discard("MODEL_NOT_READY")
        self.send({"type": "tune.model", "model_state": state})

    # ---- results from the shared worker -----------------------------------------
    def on_notice(self, notice: WindowNotice) -> None:
        message = {"type": "tune.window", "kind": notice.kind,
                   "start_ms": samples_to_ms(notice.start_sample), "end_ms": samples_to_ms(notice.end_sample),
                   "latency_ms": round(notice.settled_at_ms - notice.enqueued_at_ms, 1)}
        if notice.started_at_ms is not None:
            message["model_ms"] = round(notice.settled_at_ms - notice.started_at_ms, 1)
        if notice.kind == "scored" and notice.scored is not None:
            raw = {k: float(notice.scored.scores[k]) for k in LABELS}
            previous = None
            if self.previous and notice.start_sample == self.previous[0] + 16000:
                previous = self.previous[1]
            policy = self.runtime.policy
            smoothed = {k: float(v) for k, v in policy.smooth(raw, previous, self.settings).items()}
            self.previous = (notice.start_sample, smoothed)
            candidate = policy.classify(smoothed, None, self.settings)
            message.update({
                "scores": raw,
                "smoothed": smoothed,
                "top_label": max(LABELS, key=lambda k: raw[k]),
                "classify": asdict(candidate) if candidate is not None else None,
            })
            self.windows += 1
        self.send(message)

    async def run(self) -> None:
        self.runtime.tune_sinks[self.session_id] = self
        sender = asyncio.create_task(self._sender())
        receiver = asyncio.create_task(self._receiver())
        try:
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.runtime.tune_sinks.pop(self.session_id, None)
            with contextlib.suppress(Exception):
                self.runtime.worker.discard(self.session_id)
            with contextlib.suppress(Exception):
                self.scheduler.end_session(self.session_id)
            for task in (sender, receiver):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def _sender(self) -> None:
        while True:
            item = await self.outbox.get()
            if item is None:
                return
            await self.ws.send_text(item)

    async def _receiver(self) -> None:
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    self.on_bytes(message["bytes"])
                elif message.get("text") is not None:
                    self.on_text(message["text"])


async def tune_endpoint(websocket: WebSocket) -> None:
    app = websocket.app
    settings: Settings = app.state.settings
    origin = websocket.headers.get("origin")
    client_host = websocket.client.host if websocket.client else None
    if (origin is not None and origin != settings.allowed_origin) or client_host not in LOOPBACK:
        await websocket.close(code=POLICY_CLOSE)
        return
    runtime = app.state.live_runtime
    await websocket.accept()
    if runtime is None or not runtime.emotion_ready:
        await websocket.send_text(json.dumps({"type": "tune.error", "code": "MODEL_UNAVAILABLE",
                                              "message": "The emotion model runtime is not installed or failed."}))
        await websocket.close(code=1000)
        return
    connection = TuneConnection(websocket, runtime)
    connection.hello()
    await connection.run()
