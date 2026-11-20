"""Test-only model-side fakes: scheduler, scorer, bounded worker and score policy.

These implement the ports in backend/app/audio_ai_ports.py with synthetic vectors.
They are never imported by production code.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable

from backend.app.audio_ai_ports import AudioWindow, PcmFrame, RenderCandidate, ScoredWindow, WindowNotice
from backend.app.config import Settings

LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")
VISIBLE = ("angry", "disgusted", "fearful", "happy", "sad", "surprised")
WINDOW, HOP = 32000, 16000


def vector(**values: float) -> dict[str, float]:
    rest = (1 - sum(values.values())) / (len(LABELS) - len(values))
    return {label: values.get(label, rest) for label in LABELS}


ANGRY = vector(angry=0.7, neutral=0.09)
SAD = vector(sad=0.66, neutral=0.09)
NEUTRAL = vector(neutral=0.78)


class FakeScheduler:
    """Windows [o, o+32000), [o+16000, o+48000), ... per epoch; never pads or joins epochs."""

    def __init__(self) -> None:
        self.state: dict[str, tuple[int, int, bytearray, int]] = {}
        self.pushed: list[PcmFrame] = []

    def begin_epoch(self, session_id: str, epoch: int, first_sample: int) -> None:
        self.state[session_id] = (epoch, first_sample, bytearray(), first_sample)

    def end_session(self, session_id: str) -> None:
        self.state.pop(session_id, None)

    def push(self, frame: PcmFrame) -> list[AudioWindow]:
        self.pushed.append(frame)
        epoch, origin, buf, next_start = self.state[frame.session_id]
        assert frame.epoch == epoch and frame.start_sample == origin + len(buf) // 2
        buf.extend(frame.pcm_s16le)
        out = []
        while origin + len(buf) // 2 >= next_start + WINDOW:
            offset = (next_start - origin) * 2
            out.append(AudioWindow(frame.session_id, epoch, next_start, next_start + WINDOW,
                                   bytes(buf[offset:offset + WINDOW * 2])))
            next_start += HOP
        self.state[frame.session_id] = (epoch, origin, buf, next_start)
        return out


class FakeScorer:
    def __init__(self, scores: Callable[[AudioWindow], dict[str, float]] = lambda w: ANGRY):
        self.scores = scores
        self.loads = 0

    def load(self) -> None:
        self.loads += 1

    def score(self, window: AudioWindow) -> ScoredWindow:
        return ScoredWindow(window.session_id, window.epoch, window.start_sample, window.end_sample,
                            "probability_like", self.scores(window))


class FakeWorker:
    """Single-runner bounded worker. `gate` (if set) blocks each inference until released."""

    def __init__(self, scorer: FakeScorer, *, max_pending: int = 2, fail_load: bool = False,
                 fail_scoring: bool = False):
        self.scorer = scorer
        self.max_pending = max_pending
        self.fail_load = fail_load
        self.fail_scoring = fail_scoring
        self.pending: deque[tuple[AudioWindow, float]] = deque()
        self.out: asyncio.Queue[WindowNotice] = asyncio.Queue()
        self.wake = asyncio.Event()
        self.gate: asyncio.Event | None = None
        self.offered = 0
        self.discards: list[tuple[str, int | None]] = []
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.fail_load:
            raise RuntimeError("load failed")
        self.scorer.load()
        self.task = asyncio.create_task(self._run())

    def _notice(self, window, kind, enqueued, started=None, scored=None) -> WindowNotice:
        return WindowNotice(window.session_id, window.epoch, window.start_sample, window.end_sample, kind,
                            enqueued, time.monotonic() * 1000, started, scored)

    def offer(self, window: AudioWindow) -> None:
        self.offered += 1
        if len(self.pending) >= self.max_pending:
            old, enqueued = self.pending.popleft()
            self.out.put_nowait(self._notice(old, "dropped", enqueued))
        self.pending.append((window, time.monotonic() * 1000))
        self.wake.set()

    async def _run(self) -> None:
        while True:
            while not self.pending:
                self.wake.clear()
                await self.wake.wait()
            window, enqueued = self.pending.popleft()
            started = time.monotonic() * 1000
            if self.gate is not None:
                await self.gate.wait()
            if self.fail_scoring:
                self.out.put_nowait(self._notice(window, "failed", enqueued, started))
            else:
                self.out.put_nowait(self._notice(window, "scored", enqueued, started, self.scorer.score(window)))
            await asyncio.sleep(0)

    async def results(self):
        while True:
            yield await self.out.get()

    def discard(self, session_id: str, *, epoch: int | None = None) -> None:
        self.discards.append((session_id, epoch))
        self.pending = deque((w, t) for w, t in self.pending
                             if not (w.session_id == session_id and (epoch is None or w.epoch == epoch)))

    async def aclose(self) -> None:
        if self.task:
            self.task.cancel()


class FakePolicy:
    """Simplified PIPELINE classification rules for tests (B-05 owns the real one)."""

    def smooth(self, current, previous, config: Settings):
        if previous is None:
            return dict(current)
        a = config.emotion_smoothing_alpha
        out = {k: a * current[k] + (1 - a) * previous[k] for k in LABELS}
        total = sum(out.values())
        return {k: v / total for k, v in out.items()}

    def classify(self, scores, previous_state, config: Settings):
        ranked = sorted(LABELS, key=lambda k: (-scores[k], LABELS.index(k)))
        top = ranked[0]
        if top not in VISIBLE or scores["neutral"] >= config.emotion_neutral_suppress:
            return None
        p = scores[top]
        if p < config.emotion_faint_support:
            return None
        second = ranked[1]
        secondary = None
        weight = None
        if (second in VISIBLE and p >= config.emotion_visible_support
                and scores[second] >= config.emotion_blend_secondary_min
                and p - scores[second] <= config.emotion_blend_gap_max):
            secondary = second
            weight = scores[second] / (p + scores[second])
        intensity = max(0.0, min(1.0, (p - max(scores[k] for k in LABELS if k != top) + 0.25) / 0.75))
        opacity = 0.14 + (p - 0.25) / 0.17 * 0.16 if p < config.emotion_visible_support else \
            min(0.75, 0.35 + (p - 0.42) / 0.33 * 0.40)
        return RenderCandidate(top, secondary, p, intensity, max(0.01, opacity), weight)
