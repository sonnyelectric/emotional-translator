"""Bounded, single-flight emotion worker (B-05)."""

from __future__ import annotations

import asyncio
import time
from array import array
from collections import deque
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..audio_ai_ports import AudioWindow, ModelScorer, WindowNotice

# Silence gate: RMS of the whole window below this (full scale = 1.0) is settled
# without inference. 0.003 is about -50 dBFS. Tune against measured room noise.
SILENCE_RMS = 0.003


def window_rms(pcm_s16le: bytes) -> float:
    a = array("h")
    a.frombytes(pcm_s16le[: len(pcm_s16le) // 2 * 2])
    if not a:
        return 0.0
    return (sum(x * x for x in a) / len(a)) ** 0.5 / 32768.0


def _monotonic_ms() -> float:
    return time.monotonic() * 1000.0


@dataclass
class WorkerStats:
    offered: int = 0
    scored: int = 0
    dropped: int = 0
    silence: int = 0
    failed: int = 0
    discarded: int = 0  # pending items removed by discard()
    stale_results: int = 0  # completions quarantined after discard()
    max_queue_depth: int = 0
    queue_wait_ms: list[float] = field(default_factory=list)
    run_ms: list[float] = field(default_factory=list)


class BoundedEmotionWorker:
    def __init__(
        self,
        scorer: ModelScorer,
        *,
        max_pending: int = 2,
        silence_rms: float = SILENCE_RMS,
        clock_ms: Callable[[], float] = _monotonic_ms,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        self._scorer = scorer
        self._max_pending = max_pending
        self._silence_rms = silence_rms
        self._clock = clock_ms
        self._pending: deque[tuple[AudioWindow, float]] = deque()
        self._running: AudioWindow | None = None
        self._running_discarded = False
        self._wake = asyncio.Event()
        self._out: asyncio.Queue[WindowNotice | None] = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="emotion")
        self._task: asyncio.Task | None = None
        self._closed = False
        self.ready = False
        self.stats = WorkerStats()

    async def start(self) -> None:
        if self._task is not None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._scorer.load)  # raises on failure
        self.ready = True
        self._task = asyncio.create_task(self._run(), name="emotion-worker")

    def offer(self, window: AudioWindow) -> None:
        if self._closed:
            return
        now = self._clock()
        self.stats.offered += 1
        if len(self._pending) >= self._max_pending:
            old, t0 = self._pending.popleft()  # evict oldest not-yet-started
            self.stats.dropped += 1
            self._emit(old, "dropped", t0, now)
        self._pending.append((window, now))
        self.stats.max_queue_depth = max(self.stats.max_queue_depth, len(self._pending))
        self._wake.set()

    def results(self) -> AsyncIterator[WindowNotice]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[WindowNotice]:
        while True:
            item = await self._out.get()
            if item is None:
                return
            yield item

    def discard(self, session_id: str, *, epoch: int | None = None) -> None:
        def hit(w: AudioWindow) -> bool:
            return w.session_id == session_id and (epoch is None or w.epoch == epoch)

        keep = deque(x for x in self._pending if not hit(x[0]))
        self.stats.discarded += len(self._pending) - len(keep)
        self._pending = keep
        if self._running is not None and hit(self._running):
            self._running_discarded = True  # uninterruptible call: quarantine its result

    async def aclose(self) -> None:
        self._closed = True
        self._pending.clear()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._out.put_nowait(None)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _emit(self, w: AudioWindow, kind: str, enq: float, settled: float,
              started: float | None = None, scored=None) -> None:
        self._out.put_nowait(WindowNotice(
            w.session_id, w.epoch, w.start_sample, w.end_sample, kind,  # type: ignore[arg-type]
            enq, settled, started, scored))

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            if not self._pending:
                self._wake.clear()
                await self._wake.wait()
                continue
            window, enq = self._pending.popleft()
            if window_rms(window.pcm_s16le) < self._silence_rms:
                self.stats.silence += 1
                self._emit(window, "silence", enq, self._clock())
                await asyncio.sleep(0)
                continue
            self._running, self._running_discarded = window, False
            started = self._clock()
            self.stats.queue_wait_ms.append(started - enq)
            try:
                scored = await loop.run_in_executor(self._executor, self._scorer.score, window)
                err = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # model/unsupported-score errors
                scored, err = None, exc
            settled = self._clock()
            self.stats.run_ms.append(settled - started)
            quarantined = self._running_discarded
            self._running = None
            if quarantined:
                self.stats.stale_results += 1
            elif err is not None:
                self.stats.failed += 1
                self._emit(window, "failed", enq, settled, started)
            else:
                self.stats.scored += 1
                self._emit(window, "scored", enq, settled, started, scored)
