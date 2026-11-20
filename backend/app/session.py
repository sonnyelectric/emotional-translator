"""Live session orchestration: emitter, process runtime, clock, epochs and fan-out (A-owned).

Concrete B classes are imported lazily inside `build_live_runtime`, so replay mode
never imports Scribe, the model runtime, or the score policy.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from .alignment.phrases import PhraseEngine
from .alignment.segments import SegmentTracker
from .audio.clock import Epoch, SampleClock, frame_samples
from .audio.relay import (
    FATAL_MESSAGES,
    QUIET_CODES,
    UpstreamLink,
    classify_failure,
    open_with_retry,
)
from .audio_ai_ports import (
    AudioWindow,
    EmotionWorker,
    PcmFrame,
    ScribeAdapter,
    ScribeNotice,
    ScorePolicy,
    WindowNotice,
    WindowScheduler,
)
from .config import Settings
from .metrics import Metrics
from .schemas import SCHEMA_VERSION, ServerEvent

log = logging.getLogger(__name__)

PCM_FIELDS = {"sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le"}
TICK_SECONDS = 0.25
MODEL_FAILURES_BEFORE_DISABLE = 3
SLOW_DROPS_BEFORE_WARNING = 3

WARNING_MESSAGES = {
    "SCRIBE_RECONNECTING": "Transcription is reconnecting. Committed words are preserved.",
    "EMOTION_MODEL_UNAVAILABLE": "Emotion cues are unavailable. Transcription continues.",
    "EMOTION_INFERENCE_SLOW": "Emotion annotations are delayed; transcription continues.",
    "INVALID_COMMAND": "That command was malformed and was ignored.",
    "INVALID_STATE": "That command is not available in the current session state.",
    "INVALID_AUDIO_FRAME": "An audio frame had an invalid size and was dropped.",
    "AUDIO_NOT_ACCEPTED": "Audio is accepted only while listening; the frame was dropped.",
}
ERROR_MESSAGES = {
    **FATAL_MESSAGES,
    "LIVE_NOT_CONFIGURED": "Live mode is not configured on this backend. Replay remains available.",
    "LIVE_SESSION_BUSY": "Another live session is already active on this backend.",
}


def new_session_id() -> str:
    return f"s-{uuid.uuid4().hex[:16]}"


class Emitter:
    """Single outbound path: assigns seq/issued time and validates every event."""

    def __init__(self, session_id: str, sink: Callable[[str], None], now: Callable[[], float] = time.monotonic):
        self.session_id = session_id
        self.sink = sink
        self.now = now
        self.t0 = now()
        self.seq = 0
        self.last_issued = 0
        self.rejected = 0

    def emit(self, event_type: str, payload: dict) -> dict | None:
        issued = max(self.last_issued, int(round((self.now() - self.t0) * 1000)))
        data = {"schema_version": SCHEMA_VERSION, "type": event_type, "session_id": self.session_id,
                "seq": self.seq + 1, "issued_at_ms": issued, "payload": payload}
        try:
            ServerEvent.model_validate(data)
        except ValidationError as exc:
            self.rejected += 1
            log.error("Dropped invalid outbound %s: %s", event_type, exc.errors()[0]["msg"])
            return None
        self.seq += 1
        self.last_issued = issued
        self.sink(json.dumps(data, separators=(",", ":"), allow_nan=False))
        return data


class LiveRuntime:
    """Process-level live resources: one Scribe adapter, one model worker, one lease."""

    def __init__(
        self,
        settings: Settings,
        *,
        scribe_adapter: ScribeAdapter | None = None,
        worker: EmotionWorker | None = None,
        scheduler_factory: Callable[[], WindowScheduler] | None = None,
        policy: ScorePolicy | None = None,
        setup_error: str | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ):
        self.settings = settings
        self.scribe_adapter = scribe_adapter
        self.worker = worker
        self.scheduler_factory = scheduler_factory
        self.policy = policy
        self.setup_error = setup_error or (None if scribe_adapter else "LIVE_NOT_CONFIGURED")
        self.sleep = sleep
        self.emotion_ready = worker is not None and scheduler_factory is not None and policy is not None
        self.model_state = "loading" if self.emotion_ready else "failed"
        self.lease: LiveSession | None = None
        self.metrics = Metrics()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self.emotion_ready:
            self._tasks.append(asyncio.create_task(self._load(), name="emotion-load"))

    async def _load(self) -> None:
        started = time.monotonic()
        try:
            await self.worker.start()
        except Exception as exc:  # load failure leaves Scribe usable, text-only
            log.warning("Emotion model failed to load: %s", type(exc).__name__)
            self.set_model_state("failed")
            return
        self.metrics.observe("model_load", (time.monotonic() - started) * 1000)
        self.set_model_state("ready")
        self._tasks.append(asyncio.create_task(self._results(), name="emotion-results"))

    async def _results(self) -> None:
        try:
            async for notice in self.worker.results():
                session = self.lease
                if session is not None and session.session_id == notice.session_id:
                    session.on_window_notice(notice)
                else:
                    self.metrics.count("window_results_quarantined")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Emotion worker results ended: %s", type(exc).__name__)
            self.set_model_state("failed")

    def set_model_state(self, state: str) -> None:
        previous, self.model_state = self.model_state, state
        if previous != state and self.lease is not None:
            self.lease.on_model_state(previous, state)

    @property
    def model_usable(self) -> bool:
        return self.model_state in ("ready", "degraded")

    def acquire(self, session: LiveSession) -> bool:
        if self.lease is not None:
            return False
        self.lease = session
        return True

    def release(self, session: LiveSession) -> None:
        if self.lease is session:
            self.lease = None

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self.worker is not None:
            with contextlib.suppress(Exception):
                await self.worker.aclose()


def _load_policy() -> ScorePolicy:
    module = importlib.import_module("backend.app.emotion.smoothing")
    for name in ("ScorePolicy", "DefaultScorePolicy", "EmotionScorePolicy", "Policy"):
        candidate = getattr(module, name, None)
        if isinstance(candidate, type) and hasattr(candidate, "classify") and hasattr(candidate, "smooth"):
            return candidate()
    if callable(getattr(module, "smooth", None)) and callable(getattr(module, "classify", None)):
        return module  # module-level functions satisfy the port
    raise ImportError("No ScorePolicy implementation in backend.app.emotion.smoothing")


def build_live_runtime(settings: Settings) -> LiveRuntime:
    """Explicit live launch only. Imports B's concrete classes here, never at module import."""
    adapter = setup_error = None
    if settings.elevenlabs_api_key is None or not settings.elevenlabs_api_key.get_secret_value():
        setup_error = "LIVE_NOT_CONFIGURED"
        log.error("Live launch without ELEVENLABS_API_KEY; live start will report LIVE_NOT_CONFIGURED")
    else:
        try:
            from .adapters.scribe import ElevenLabsScribeAdapter

            adapter = ElevenLabsScribeAdapter(api_key=settings.elevenlabs_api_key.get_secret_value(),
                                              vad_silence_secs=settings.scribe_vad_silence_secs)
        except ImportError as exc:
            setup_error = "LIVE_NOT_CONFIGURED"
            log.error("Scribe adapter unavailable: %s", exc)
    worker = scheduler_factory = policy = None
    try:
        from .adapters.emotion2vec import Emotion2vecLargeScorer
        from .audio.window_scheduler import WindowScheduler as SchedulerClass
        from .emotion.worker import BoundedEmotionWorker

        policy = _load_policy()
        scorer = Emotion2vecLargeScorer(cache_dir=settings.emotion_model_cache_dir)
        worker = BoundedEmotionWorker(scorer, max_pending=settings.max_pending_emotion_windows)
        scheduler_factory = SchedulerClass
    except ImportError as exc:
        log.error("Emotion runtime unavailable, live sessions will be text-only: %s", exc)
    return LiveRuntime(settings, scribe_adapter=adapter, worker=worker, scheduler_factory=scheduler_factory,
                       policy=policy, setup_error=setup_error)


