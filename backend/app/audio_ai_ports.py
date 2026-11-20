"""A/B interface. Concrete adapters and processing are supplied by Builder B."""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from .config import Settings
from .schemas import VisibleCategory

ScoreVector = Mapping[str, float]
ScoreKind = Literal["probability_like", "comparable"]


@dataclass(frozen=True, slots=True)
class PcmFrame:
    session_id: str
    epoch: int
    start_sample: int
    end_sample: int
    pcm_s16le: bytes


@dataclass(frozen=True, slots=True)
class AudioWindow:
    session_id: str
    epoch: int
    start_sample: int
    end_sample: int
    pcm_s16le: bytes


@dataclass(frozen=True, slots=True)
class TimedToken:
    text: str
    start_sample: int
    end_sample: int


@dataclass(frozen=True, slots=True)
class ScribeNotice:
    epoch: int
    kind: Literal["partial", "commit", "timed", "transient_error", "fatal_error"]
    text: str | None = None
    language_code: str | None = None
    provider_commit_key: str | None = None
    tokens: tuple[TimedToken, ...] = ()
    timestamp_basis: Literal["connection", "segment", "unknown"] = "unknown"
    segment_origin_samples: int | None = None
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredWindow:
    session_id: str
    epoch: int
    start_sample: int
    end_sample: int
    score_kind: ScoreKind
    scores: ScoreVector


@dataclass(frozen=True, slots=True)
class WindowNotice:
    session_id: str
    epoch: int
    start_sample: int
    end_sample: int
    kind: Literal["scored", "dropped", "silence", "failed"]
    enqueued_at_ms: float
    settled_at_ms: float
    started_at_ms: float | None = None
    scored: ScoredWindow | None = None


@dataclass(frozen=True, slots=True)
class RenderCandidate:
    primary: VisibleCategory
    secondary: VisibleCategory | None
    support: float
    visual_intensity: float
    opacity: float
    blend_weight: float | None


class ScribeStream(Protocol):
    async def send_pcm(self, pcm_s16le: bytes) -> None: ...
    def events(self) -> AsyncIterator[ScribeNotice]: ...
    async def aclose(self) -> None: ...


class ScribeAdapter(Protocol):
    async def open(self, epoch: int) -> ScribeStream: ...


class WindowScheduler(Protocol):
    def begin_epoch(self, session_id: str, epoch: int, first_sample: int) -> None: ...
    def push(self, frame: PcmFrame) -> Sequence[AudioWindow]: ...


class ModelScorer(Protocol):
    def load(self) -> None: ...
    def score(self, window: AudioWindow) -> ScoredWindow: ...


class EmotionWorker(Protocol):
    async def start(self) -> None: ...
    def offer(self, window: AudioWindow) -> None: ...
    def results(self) -> AsyncIterator[WindowNotice]: ...
    def discard(self, session_id: str, *, epoch: int | None = None) -> None: ...
    async def aclose(self) -> None: ...


class ScorePolicy(Protocol):
    def smooth(self, current: ScoreVector, previous: ScoreVector | None, config: Settings) -> ScoreVector: ...
    def classify(
        self, scores: ScoreVector, previous_state: RenderCandidate | None, config: Settings
    ) -> RenderCandidate | None: ...
