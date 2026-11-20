"""Canonical session audio clock: accepted 16 kHz samples only (A-owned)."""

from __future__ import annotations

from dataclasses import dataclass

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
MIN_FRAME_BYTES = 640  # 20 ms
MAX_FRAME_BYTES = 3200  # 100 ms


def frame_samples(data: bytes) -> int | None:
    """Return the sample count of a legal PCM frame, or None if it must be dropped."""
    size = len(data)
    if size % BYTES_PER_SAMPLE or not MIN_FRAME_BYTES <= size <= MAX_FRAME_BYTES:
        return None
    return size // BYTES_PER_SAMPLE


def samples_to_ms(samples: int) -> float | int:
    """audio_ms = sample_offset * 1000 / 16000; whole numbers stay integers on the wire."""
    ms = samples / 16
    return int(ms) if ms.is_integer() else ms


class SampleClock:
    """Monotonic accepted-sample counter. Paused time and dropped frames add nothing."""

    def __init__(self) -> None:
        self.offset = 0

    def accept(self, samples: int) -> tuple[int, int]:
        start = self.offset
        self.offset += samples
        return start, self.offset


@dataclass
class Epoch:
    """One upstream Scribe connection on the session clock.

    `origin` is the first sample forwarded on the connection; `sent_end` is the end of
    the contiguous range the writer has successfully delivered upstream.
    """

    number: int
    origin: int | None = None
    forwarded_end: int | None = None
    sent_end: int | None = None
    closed: bool = False

    def forward(self, start: int, end: int) -> bool:
        """Record a forwarded frame. Returns True when this frame opens the epoch."""
        opened = self.origin is None
        if opened:
            self.origin = start
        elif start != self.forwarded_end:
            raise ValueError("Forwarded audio must be contiguous within an epoch")
        self.forwarded_end = end
        return opened

    def mark_sent(self, end: int) -> None:
        self.sent_end = end