class LiveSession:
    """One bound live session: audio clock, upstream epochs, alignment and lifecycle."""

    def __init__(self, runtime: LiveRuntime, emitter: Emitter, close_transport: Callable[[int], None]):
        self.runtime = runtime
        self.settings = runtime.settings
        self.emitter = emitter
        self.session_id = emitter.session_id
        self.close_transport = close_transport
        self.state = "idle"
        self.scribe = "disconnected"
        self.clock = SampleClock()
        self.epoch_counter = 0
        self.epoch: Epoch | None = None
        self.link: UpstreamLink | None = None
        self.scheduler = runtime.scheduler_factory() if runtime.scheduler_factory else None
        self.tracker = SegmentTracker(timestamp_basis=self.settings.scribe_timestamp_basis)
        self.engine = PhraseEngine(self.settings, runtime.policy) if runtime.policy else None
        self.outstanding: dict[tuple[int, int], int] = {}
        self.retry_once_seen: set[str] = set()
        self.metrics = Metrics()
        self.model_failures = 0
        self.drops_since_warning = 0
        self.warned: set[str] = set()
        self.audio_warned_state: str | None = None
        self._connect_task: asyncio.Task | None = None
        self._pause_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._ticker: asyncio.Task | None = None
        self._closed = False

    # ---- emission helpers -------------------------------------------------------
    def emit(self, events: list[tuple[str, dict]]) -> None:
        for event_type, payload in events:
            self.emitter.emit(event_type, payload)

    def status(self, detail: str | None = None) -> None:
        payload = {"state": self.state, "mode": "live", "scribe": self.scribe,
                   "emotion_model": self.runtime.model_state, "detail": detail}
        if self.state == "listening":
            payload.update(PCM_FIELDS)
        self.emitter.emit("session.status", payload)

    def warn(self, code: str, once: bool = False) -> None:
        if once and code in self.warned:
            return
        self.warned.add(code)
        self.emitter.emit("session.warning", {"code": code, "message": WARNING_MESSAGES[code], "recoverable": True})

    def _spawn(self, coro, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ---- commands ---------------------------------------------------------------
    def start(self) -> None:
        self.state, self.scribe = "connecting", "connecting"
        self.status()
        if not self.runtime.model_usable and self.runtime.model_state == "failed":
            self.warn("EMOTION_MODEL_UNAVAILABLE", once=True)
        self._ticker = self._spawn(self._tick_loop(), "phrase-ticker")
        self._connect_task = self._spawn(self._connect(first_delay=False), "scribe-connect")

    def pause(self) -> None:
        self.state = "paused"  # audio after this point is not accepted
        self._pause_task = self._spawn(self._pause(), "session-pause")

    def resume(self) -> None:
        self.state, self.scribe = "connecting", "connecting"
        self.status()
        self._connect_task = self._spawn(self._resume(self._pause_task), "scribe-connect")

    async def _resume(self, pause_task: asyncio.Task | None) -> None:
        if pause_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(pause_task)  # old epoch fully closed before a new one opens
        self.scribe = "connecting"
        await self._connect(first_delay=False)

    def stop(self) -> None:
        previous = self.state
        self.state = "stopping"
        self.status()
        self._spawn(self._stop(previous), "session-stop")

    # ---- upstream connection ----------------------------------------------------
    async def _connect(self, first_delay: bool) -> None:
        self.epoch_counter += 1
        number = self.epoch_counter
        started = time.monotonic()
        stream, fatal, attempts = await open_with_retry(
            lambda: self.runtime.scribe_adapter.open(number),
            attempts=self.settings.retry_max_attempts, base_ms=self.settings.retry_base_ms,
            cap_ms=self.settings.retry_cap_ms, retry_once_seen=self.retry_once_seen,
            sleep=self.runtime.sleep, first_delay=first_delay)
        self.metrics.count("scribe_open_attempts", attempts)
        if self.state not in ("connecting", "listening"):
            if stream is not None:
                with contextlib.suppress(Exception):
                    await stream.aclose()
            return
        if fatal:
            await self.fail(fatal)
            return
        self.metrics.observe("scribe_open", (time.monotonic() - started) * 1000)
        self.epoch = Epoch(number)
        self.link = UpstreamLink(stream, self.epoch, queue_frames=self.settings.scribe_send_queue_frames,
                                 on_notice=self.on_notice, on_lost=self.on_lost)
        self.state, self.scribe = "listening", "connected"
        self.audio_warned_state = None
        self.status()

    def on_lost(self, link: UpstreamLink, code: str | None, fatal_hint: bool) -> None:
        if link is not self.link or self.state not in ("listening", "connecting"):
            return
        self.metrics.count("scribe_losses")
        fatal = classify_failure(code, fatal_hint, self.retry_once_seen)
        self._end_epoch(link)
        self._spawn(self._after_loss(link, code, fatal), "scribe-recover")

    def _end_epoch(self, link: UpstreamLink) -> None:
        """Common epoch teardown: clear stale partial, warn for untimed commits."""
        self.link = None
        link.epoch.closed = True
        events = self.tracker.clear_partial() + self.tracker.expire_epoch(link.epoch.number)
        if self.engine:
            events += self.engine.close_epoch(link.epoch.number)
        self.emit(events)

    async def _after_loss(self, link: UpstreamLink, code: str | None, fatal: str | None) -> None:
        await link.aclose()
        if fatal:
            await self.fail(fatal)
            return
        self.scribe = "reconnecting"
        if code not in QUIET_CODES:
            self.warn("SCRIBE_RECONNECTING")
        self.status()
        self._connect_task = asyncio.current_task()
        await self._connect(first_delay=True)

    # ---- inbound notices ---------------------------------------------------------
    def on_notice(self, link: UpstreamLink, notice: ScribeNotice) -> None:
        if link is not self.link:
            return
        if notice.kind == "partial":
            self.emit(self.tracker.on_partial(notice))
        elif notice.kind == "commit":
            self.emit(self.tracker.on_commit(notice))
        elif notice.kind == "timed":
            events, segment = self.tracker.on_timed(notice, link.epoch)
            self.emit(events)
            if segment is not None and self.engine is not None:
                self.emit(self.engine.add_segment(segment))

    def on_audio(self, data: bytes) -> str | None:
        """Accept a binary PCM frame. Returns a warning code when the frame is dropped."""
        if self.state != "listening":
            return "AUDIO_NOT_ACCEPTED"
        samples = frame_samples(data)
        if samples is None:
            return "INVALID_AUDIO_FRAME"
        start, end = self.clock.accept(samples)
        self.metrics.count("accepted_frames")
        link = self.link
        if link is None or link.lost:
            self.metrics.count("frames_not_forwarded")
            return None
        epoch = link.epoch
        opened = epoch.forward(start, end)
        if opened:
            if self.scheduler is not None:
                self.scheduler.begin_epoch(self.session_id, epoch.number, start)
            if self.engine is not None:
                self.engine.begin_epoch(epoch.number, start)
        if not link.offer(end, data):
            self.metrics.count("scribe_queue_overflow")
            self.on_lost(link, "queue_overflow", False)
            return None
        if self.engine is not None:
            self.engine.extend_epoch(epoch.number, end)
        if self.scheduler is not None:
            frame = PcmFrame(self.session_id, epoch.number, start, end, data)
            for window in self.scheduler.push(frame):
                self._offer_window(window)
        return None

    def _offer_window(self, window: AudioWindow) -> None:
        if self.runtime.model_usable and self.runtime.worker is not None:
            self.outstanding[(window.epoch, window.start_sample)] = window.end_sample
            self.runtime.worker.offer(window)
            self.metrics.count("windows_offered")
        elif self.engine is not None:
            self.metrics.count("windows_text_only")
            self.emit(self.engine.window_unusable(window.epoch, window.start_sample, window.end_sample))

    def on_window_notice(self, notice: WindowNotice) -> None:
        key = (notice.epoch, notice.start_sample)
        if self._closed or key not in self.outstanding:
            self.metrics.count("window_results_quarantined")
            return
        del self.outstanding[key]
        self.metrics.count(f"windows_{notice.kind}")
        if notice.started_at_ms is not None:
            self.metrics.observe("inference_queue_wait", notice.started_at_ms - notice.enqueued_at_ms)
            self.metrics.observe("inference_run", notice.settled_at_ms - notice.started_at_ms)
        if notice.kind == "failed":
            self.model_failures += 1
            self.warn("EMOTION_MODEL_UNAVAILABLE", once=True)
            if self.model_failures >= MODEL_FAILURES_BEFORE_DISABLE:
                self.runtime.set_model_state("failed")
            elif self.runtime.model_state == "ready":
                self.runtime.set_model_state("degraded")
        elif notice.kind == "scored":
            self.model_failures = 0
        elif notice.kind == "dropped":
            self.drops_since_warning += 1
            if self.drops_since_warning >= SLOW_DROPS_BEFORE_WARNING:
                self.drops_since_warning = 0
                self.warn("EMOTION_INFERENCE_SLOW")
        if self.engine is not None:
            self.emit(self.engine.window_notice(notice))

    def on_model_state(self, previous: str, state: str) -> None:
        if self.state in ("listening", "paused", "connecting"):
            if state == "failed":
                self.warn("EMOTION_MODEL_UNAVAILABLE", once=True)
            self.status()

    # ---- lifecycle ----------------------------------------------------------------
    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            if self.engine is not None:
                self.emit(self.engine.tick())

    def _fence_outstanding(self, epoch: int | None = None) -> None:
        """Discard pending model work and settle it as unusable so phrases can freeze."""
        keys = [k for k in self.outstanding if epoch is None or k[0] == epoch]
        if self.runtime.worker is not None:
            self.runtime.worker.discard(self.session_id, epoch=epoch)
        for key in keys:
            end = self.outstanding.pop(key)
            self.metrics.count("windows_fenced")
            if self.engine is not None:
                self.emit(self.engine.window_unusable(key[0], key[1], end))

    async def _wait_drained(self, timeout_s: float, *, windows: bool) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.tracker.pending_count() == 0 and (not windows or not self.outstanding):
                return
            await asyncio.sleep(0.02)
        self.metrics.count("drain_timeouts")

    async def _close_link(self, timeout_s: float, *, windows: bool) -> None:
        link = self.link
        if link is not None:
            started = time.monotonic()
            await link.drain_writes(timeout_s)
            remaining = max(0.0, timeout_s - (time.monotonic() - started))
            await self._wait_drained(remaining, windows=windows)
            if self.link is link:
                self._end_epoch(link)
            await link.aclose()
        self.scribe = "disconnected"

    async def _pause(self) -> None:
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
        number = self.epoch.number if self.epoch else None
        await self._close_link(self.settings.session_drain_timeout_ms / 1000, windows=False)
        self._fence_outstanding(number)
        if self.state == "paused":  # an early Resume supersedes the acknowledgement
            self.status()

    async def _stop(self, previous: str) -> None:
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
        await self._close_link(self.settings.session_drain_timeout_ms / 1000, windows=True)
        self._fence_outstanding()
        if self.engine is not None:
            self.emit(self.engine.finalize_all())
        self.state = "stopped"
        self.status()
        await self.cleanup()
        self.close_transport(1000)

    async def fail(self, code: str) -> None:
        if self.state in ("error", "stopped"):
            return
        self.emitter.emit("session.error", {"code": code, "message": ERROR_MESSAGES.get(code, code.title()),
                                            "recoverable": False})
        if self.link is not None:
            link = self.link
            self._end_epoch(link)
            await link.aclose()
        self._fence_outstanding()
        if self.engine is not None:
            self.emit(self.engine.finalize_all())
        self.state, self.scribe = "error", "failed"
        self.status("Live transcription could not continue.")
        await self.cleanup()
        self.close_transport(1000)

    async def cleanup(self) -> None:
        """Idempotent: cancel tasks, close upstream, drop model work, release the lease."""
        if self._closed:
            return
        self._closed = True
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        if self.link is not None:
            link, self.link = self.link, None
            await link.aclose()
        if self.runtime.worker is not None:
            self.runtime.worker.discard(self.session_id)
        if self.scheduler is not None and hasattr(self.scheduler, "end_session"):
            self.scheduler.end_session(self.session_id)
        self.outstanding.clear()
        self.runtime.release(self)
        self.metrics.merge("segments", self.tracker.counters)
        if self.engine is not None:
            self.metrics.merge("phrases", self.engine.counters)
        self.runtime.metrics.count("live_sessions")
        self.metrics.log_summary(f"session {self.session_id}")
