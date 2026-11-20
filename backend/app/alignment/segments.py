"""Partial/commit/timed bookkeeping and word timing on the session clock (A-owned).

Scribe word times arrive from B's adapter as provider-relative integer samples
(TimedToken). This module adds the epoch origin, validates the result against
audio that was actually sent on that epoch, and assigns stable word IDs. When the
timestamp basis is unknown or the mapping cannot be resolved it keeps the stable
text and emits an alignment warning instead of guessing.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from ..audio.clock import Epoch, samples_to_ms
from ..audio_ai_ports import ScribeNotice
from ..replay import normalize_text

log = logging.getLogger(__name__)

Event = tuple[str, dict]
# Rounding seconds -> samples may land a word end at most this far past the sent audio.
END_TOLERANCE_SAMPLES = 16

WARNINGS = {
    "ALIGNMENT_TIMESTAMPS_MISSING": "Word timing is unavailable for this segment.",
    "ALIGNMENT_TIMESTAMP_MISMATCH": "Word timing did not match the transcript or the sent audio.",
    "ALIGNMENT_BASIS_UNKNOWN": "Word timing has an unverified clock basis, so no cloud is placed.",
}


@dataclass(frozen=True)
class TimedWord:
    word_id: str
    text: str
    start_sample: int
    end_sample: int


@dataclass
class TimedSegment:
    segment_id: str
    epoch: int
    words: list[TimedWord]


@dataclass
class PendingCommit:
    segment_id: str
    text: str
    language_code: str | None
    provider_key: str | None


@dataclass
class SegmentTracker:
    timestamp_basis: str = "provider"
    next_segment: int = 1
    next_partial: int = 1
    partial_id: str | None = None
    partial_text: str | None = None
    pending: dict[int, deque[PendingCommit]] = field(default_factory=dict)
    seen_keys: dict[int, set[str]] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def _count(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    def pending_count(self, epoch: int | None = None) -> int:
        if epoch is not None:
            return len(self.pending.get(epoch, ()))
        return sum(len(queue) for queue in self.pending.values())

    def on_partial(self, notice: ScribeNotice) -> list[Event]:
        text = notice.text or ""
        if not text.strip() or text == self.partial_text:
            return []
        if self.partial_id is None:
            self.partial_id = f"p-{self.next_partial}"
            self.next_partial += 1
        self.partial_text = text
        return [("transcript.partial",
                 {"partial_id": self.partial_id, "text": text, "language_code": notice.language_code})]

    def clear_partial(self) -> list[Event]:
        """Clear stale provisional text when its epoch is lost (protocol: empty string)."""
        if self.partial_id is None:
            return []
        events = [("transcript.partial", {"partial_id": self.partial_id, "text": "", "language_code": None})]
        self.partial_id = self.partial_text = None
        return events

    def on_commit(self, notice: ScribeNotice) -> list[Event]:
        text = (notice.text or "").strip()
        if not text:
            self._count("empty_commit")
            return self.clear_partial()
        key = notice.provider_commit_key
        if key is not None:
            keys = self.seen_keys.setdefault(notice.epoch, set())
            if key in keys:
                self._count("duplicate_commit")
                return []
            keys.add(key)
        segment_id = f"seg-{self.next_segment}"
        self.next_segment += 1
        self.partial_id = self.partial_text = None
        self.pending.setdefault(notice.epoch, deque()).append(
            PendingCommit(segment_id, text, notice.language_code, key))
        return [("transcript.committed", {"segment_id": segment_id, "text": text,
                                          "timing_state": "pending", "language_code": notice.language_code})]

    def expire_epoch(self, epoch: int) -> list[Event]:
        """The epoch can deliver no more timing: warn for each commit still waiting."""
        queue = self.pending.pop(epoch, deque())
        self.seen_keys.pop(epoch, None)
        return [self._warning(c.segment_id, "ALIGNMENT_TIMESTAMPS_MISSING") for c in queue]

    def _warning(self, segment_id: str, code: str) -> Event:
        self._count(code.lower())
        return ("alignment.warning", {"segment_id": segment_id, "code": code, "message": WARNINGS[code]})

    def on_timed(self, notice: ScribeNotice, epoch: Epoch) -> tuple[list[Event], TimedSegment | None]:
        queue = self.pending.get(notice.epoch)
        if not queue:
            self._count("orphan_timed")  # no commit to attach to; never invent a segment
            return [], None
        commit = None
        if notice.provider_commit_key is not None:
            commit = next((c for c in queue if c.provider_key == notice.provider_commit_key), None)
        if commit is None:
            commit = queue[0]  # validated FIFO: Scribe sends the timed event after its commit
        queue.remove(commit)
        segment_id = commit.segment_id

        if not notice.tokens:
            return [self._warning(segment_id, "ALIGNMENT_TIMESTAMPS_MISSING")], None
        texts = [token.text.strip() for token in notice.tokens]
        if any(not text for text in texts) or normalize_text(" ".join(texts)) != normalize_text(commit.text):
            return [self._warning(segment_id, "ALIGNMENT_TIMESTAMP_MISMATCH")], None

        basis = notice.timestamp_basis
        if basis == "unknown" and self.timestamp_basis == "connection":
            basis = "connection"
        if epoch.origin is None:
            return [self._warning(segment_id, "ALIGNMENT_TIMESTAMP_MISMATCH")], None
        if basis == "connection":
            base = epoch.origin
        elif basis == "segment" and notice.segment_origin_samples is not None:
            base = epoch.origin + notice.segment_origin_samples
        else:
            return [self._warning(segment_id, "ALIGNMENT_BASIS_UNKNOWN")], None

        sent_end = epoch.sent_end if epoch.sent_end is not None else epoch.origin
        words: list[TimedWord] = []
        previous = None
        for index, (token, text) in enumerate(zip(notice.tokens, texts, strict=True)):
            start, end = base + token.start_sample, base + token.end_sample
            if end > sent_end and end - sent_end <= END_TOLERANCE_SAMPLES:
                end = sent_end
            ordered = previous is None or (start >= previous.start_sample and end >= previous.end_sample)
            if not (epoch.origin <= start < end <= sent_end and ordered):
                return [self._warning(segment_id, "ALIGNMENT_TIMESTAMP_MISMATCH")], None
            previous = TimedWord(f"{segment_id}:w{index}", text, start, end)
            words.append(previous)
        payload = {
            "segment_id": segment_id,
            "language_code": notice.language_code or commit.language_code,
            "words": [{"word_id": w.word_id, "text": w.text, "start_ms": samples_to_ms(w.start_sample),
                       "end_ms": samples_to_ms(w.end_sample)} for w in words],
        }
        return [("transcript.timed", payload)], TimedSegment(segment_id, notice.epoch, words)
