"""Partial/commit/timed bookkeeping and word timing on the session clock (A-owned).

Scribe word times arrive from B's adapter as provider-relative integer samples
(TimedToken). This module adds the epoch origin, validates the result against
audio that was actually sent on that epoch, and assigns stable word IDs. When the
timestamp basis is unknown or the mapping cannot be resolved it keeps the stable
text and emits an alignment warning instead of guessing.
"""

from __future__ import annotations

import logging
import unicodedata
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
    # True only for the first commit Scribe sent on this epoch (connection). Plan B for a
    # segment-relative basis: that segment starts at the connection start, so its origin is
    # the epoch origin. Any later segment's origin is unknown and is never guessed.
    first_in_epoch: bool = False


def _loose(text: str) -> str:
    """Matching key: NFC, case-folded, letters and digits only (no punctuation or spaces)."""
    folded = unicodedata.normalize("NFC", text).casefold()
    return "".join(ch for ch in folded if unicodedata.category(ch)[0] in "LN")


def align_words(token_texts: list[str], text: str) -> list[tuple[str, int, int]] | None:
    """Map provider tokens onto the words of `text`, tolerant of case, punctuation, spacing
    and token splits ("o'clock" vs "o", "'", "clock").

    Returns one (word_text, first_token, last_token) per whitespace word of `text`, in order,
    so the joined word texts equal `text` after whitespace normalization. Returns None when
    the letters and digits of the tokens and of `text` differ. A word with no letters or
    digits (a dash) is merged into its neighbour so every word owns at least one token.
    """
    owner: list[int] = []
    for index, token in enumerate(token_texts):
        owner.extend([index] * len(_loose(token)))
    words = text.split()
    keys = [_loose(w) for w in words]
    if not owner or "".join(keys) != "".join(_loose(t) for t in token_texts):
        return None
    merged: list[list] = []  # [text, loose key]
    carry = ""
    for word, key in zip(words, keys, strict=True):
        if not key:
            if merged:
                merged[-1][0] += " " + word
            else:
                carry += word + " "
            continue
        merged.append([carry + word, key])
        carry = ""
    out: list[tuple[str, int, int]] = []
    pos = 0
    for word, key in merged:
        out.append((word, owner[pos], owner[pos + len(key) - 1]))
        pos += len(key)
    return out


@dataclass
class SegmentTracker:
    # Configured basis (Settings.scribe_timestamp_basis): unknown | connection | segment.
    timestamp_basis: str = "unknown"
    next_segment: int = 1
    next_partial: int = 1
    partial_id: str | None = None
    partial_text: str | None = None
    pending: dict[int, deque[PendingCommit]] = field(default_factory=dict)
    seen_keys: dict[int, set[str]] = field(default_factory=dict)
    commits_seen: dict[int, int] = field(default_factory=dict)  # commit notices per epoch
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
        key = notice.provider_commit_key
        if key is not None:
            keys = self.seen_keys.setdefault(notice.epoch, set())
            if key in keys:
                self._count("duplicate_commit")
                return []
            keys.add(key)
        # Count every distinct provider commit, empty ones included: an empty commit may
        # still close a provider segment, so a later commit is no longer the epoch's first.
        first = self.commits_seen.get(notice.epoch, 0) == 0
        self.commits_seen[notice.epoch] = self.commits_seen.get(notice.epoch, 0) + 1
        if not text:
            self._count("empty_commit")
            return self.clear_partial()
        segment_id = f"seg-{self.next_segment}"
        self.next_segment += 1
        self.partial_id = self.partial_text = None
        self.pending.setdefault(notice.epoch, deque()).append(
            PendingCommit(segment_id, text, notice.language_code, key, first_in_epoch=first))
        return [("transcript.committed", {"segment_id": segment_id, "text": text,
                                          "timing_state": "pending", "language_code": notice.language_code})]

    def expire_epoch(self, epoch: int) -> list[Event]:
        """The epoch can deliver no more timing: warn for each commit still waiting."""
        queue = self.pending.pop(epoch, deque())
        self.seen_keys.pop(epoch, None)
        self.commits_seen.pop(epoch, None)
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

        # Guard against provider spacing items (B's adapter should already drop them).
        tokens = [token for token in notice.tokens if token.text.strip()]
        if not tokens:
            return [self._warning(segment_id, "ALIGNMENT_TIMESTAMPS_MISSING")], None
        token_texts = [token.text.strip() for token in tokens]
        # Match the timed words to the committed text loosely. If that fails, try the timed
        # notice's own text, then the tokens' own text: the timed text is what the provider
        # actually timed, so it replaces the committed text instead of dropping the cloud.
        revised_text = None
        aligned = align_words(token_texts, commit.text)
        if aligned is None:
            timed_text = (notice.text or "").strip()
            aligned = align_words(token_texts, timed_text) if timed_text else None
            if aligned is None:
                aligned = align_words(token_texts, " ".join(token_texts))
            if aligned is None:  # tokens with no letters or digits at all
                return [self._warning(segment_id, "ALIGNMENT_TIMESTAMP_MISMATCH")], None
            revised_text = normalize_text(" ".join(word for word, _, _ in aligned))
            self._count("timed_text_revised")

        basis = notice.timestamp_basis
        if basis == "unknown" and self.timestamp_basis in ("connection", "segment"):
            basis = self.timestamp_basis
        if epoch.origin is None:
            return [self._warning(segment_id, "ALIGNMENT_TIMESTAMP_MISMATCH")], None
        if basis == "connection":
            base = epoch.origin
        elif basis == "segment" and notice.segment_origin_samples is not None:
            base = epoch.origin + notice.segment_origin_samples
        elif basis == "segment" and self.timestamp_basis == "segment" and commit.first_in_epoch:
            # Plan B, only when the operator set SCRIBE_TIMESTAMP_BASIS=segment from smoke-test
            # evidence: the first segment of a connection starts at the connection start.
            base = epoch.origin
            self._count("segment_first_in_epoch")
        else:
            return [self._warning(segment_id, "ALIGNMENT_BASIS_UNKNOWN")], None

        sent_end = epoch.sent_end if epoch.sent_end is not None else epoch.origin
        words: list[TimedWord] = []
        previous = None
        for index, (text, first, last) in enumerate(aligned):
            start, end = base + tokens[first].start_sample, base + tokens[last].end_sample
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
        if revised_text is not None:
            payload["text"] = revised_text
        return [("transcript.timed", payload)], TimedSegment(segment_id, notice.epoch, words)
