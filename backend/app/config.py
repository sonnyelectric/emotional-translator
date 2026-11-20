"""Process settings. Only an explicit live launch reads backend/.env."""

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, PositiveFloat, PositiveInt, SecretStr, field_validator

ORIGIN_PATTERN = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+$")
ORIGIN_ENV = ("ALLOWED_ORIGIN", "ALLOWED_ORIGINS", "ALLOWED_ORIGIN_REGEX")

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    mode: Literal["replay", "live"] = "replay"
    # Browser origins allowed to open the session WebSocket and read the replay routes.
    # ALLOWED_ORIGIN (legacy, one origin) and ALLOWED_ORIGINS (comma-separated) are exact
    # matches; ALLOWED_ORIGIN_REGEX is matched against the whole Origin (re.fullmatch), e.g.
    # ^https://[a-z0-9-]+-team\.vercel\.app$ for Vercel previews. When ALLOWED_ORIGINS is
    # set and ALLOWED_ORIGIN is not, the localhost default is dropped. Everything else is refused.
    allowed_origin: str = "http://localhost:5173"
    allowed_origins: tuple[str, ...] = ()
    allowed_origin_regex: str | None = None
    elevenlabs_api_key: SecretStr | None = None
    scribe_model_id: Literal["scribe_v3_live"] = "scribe_v3_live"
    scribe_commit_strategy: Literal["vad"] = "vad"
    scribe_vad_silence_secs: float = 0.65
    audio_sample_rate: int = 16000
    emotion_model_id: Literal["iic/emotion2vec_plus_large"] = "iic/emotion2vec_plus_large"
    emotion_window_seconds: float = 2.0
    emotion_hop_seconds: float = 1.0
    emotion_smoothing_alpha: float = 0.55
    emotion_visible_support: float = 0.36
    emotion_faint_support: float = 0.20
    emotion_neutral_suppress: float = 0.60
    emotion_blend_secondary_min: float = 0.30
    emotion_blend_gap_max: float = 0.15
    emotion_hysteresis: float = 0.06
    # EMOTION_LABEL_GAINS: per-label weights applied only when choosing which emotion a phrase
    # shows and how strongly (raw model scores are still emitted and shown unchanged). A demo
    # tuning knob, not a calibration: >1 makes a label easier to show, <1 harder.
    # Format: "happy=0.6,sad=1.3". Labels left out keep weight 1.0.
    emotion_label_gains: dict[str, float] = {
        "angry": 1.3, "disgusted": 1.6, "fearful": 1.6, "happy": 0.6, "sad": 1.3,
        "surprised": 1.4, "neutral": 0.8, "other": 0.8, "unknown": 0.7,
    }
    max_pending_emotion_windows: PositiveInt = 2
    phrase_gap_ms: PositiveInt = 350
    session_drain_timeout_ms: PositiveInt = 1200
    phrase_lookahead_ms: PositiveInt = 2000
    retry_max_attempts: PositiveInt = 5
    # Backoff for transient Scribe failures: 0.5, 1, 2, 4 s (capped) with jitter.
    retry_base_ms: PositiveInt = 500
    retry_cap_ms: PositiveInt = 4000
    # Clock basis of Scribe word times. scripts/smoke_scribe.py determines it at the event.
    # "unknown" (default) honours the adapter's per-notice basis; the adapter reports
    # "unknown", so no clouds attach (ALIGNMENT_BASIS_UNKNOWN) until the smoke proves a basis.
    # "connection": word times count from the start of the upstream connection.
    # "segment": word times restart per commit. Scribe supplies no segment origin, so only
    # the first commit of each connection is timed (at the connection start, plan B); later
    # commits yield ALIGNMENT_BASIS_UNKNOWN (no invented offsets). "provider" is a legacy
    # alias for "unknown".
    scribe_timestamp_basis: Literal["unknown", "connection", "segment"] = "unknown"
    # Bounded Scribe writer queue in frames (~2 s at 40 ms). Overflow starts a new epoch.
    scribe_send_queue_frames: PositiveInt = 50
    # Wall-clock bound on waiting for model windows before a phrase is frozen.
    phrase_pending_timeout_ms: PositiveInt = 3000
    emotion_model_cache_dir: Path | None = None
    # RECORD_SESSION_EVENTS: opt-in. When set to a .jsonl path (relative paths resolve from
    # the repo root), each live session's emitted events (text, timestamps, scores; never
    # audio) are written there as a replay fixture with a "recorded live session" manifest
    # entry when the session ends. Example: shared/fixtures/replay_live_recorded.jsonl
    record_session_events: Path | None = None
    # Public-endpoint guards (the Scribe key is server-side, so every live second costs credit).
    # SESSION_MAX_SECONDS: a live session is stopped cleanly (session.warning, then stopped)
    # this many wall-clock seconds after Start, paused time included.
    session_max_seconds: PositiveFloat = 300
    # LIVE_DAILY_MAX_SECONDS: optional in-memory cap on live wall-clock seconds per UTC day.
    # New live sessions are refused with session.error LIVE_DAILY_LIMIT_REACHED once it is used.
    # Resets on process restart.
    live_daily_max_seconds: PositiveFloat | None = None
    # ENABLE_TUNE_ROUTE=1 mounts the dev tuning route (/ws/dev/tune) in live mode.
    enable_tune_route: bool = False

    @field_validator("emotion_label_gains", mode="before")
    @classmethod
    def _parse_gains(cls, value: object) -> object:
        if isinstance(value, str):
            parsed: dict[str, float] = {}
            for item in value.split(","):
                if not item.strip():
                    continue
                label, _, weight = item.partition("=")
                parsed[label.strip().lower()] = float(weight)
            return parsed
        return value

    @field_validator("emotion_label_gains", mode="after")
    @classmethod
    def _check_gains(cls, value: dict[str, float]) -> dict[str, float]:
        known = {"angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown"}
        for label, weight in value.items():
            if label not in known:
                raise ValueError(f"Unknown emotion label in EMOTION_LABEL_GAINS: {label!r}")
            if not (0 < weight <= 10):
                raise ValueError(f"EMOTION_LABEL_GAINS weight for {label!r} must be in (0, 10]")
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, (list, tuple)):
            return tuple(item.strip().rstrip("/") for item in value if item and item.strip())
        return value

    @field_validator("allowed_origin", mode="after")
    @classmethod
    def _check_origin(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not ORIGIN_PATTERN.match(value):
            raise ValueError(f"Not an exact http(s) origin: {value!r}")
        return value

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def _check_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for origin in value:
            if not ORIGIN_PATTERN.match(origin):
                raise ValueError(f"Not an exact http(s) origin: {origin!r}")
        return value

    @field_validator("allowed_origin_regex", mode="after")
    @classmethod
    def _check_regex(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"ALLOWED_ORIGIN_REGEX is not a valid regex: {exc}") from None
        return value.strip()

    @property
    def exact_origins(self) -> tuple[str, ...]:
        if self.allowed_origins and "allowed_origin" not in self.model_fields_set:
            return self.allowed_origins
        return tuple(dict.fromkeys((self.allowed_origin, *self.allowed_origins)))

    def origin_allowed(self, origin: str) -> bool:
        if origin in self.exact_origins:
            return True
        return self.allowed_origin_regex is not None and re.fullmatch(self.allowed_origin_regex, origin) is not None

    @field_validator("record_session_events", mode="after")
    @classmethod
    def _resolve_record_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        if value.suffix != ".jsonl":
            raise ValueError("RECORD_SESSION_EVENTS must end in .jsonl")
        return value if value.is_absolute() else BACKEND_ROOT.parent / value

    @field_validator("scribe_timestamp_basis", mode="before")
    @classmethod
    def _legacy_basis(cls, value: object) -> object:
        return "unknown" if value == "provider" else value


def load_settings() -> Settings:
    mode = os.environ.get("TRANSLATOR_MODE", "replay")
    if mode != "live":
        values = {"mode": mode}
        for name in ORIGIN_ENV:
            if os.environ.get(name):
                values[name.lower()] = os.environ[name]
        return Settings.model_validate(values)

    from dotenv import dotenv_values


    environment = {**dotenv_values(BACKEND_ROOT / ".env"), **os.environ}
    values = {
        name: environment[name.upper()]
        for name in Settings.model_fields
        if name != "mode" and environment.get(name.upper()) not in (None, "")
    }
    return Settings(mode=mode, **values)
