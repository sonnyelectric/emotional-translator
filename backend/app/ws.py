"""Local session WebSocket: origin, command and frame validation, state transitions (A-owned)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from .schemas import ClientCommand, parse_command
from .session import ERROR_MESSAGES, Emitter, LiveRuntime, LiveSession, new_session_id

log = logging.getLogger(__name__)

MAX_COMMAND_CHARS = 4096
POLICY_CLOSE = 1008
LEGAL = {
    "session.start": {"unbound", "idle"},
    "session.pause": {"listening"},
    "session.resume": {"paused"},
    "session.stop": {"connecting", "listening", "paused"},
    "session.reset": {"unbound", "idle", "stopped", "error"},
}


class Connection:
    def __init__(self, websocket: WebSocket, runtime: LiveRuntime | None, live_mode: bool):
        self.ws = websocket
        self.runtime = runtime
        self.live_mode = live_mode
        self.outbox: asyncio.Queue[str | int] = asyncio.Queue()
        self.emitter: Emitter | None = None
        self.session: LiveSession | None = None
        self.local_state = "unbound"  # used when no LiveSession exists

    @property
    def state(self) -> str:
        return self.session.state if self.session else self.local_state

    def send(self, text: str) -> None:
        self.outbox.put_nowait(text)

    def close(self, code: int) -> None:
        self.outbox.put_nowait(code)

    def bind(self) -> Emitter:
        self.emitter = Emitter(new_session_id(), self.send)
        return self.emitter

    async def run(self) -> None:
        sender = asyncio.create_task(self._sender())
        receiver = asyncio.create_task(self._receiver())
        try:
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sender, receiver):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if self.session is not None:
                await self.session.cleanup()

    async def _sender(self) -> None:
        while True:
            item = await self.outbox.get()
            if isinstance(item, int):
                with contextlib.suppress(Exception):
                    await self.ws.close(code=item)
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

    # ---- inbound -------------------------------------------------------------
    def on_bytes(self, data: bytes) -> None:
        if self.emitter is None:
            self.close(POLICY_CLOSE)  # audio before initialization
            return
        if self.session is None:
            code = "AUDIO_NOT_ACCEPTED"
        else:
            code = self.session.on_audio(data)
        if code is not None:
            self._audio_warning(code)

    def _audio_warning(self, code: str) -> None:
        # One warning per state period, so in-flight frames after Pause do not spam.
        session = self.session
        marker = (code, self.state)
        if session is not None:
            if session.audio_warned_state == marker:
                return
            session.audio_warned_state = marker
            session.warn(code)
        elif self.emitter is not None:
            self.emitter.emit("session.warning", {"code": code, "message": "Audio is not accepted now.",
                                                  "recoverable": True})

    def on_text(self, raw: str) -> None:
        command = None
        if len(raw) <= MAX_COMMAND_CHARS:
            with contextlib.suppress(ValueError, ValidationError):
                command = parse_command(raw)
        if command is None:
            self._reject("INVALID_COMMAND")
            return
        if not isinstance(command, ClientCommand):
            log.warning("Ignored unknown v1 command type")
            return
        if self.state not in LEGAL[command.type]:
            self._reject("INVALID_STATE")
            return
        getattr(self, "_" + command.type.split(".")[1])()

    def _reject(self, code: str) -> None:
        if self.emitter is None:
            self.close(POLICY_CLOSE)
        elif self.session is not None:
            self.session.warn(code)
        else:
            self.emitter.emit("session.warning", {"code": code, "message": f"Command rejected ({code}).",
                                                  "recoverable": True})

    # ---- commands --------------------------------------------------------------
    def _start(self) -> None:
        emitter = self.emitter if self.local_state == "idle" else self.bind()
        runtime = self.runtime
        error = None
        if not self.live_mode or runtime is None:
            error = "LIVE_NOT_CONFIGURED"
        elif runtime.setup_error:
            error = runtime.setup_error
        if error is None:
            session = LiveSession(runtime, emitter, self.close)
            if runtime.acquire(session):
                self.session = session
                session.start()
                return
            error = "LIVE_SESSION_BUSY"
        # Open the session scope with a status first, as in the s-failed server example.
        model = runtime.model_state if runtime else "failed"
        emitter.emit("session.status", {"state": "connecting", "mode": "live", "scribe": "connecting",
                                        "emotion_model": model, "detail": None})
        emitter.emit("session.error", {"code": error, "message": ERROR_MESSAGES[error], "recoverable": False})
        emitter.emit("session.status", {"state": "error", "mode": "live", "scribe": "failed",
                                        "emotion_model": runtime.model_state if runtime else "failed",
                                        "detail": "Live transcription could not start."})
        self.local_state = "error"
        self.close(1000)

    def _pause(self) -> None:
        self.session.pause()

    def _resume(self) -> None:
        self.session.resume()

    def _stop(self) -> None:
        self.session.stop()

    def _reset(self) -> None:
        if self.session is not None:
            asyncio.get_running_loop().create_task(self.session.cleanup())
            self.session = None
        emitter = self.bind()
        emitter.emit("session.reset", {})
        model = self.runtime.model_state if self.runtime and self.live_mode else "failed"
        emitter.emit("session.status", {"state": "idle", "mode": "live", "scribe": "disconnected",
                                        "emotion_model": model, "detail": None})
        self.local_state = "idle"


async def session_endpoint(websocket: WebSocket) -> None:
    app = websocket.app
    origin = websocket.headers.get("origin")
    # Browsers always send Origin; reject a foreign one before accepting the upgrade.
    if origin is not None and origin != app.state.settings.allowed_origin:
        await websocket.close(code=POLICY_CLOSE)
        return
    await websocket.accept()
    connection = Connection(websocket, app.state.live_runtime, app.state.settings.mode == "live")
    await connection.run()
