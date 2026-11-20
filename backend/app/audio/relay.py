"""Scribe relay: one bounded writer and one reader per upstream connection (A-owned).

The relay never replays earlier microphone audio. A queue overflow or delivery
failure ends the link; the session then opens a fresh epoch.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable

from ..audio_ai_ports import ScribeNotice, ScribeStream
from .clock import Epoch

log = logging.getLogger(__name__)

# Upstream failure classes (SYNTHESIS BA section). Codes are provider message_type
# values or adapter handshake codes.
PERMANENT_CODES = {
    "auth_error": "SCRIBE_AUTH",
    "quota_exceeded": "SCRIBE_QUOTA",
    "unaccepted_terms": "SCRIBE_TERMS",
    "invalid_request": "SCRIBE_INVALID_REQUEST",
    "http_401": "SCRIBE_AUTH",
    "http_403": "SCRIBE_AUTH",
    "http_402": "SCRIBE_QUOTA",
}
# Our-side bugs: transient once, then fatal.
RETRY_ONCE_CODES = {"commit_throttled", "chunk_size_exceeded", "input_error"}
# Upstream closed during long silence: reconnect without a user-facing warning.
QUIET_CODES = {"insufficient_audio_activity"}

FATAL_MESSAGES = {
    "SCRIBE_AUTH": "Check the backend ElevenLabs credential.",
    "SCRIBE_QUOTA": "The ElevenLabs quota is exhausted. Replay remains available.",
    "SCRIBE_TERMS": "Accept the ElevenLabs terms for this account, then retry.",
    "SCRIBE_INVALID_REQUEST": "Live transcription rejected the request configuration.",
    "SCRIBE_RETRY_EXHAUSTED": "Live transcription could not reconnect. Committed text is preserved.",
    "SCRIBE_INPUT_REJECTED": "Live transcription rejected the audio stream repeatedly.",
    "SCRIBE_FATAL": "Live transcription stopped with an unrecoverable error.",
}


def classify_failure(code: str | None, fatal_hint: bool, retry_once_seen: set[str]) -> str | None:
    """Return a fatal wire code, or None if the failure may be retried."""
    code = code or ""
    if code in PERMANENT_CODES:
        return PERMANENT_CODES[code]
    if code in RETRY_ONCE_CODES:
        if code in retry_once_seen:
            return "SCRIBE_INPUT_REJECTED"
        retry_once_seen.add(code)
        return None
    if fatal_hint:
        return "SCRIBE_FATAL"
    return None


def backoff_delay(attempt: int, base_ms: int, cap_ms: int, rand: Callable[[], float] = random.random) -> float:
    """Exponential backoff with jitter in seconds. attempt starts at 1: 0.5, 1, 2, 4, 4."""
    nominal = min(cap_ms, base_ms * 2 ** (attempt - 1)) / 1000
    return nominal * (0.5 + 0.5 * rand())


class UpstreamLink:
    """A single Scribe connection (= one audio epoch)."""

    def __init__(
        self,
        stream: ScribeStream,
        epoch: Epoch,
        *,
        queue_frames: int,
        on_notice: Callable[[UpstreamLink, ScribeNotice], None],
        on_lost: Callable[[UpstreamLink, str | None, bool], None],
    ) -> None:
        self.stream = stream
        self.epoch = epoch
        self.queue: asyncio.Queue[tuple[int, bytes] | None] = asyncio.Queue(maxsize=queue_frames)
        self._on_notice = on_notice
        self._on_lost = on_lost
        self.lost = False
        self.sent_frames = 0
        self._writer = asyncio.create_task(self._write(), name=f"scribe-writer-{epoch.number}")
        self._reader = asyncio.create_task(self._read(), name=f"scribe-reader-{epoch.number}")

    def offer(self, end_sample: int, pcm: bytes) -> bool:
        """Non-blocking enqueue. False means overflow; the caller must cut the epoch."""
        if self.lost:
            return False
        try:
            self.queue.put_nowait((end_sample, pcm))
        except asyncio.QueueFull:
            return False
        return True

    async def _write(self) -> None:
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    return
                end_sample, pcm = item
                await self.stream.send_pcm(pcm)
                self.epoch.mark_sent(end_sample)
                self.sent_frames += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # delivery lost; never replay old audio
            log.info("Scribe writer stopped: %s", type(exc).__name__)
            self._lose("send_failed", False)

    async def _read(self) -> None:
        try:
            async for notice in self.stream.events():
                if notice.epoch != self.epoch.number:
                    continue  # mis-tagged or stale notice
                if notice.kind in ("transient_error", "fatal_error"):
                    self._lose(notice.code, notice.kind == "fatal_error")
                    return
                self._on_notice(self, notice)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("Scribe reader stopped: %s", type(exc).__name__)
            self._lose("read_failed", False)
            return
        self._lose("closed", False)

    def _lose(self, code: str | None, fatal: bool) -> None:
        if self.lost:
            return
        self.lost = True
        self._on_lost(self, code, fatal)

    async def drain_writes(self, timeout: float) -> None:
        """Let queued audio reach Scribe (used on Stop/Pause) within a bound."""
        if self.lost:
            return
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(None)
        with contextlib.suppress(asyncio.TimeoutError, Exception):
            await asyncio.wait_for(asyncio.shield(self._writer), timeout)

    async def aclose(self) -> None:
        self.lost = True
        self.epoch.closed = True
        for task in (self._writer, self._reader):
            task.cancel()
        for task in (self._writer, self._reader):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.stream.aclose(), 2.0)


async def open_with_retry(
    open_once: Callable[[], Awaitable[ScribeStream]],
    *,
    attempts: int,
    base_ms: int,
    cap_ms: int,
    retry_once_seen: set[str],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    first_delay: bool = False,
) -> tuple[ScribeStream | None, str | None, int]:
    """Try to open upstream. Returns (stream, fatal_code, attempts_used)."""
    for attempt in range(1, attempts + 1):
        if first_delay or attempt > 1:
            await sleep(backoff_delay(attempt, base_ms, cap_ms))
        try:
            return await open_once(), None, attempt
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            fatal = classify_failure(code, bool(getattr(exc, "fatal", False)), retry_once_seen)
            log.info("Scribe open failed (attempt %d): %s", attempt, code or type(exc).__name__)
            if fatal:
                return None, fatal, attempt
    return None, "SCRIBE_RETRY_EXHAUSTED", attempts
