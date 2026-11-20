"""Local fake of the ElevenLabs realtime STT websocket for adapter tests."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response


class FakeScribe:
    def __init__(
        self,
        script: Callable[["FakeScribe", object], Awaitable[None]] | None = None,
        reject_status: int | None = None,
    ) -> None:
        self.script = script
        self.reject_status = reject_status
        self.path = ""
        self.headers: dict[str, str] = {}
        self.received: list[dict] = []
        self.connections = 0
        self.closed = asyncio.Event()
        self.port = 0

    @property
    def query(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/v1/speech-to-text/realtime"

    def _process_request(self, connection, request):
        self.path = request.path
        self.headers = {k.lower(): v for k, v in request.headers.items()}
        if self.reject_status:
            return Response(self.reject_status, "Rejected", Headers(), b"")
        return None

    async def _handler(self, ws):
        self.connections += 1
        await ws.send(json.dumps({"message_type": "session_started", "session_id": "s1", "config": {}}))

        async def drain():
            try:
                async for raw in ws:
                    self.received.append(json.loads(raw))
            except Exception:
                pass
            finally:
                self.closed.set()

        task = asyncio.ensure_future(drain())
        try:
            if self.script:
                await self.script(self, ws)
            await task
        finally:
            task.cancel()

    @asynccontextmanager
    async def running(self):
        async with serve(self._handler, "127.0.0.1", 0, process_request=self._process_request) as server:
            self.port = server.sockets[0].getsockname()[1]
            yield self


async def send(ws, **msg) -> None:
    await ws.send(json.dumps(msg))
