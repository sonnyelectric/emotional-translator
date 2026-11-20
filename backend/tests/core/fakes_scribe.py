"""Test-only Scribe port fakes. No network, no key."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.app.audio_ai_ports import ScribeNotice, TimedToken


class FakeSetupError(Exception):
    def __init__(self, code: str, fatal: bool):
        super().__init__(code)
        self.code = code
        self.fatal = fatal


@dataclass
class Utterance:
    """Emit partial -> commit -> timed once `after_samples` have been received upstream.

    Token times are (text, start_s, end_s) relative to the connection start, converted to
    samples the way B's adapter does: round(seconds * 16000).
    """

    after_samples: int
    text: str
    words: list[tuple[str, float, float]]
    basis: str = "connection"
    segment_origin_samples: int | None = None
    emit_timed: bool = True
    duplicate_timed: bool = False


class FakeScribeStream:
    def __init__(self, adapter: FakeScribeAdapter, epoch: int):
        self.adapter = adapter
        self.epoch = epoch
        self.received = 0
        self.chunks: list[bytes] = []
        self.queue: asyncio.Queue[ScribeNotice | None] = asyncio.Queue()
        self.closed = False
        self.pending = list(adapter.utterances_for(epoch))

    def push(self, kind: str, **kwargs) -> None:
        self.queue.put_nowait(ScribeNotice(epoch=self.epoch, kind=kind, **kwargs))

    async def send_pcm(self, pcm_s16le: bytes) -> None:
        if self.closed:
            raise ConnectionError("closed")
        if self.adapter.send_delay:
            await asyncio.sleep(self.adapter.send_delay)
        self.received += len(pcm_s16le) // 2
        self.chunks.append(pcm_s16le)
        self.adapter.total_samples += len(pcm_s16le) // 2
        while self.pending and self.received >= self.pending[0].after_samples:
            utterance = self.pending.pop(0)
            self.push("partial", text=utterance.text.split()[0], language_code="en")
            self.push("commit", text=utterance.text)
            if utterance.emit_timed:
                tokens = tuple(TimedToken(t, round(s * 16000), round(e * 16000)) for t, s, e in utterance.words)
                for _ in range(2 if utterance.duplicate_timed else 1):
                    self.push("timed", text=utterance.text, language_code="en", tokens=tokens,
                              timestamp_basis=utterance.basis,
                              segment_origin_samples=utterance.segment_origin_samples)
        hook = self.adapter.on_send
        if hook:
            hook(self)

    async def events(self):
        while True:
            notice = await self.queue.get()
            if notice is None:
                return
            yield notice

    async def aclose(self) -> None:
        self.closed = True
        self.queue.put_nowait(None)


@dataclass
class FakeScribeAdapter:
    utterances: list[Utterance] = field(default_factory=list)
    # Per-epoch utterances; if absent, `utterances` applies to the first epoch only.
    by_epoch: dict[int, list[Utterance]] = field(default_factory=dict)
    open_errors: list[Exception] = field(default_factory=list)
    on_send: Callable[[FakeScribeStream], None] | None = None
    send_delay: float = 0.0
    opened: list[int] = field(default_factory=list)
    streams: list[FakeScribeStream] = field(default_factory=list)
    total_samples: int = 0

    def utterances_for(self, epoch: int) -> list[Utterance]:
        if self.by_epoch:
            return self.by_epoch.get(epoch, [])
        return self.utterances if len(self.streams) == 0 else []

    async def open(self, epoch: int) -> FakeScribeStream:
        self.opened.append(epoch)
        if self.open_errors:
            raise self.open_errors.pop(0)
        stream = FakeScribeStream(self, epoch)
        self.streams.append(stream)
        return stream
