"""Overlap-weighted phrase grouping and annotation lifecycle (A-owned).

Policy (decisions recorded here; see also the A-04 handoff):
- Windows and words share the session sample clock; a window only contributes to
  words of its own epoch.
- Word score = sum(w_i * s_i) / sum(w_i), with w_i = overlap/word_duration *
  (1 - 0.25 * min(2, |window_mid - word_mid| / 1000 ms)). Unusable windows weigh 0.
- Groups split at word-final punctuation, pauses > PHRASE_GAP_MS, and a sustained
  (>= 2 adjacent words) change of the classified cue.
- A group is decided, and its annotation first emitted, once every window that can
  overlap it has settled (or the wall deadline passes). Anchors are therefore a pure
  function of inputs and do not depend on model-first vs timed-first arrival.
- A group needs evidence on >= 50% of its word duration to carry a cloud.
- Neutral/other/unknown (policy returns None) leaves the phrase plain.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..audio.clock import samples_to_ms
from ..audio_ai_ports import RenderCandidate, ScorePolicy, ScoredWindow, WindowNotice
from ..config import Settings
from ..schemas import PALETTE
from .segments import TimedSegment, TimedWord

Event = tuple[str, dict]
LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")
PUNCTUATION = (".", ",", "!", "?", ";", ":", "…", "—", "–")
WINDOW_SAMPLES = 32000
HOP_SAMPLES = 16000
MIN_COVERAGE = 0.5
SUPPRESSED = "_suppressed"


def valid_scores(scores: Mapping[str, float]) -> bool:
    try:
        return set(scores) == set(LABELS) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 1
            for v in scores.values())
    except TypeError:
        return False


def recency(window_mid: float, word_mid: float) -> float:
    """Initial PIPELINE recency factor on millisecond midpoints."""
    return 1 - 0.25 * min(2.0, abs(window_mid - word_mid) / 16 / 1000)


def word_vector(word: TimedWord, windows: list[tuple[int, int, dict | None]]) -> dict[str, float] | None:
    """Weighted mean of usable window vectors overlapping a word, or None without evidence."""
    duration = word.end_sample - word.start_sample
    word_mid = (word.start_sample + word.end_sample) / 2
    total = 0.0
    acc = dict.fromkeys(LABELS, 0.0)
    for start, end, scores in windows:
        overlap = min(end, word.end_sample) - max(start, word.start_sample)
        if overlap <= 0 or scores is None:
            continue
        weight = overlap / duration * recency((start + end) / 2, word_mid)
        if weight <= 0:
            continue
        total += weight
        for label in LABELS:
            acc[label] += weight * scores[label]
    if total <= 0:
        return None
    return {label: value / total for label, value in acc.items()}


def phrase_vector(words: list[TimedWord], vectors: list[dict | None]) -> tuple[dict | None, float]:
    """Duration-weighted mean of covered words (each word counted once) and coverage."""
    total = sum(w.end_sample - w.start_sample for w in words)
    covered = 0
    acc = dict.fromkeys(LABELS, 0.0)
    for word, vector in zip(words, vectors, strict=True):
        if vector is None:
            continue
        duration = word.end_sample - word.start_sample
        covered += duration
        for label in LABELS:
            acc[label] += duration * vector[label]
    if not covered:
        return None, 0.0
    return {label: value / covered for label, value in acc.items()}, covered / total


@dataclass
class EpochWindows:
    origin: int
    audio_end: int
    closed: bool = False
    settled: dict[int, tuple[int, int, dict | None]] = field(default_factory=dict)
    previous: tuple[int, Mapping[str, float]] | None = None


@dataclass
class Phrase:
    annotation_id: str
    first: int
    last: int
    revision: int = 0
    visible: bool = False
    final: bool = False
    payload: dict | None = None


@dataclass
class SegmentState:
    segment: TimedSegment
    deadline: float
    decided_until: int = 0  # words [0, decided_until) belong to decided groups
    phrases: list[Phrase] = field(default_factory=list)
    final: bool = False


class PhraseEngine:
    def __init__(self, settings: Settings, policy: ScorePolicy, *, now: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.policy = policy
        self.now = now
        self.epochs: dict[int, EpochWindows] = {}
        self.segments: list[SegmentState] = []
        self.next_annotation = 1
        self.counters: dict[str, int] = {}
        self.gap_samples = settings.phrase_gap_ms * 16

    def _count(self, name: str, n: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + n

    # ---- audio and window inputs -------------------------------------------------
    def begin_epoch(self, epoch: int, origin: int) -> None:
        self.epochs[epoch] = EpochWindows(origin, origin)

    def extend_epoch(self, epoch: int, end_sample: int) -> None:
        state = self.epochs.get(epoch)
        if state:
            state.audio_end = max(state.audio_end, end_sample)

    def close_epoch(self, epoch: int) -> list[Event]:
        state = self.epochs.get(epoch)
        if state is None or state.closed:
            return []
        state.closed = True
        return self.evaluate(epoch)

    def window_unusable(self, epoch: int, start: int, end: int) -> list[Event]:
        """A window was produced but will carry no scores (model unavailable, dropped)."""
        return self._settle(epoch, start, end, None)

    def window_notice(self, notice: WindowNotice) -> list[Event]:
        scores = None
        if notice.kind == "scored" and notice.scored is not None:
            scores = self._smooth(notice.epoch, notice.scored)
        return self._settle(notice.epoch, notice.start_sample, notice.end_sample, scores)

    def _smooth(self, epoch: int, scored: ScoredWindow) -> dict | None:
        if not valid_scores(scored.scores):
            self._count("invalid_scores")
            return None
        state = self.epochs.get(epoch)
        previous = None
        if state and state.previous and scored.start_sample == state.previous[0] + HOP_SAMPLES:
            previous = state.previous[1]
        smoothed = dict(self.policy.smooth(dict(scored.scores), previous, self.settings))
        if not valid_scores(smoothed):
            self._count("invalid_scores")
            return None
        if state:
            state.previous = (scored.start_sample, smoothed)
        return smoothed

    def _settle(self, epoch: int, start: int, end: int, scores: dict | None) -> list[Event]:
        state = self.epochs.get(epoch)
        if state is None:
            self._count("windows_unknown_epoch")
            return []
        if any(s.segment.epoch == epoch and s.final and s.segment.words[0].start_sample < end
               and s.segment.words[-1].end_sample > start for s in self.segments):
            self._count("late_results_discarded")
        state.settled[start] = (start, end, scores)
        return self.evaluate(epoch)

    # ---- segment inputs ------------------------------------------------------------
    def add_segment(self, segment: TimedSegment) -> list[Event]:
        deadline = self.now() + (self.settings.phrase_lookahead_ms + self.settings.phrase_pending_timeout_ms) / 1000
        self.segments.append(SegmentState(segment, deadline))
        return self.evaluate(segment.epoch)

    def tick(self) -> list[Event]:
        events: list[Event] = []
        now = self.now()
        for state in self.segments:
            if not state.final and now >= state.deadline:
                self._count("deadline_finalizations")
                events += self._evaluate_segment(state, force=True)
        return events

    def finalize_all(self) -> list[Event]:
        events: list[Event] = []
        for state in self.segments:
            if not state.final:
                events += self._evaluate_segment(state, force=True)
        return events

    def pending_segments(self) -> int:
        return sum(not s.final for s in self.segments)

    # ---- evaluation ----------------------------------------------------------------
    def evaluate(self, epoch: int) -> list[Event]:
        events: list[Event] = []
        for state in self.segments:
            if not state.final and state.segment.epoch == epoch:
                events += self._evaluate_segment(state)
        return events

    def _complete(self, epoch: int, start: int, end: int) -> bool:
        """Have all windows that can overlap [start, end) settled?"""
        state = self.epochs.get(epoch)
        if state is None:
            return True
        k = max(0, math.floor((start - WINDOW_SAMPLES - state.origin) / HOP_SAMPLES) + 1)
        while True:
            s = state.origin + k * HOP_SAMPLES
            if s >= end:
                return True
            if s + WINDOW_SAMPLES > start:
                if s + WINDOW_SAMPLES > state.audio_end:
                    return state.closed  # not produced yet; never will be once closed
                if s not in state.settled:
                    return False
            k += 1

    def _label(self, vector: dict | None) -> str | None:
        if vector is None:
            return None
        candidate = self.policy.classify(vector, None, self.settings)
        return candidate.primary if candidate else SUPPRESSED

    def _coarse_end(self, words: list[TimedWord], begin: int) -> int:
        """Last index of the punctuation/pause group starting at `begin`."""
        for i in range(begin, len(words) - 1):
            if words[i].text.endswith(PUNCTUATION) or (
                    words[i + 1].start_sample - words[i].end_sample > self.gap_samples):
                return i
        return len(words) - 1

    def _cue_split(self, vectors: list[dict | None], first: int, last: int) -> list[tuple[int, int]]:
        """Split [first, last] where a different cue holds for >= 2 adjacent words."""
        labels = [self._label(vectors[i]) for i in range(first, last + 1)]
        groups: list[tuple[int, int]] = []
        current = None
        start = first
        for offset, label in enumerate(labels):
            if label is None:
                continue
            if current is None:
                current = label
                continue
            following = labels[offset + 1] if offset + 1 < len(labels) else None
            if label != current and following == label:
                groups.append((start, first + offset - 1))
                start = first + offset
                current = label
        groups.append((start, last))
        return groups

    def _evaluate_segment(self, state: SegmentState, force: bool = False) -> list[Event]:
        segment = state.segment
        words = segment.words
        epoch_state = self.epochs.get(segment.epoch)
        windows = list(epoch_state.settled.values()) if epoch_state else []
        vectors = [word_vector(w, windows) for w in words]
        events: list[Event] = []
        while state.decided_until < len(words):
            first = state.decided_until
            last = self._coarse_end(words, first)
            # Decide only with complete evidence for the whole coarse group, so cue splits
            # and anchors do not depend on arrival order.
            if not force and not self._complete(segment.epoch, words[first].start_sample, words[last].end_sample):
                break
            for group_first, group_last in self._cue_split(vectors, first, last):
                events += self._decide(state, group_first, group_last, vectors)
            state.decided_until = last + 1
        if state.decided_until >= len(words):
            state.final = True
        return events

    def _decide(self, state: SegmentState, first: int, last: int, vectors: list[dict | None]) -> list[Event]:
        words = state.segment.words[first:last + 1]
        vector, coverage = phrase_vector(words, vectors[first:last + 1])
        if vector is None or coverage < MIN_COVERAGE:
            self._count("phrases_without_evidence")
            return []
        candidate = self.policy.classify(vector, None, self.settings)
        if candidate is None:
            self._count("phrases_suppressed")
            return []
        payload = self._payload(state.segment, first, last, vector, candidate)
        if payload is None:
            return []
        phrase = Phrase(f"a-{state.segment.segment_id}-{self.next_annotation}", first, last)
        self.next_annotation += 1
        state.phrases.append(phrase)
        payload["annotation_id"] = phrase.annotation_id
        payload["revision"] = 1
        phrase.revision = 2
        phrase.visible = phrase.final = True
        phrase.payload = payload
        self._count("annotations")
        return [("emotion.updated", payload),
                ("emotion.finalized", {"annotation_id": phrase.annotation_id, "revision": 2})]

    def _payload(self, segment: TimedSegment, first: int, last: int, vector: dict,
                 candidate: RenderCandidate) -> dict | None:
        if candidate.primary not in PALETTE or candidate.secondary == candidate.primary:
            self._count("invalid_candidates")
            return None
        scores = {label: round(min(1.0, max(0.0, vector[label])), 4) for label in LABELS}
        blend = None
        if candidate.secondary is not None:
            if candidate.secondary not in PALETTE:
                self._count("invalid_candidates")
                return None
            weight = candidate.blend_weight
            if weight is None:
                p, s = vector[candidate.primary], vector[candidate.secondary]
                weight = s / (p + s) if p + s > 0 else 0.0
            weight = round(min(0.5, weight), 4)
            if weight <= 0:
                return None
            blend = {"secondary": candidate.secondary, "weight": weight}
        shape, color = PALETTE[candidate.primary]
        first_word, last_word = segment.words[first], segment.words[last]
        return {
            "segment_id": segment.segment_id,
            "start_word_id": first_word.word_id,
            "end_word_id": last_word.word_id,
            "start_ms": samples_to_ms(first_word.start_sample),
            "end_ms": samples_to_ms(last_word.end_sample),
            "state": "draft",
            "primary": candidate.primary,
            "secondary": candidate.secondary if blend else None,
            "scores": scores,
            "support": scores[candidate.primary],
            "visual_intensity": round(min(1.0, max(0.0, candidate.visual_intensity)), 4),
            "opacity": round(min(1.0, max(0.01, candidate.opacity)), 4),
            "shape": shape,
            "color": color,
            "blend": blend,
        }
