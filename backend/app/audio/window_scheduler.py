"""Sample-accurate 2 s / 1 s-hop window extraction (B-04)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..audio_ai_ports import AudioWindow, PcmFrame

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 32_000
HOP_SAMPLES = 16_000
RING_SAMPLES = 8 * SAMPLE_RATE  # bounded eight-second ring
BYTES_PER_SAMPLE = 2


@dataclass(slots=True)
class _EpochState:
    epoch: int
    next_start: int  # start sample of the next window to emit
    buf_start: int  # sample index of buf[0]
    buf: bytearray = field(default_factory=bytearray)

    @property
    def buf_end(self) -> int:
        return self.buf_start + len(self.buf) // BYTES_PER_SAMPLE


class WindowScheduler:
    """Per-session ring; emits [o, o+32000), [o+16000, o+48000), ... Never pads a tail
    and never joins audio across epochs or across a sample gap."""

    def __init__(
        self,
        *,
        window_samples: int = WINDOW_SAMPLES,
        hop_samples: int = HOP_SAMPLES,
        ring_samples: int = RING_SAMPLES,
    ) -> None:
        if ring_samples < window_samples:
            raise ValueError("ring must hold at least one window")
        self._window = window_samples
        self._hop = hop_samples
        self._ring = ring_samples
        self._state: dict[str, _EpochState] = {}

    def begin_epoch(self, session_id: str, epoch: int, first_sample: int) -> None:
        self._state[session_id] = _EpochState(epoch, first_sample, first_sample)

    def end_session(self, session_id: str) -> None:
        self._state.pop(session_id, None)

    def push(self, frame: PcmFrame) -> list[AudioWindow]:
        st = self._state.get(frame.session_id)
        if st is None or frame.epoch != st.epoch:
            return []  # stale or unknown epoch: never mix into the current one
        n = frame.end_sample - frame.start_sample
        if n <= 0 or len(frame.pcm_s16le) != n * BYTES_PER_SAMPLE:
            raise ValueError("frame bounds do not match PCM length")
        if frame.end_sample <= st.buf_end and st.buf:
            return []  # entirely duplicate
        if frame.start_sample != st.buf_end:
            if frame.start_sample < st.buf_end:
                raise ValueError("overlapping frame")
            # forward gap: restart windowing at this frame (no joining across a gap)
            st.buf = bytearray()
            st.buf_start = frame.start_sample
            st.next_start = frame.start_sample
        st.buf += frame.pcm_s16le
        out: list[AudioWindow] = []
        while st.next_start + self._window <= st.buf_end:
            a = (st.next_start - st.buf_start) * BYTES_PER_SAMPLE
            b = a + self._window * BYTES_PER_SAMPLE
            out.append(
                AudioWindow(
                    frame.session_id, st.epoch, st.next_start,
                    st.next_start + self._window, bytes(st.buf[a:b]),  # copy before the ring is trimmed
                )
            )
            st.next_start += self._hop
        # bound the ring: keep the last ring_samples, never dropping un-emitted audio
        keep_from = max(st.buf_start, st.buf_end - self._ring)
        keep_from = min(keep_from, st.next_start)
        if keep_from > st.buf_start:
            del st.buf[: (keep_from - st.buf_start) * BYTES_PER_SAMPLE]
            st.buf_start = keep_from
        return out
