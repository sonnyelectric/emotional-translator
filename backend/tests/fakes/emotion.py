"""Deterministic test-only ModelScorer (B-02). Never selected by live composition."""

from __future__ import annotations

import threading

from backend.app.audio_ai_ports import AudioWindow, ScoredWindow

LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")

# Vectors copied from shared/fixtures/pipeline_examples.json (probability-like, sum 1).
NEUTRAL = dict(zip(LABELS, (0.02, 0.02, 0.03, 0.04, 0.78, 0.03, 0.04, 0.02, 0.02)))
FAINT_SAD = dict(zip(LABELS, (0.13, 0.05, 0.11, 0.07, 0.20, 0.04, 0.32, 0.06, 0.02)))
STRONG_SAD = dict(zip(LABELS, (0.07, 0.02, 0.06, 0.03, 0.09, 0.03, 0.66, 0.03, 0.01)))
STRONG_ANGRY = dict(zip(LABELS, (0.70, 0.04, 0.04, 0.03, 0.09, 0.02, 0.04, 0.03, 0.01)))
MIXED_ANGER_SAD = dict(zip(LABELS, (0.46, 0.02, 0.03, 0.02, 0.06, 0.02, 0.35, 0.03, 0.01)))


class FakeScorerFailure(RuntimeError):
    """The known, deliberate failure raised by the fake."""


class FakeEmotionScorer:
    """Returns a seeded vector chosen by window.start_sample, else a repeating cycle.

    vectors_by_start: {start_sample: vector}. cycle: default sequence by hop index.
    fail_on: start samples that raise FakeScorerFailure. block_on: start samples
    that wait on ``release`` (a threading.Event); ``entered`` is set when blocked.
    """

    def __init__(self, vectors_by_start=None, *, cycle=(NEUTRAL,), fail_on=(), block_on=(),
                 load_error: Exception | None = None, score_kind="probability_like") -> None:
        self.vectors_by_start = dict(vectors_by_start or {})
        self.cycle = tuple(cycle)
        self.fail_on = set(fail_on)
        self.block_on = set(block_on)
        self.load_error = load_error
        self.score_kind = score_kind
        self.release = threading.Event()
        self.entered = threading.Event()
        self.load_count = 0
        self.calls: list[tuple[str, int, int]] = []  # (session, epoch, start)

    def load(self) -> None:
        if self.load_error:
            raise self.load_error
        self.load_count += 1

    def vector_for(self, start_sample: int) -> dict[str, float]:
        if start_sample in self.vectors_by_start:
            return dict(self.vectors_by_start[start_sample])
        return dict(self.cycle[(start_sample // 16000) % len(self.cycle)])

    def score(self, window: AudioWindow) -> ScoredWindow:
        self.calls.append((window.session_id, window.epoch, window.start_sample))
        if window.start_sample in self.block_on:
            self.entered.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("fake scorer was never released")
        if window.start_sample in self.fail_on:
            raise FakeScorerFailure(f"forced failure at {window.start_sample}")
        return ScoredWindow(window.session_id, window.epoch, window.start_sample,
                            window.end_sample, self.score_kind, self.vector_for(window.start_sample))
