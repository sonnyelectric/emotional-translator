"""Process settings. Only an explicit live launch reads backend/.env."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, PositiveInt, SecretStr

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    mode: Literal["replay", "live"] = "replay"
    allowed_origin: str = "http://localhost:5173"
    elevenlabs_api_key: SecretStr | None = None
    scribe_model_id: Literal["scribe_v3_live"] = "scribe_v3_live"
    scribe_commit_strategy: Literal["vad"] = "vad"
    scribe_vad_silence_secs: float = 0.65
    audio_sample_rate: int = 16000
    emotion_model_id: Literal["iic/emotion2vec_plus_large"] = "iic/emotion2vec_plus_large"
    emotion_window_seconds: float = 2.0
    emotion_hop_seconds: float = 1.0
    emotion_smoothing_alpha: float = 0.55
    emotion_visible_support: float = 0.42
    emotion_faint_support: float = 0.25
    emotion_neutral_suppress: float = 0.50
    emotion_blend_secondary_min: float = 0.30
    emotion_blend_gap_max: float = 0.15
    emotion_hysteresis: float = 0.06
    max_pending_emotion_windows: PositiveInt = 2
    phrase_gap_ms: PositiveInt = 350
    session_drain_timeout_ms: PositiveInt = 1200
    phrase_lookahead_ms: PositiveInt = 2000
    retry_max_attempts: PositiveInt = 5
    emotion_model_cache_dir: Path | None = None


def load_settings() -> Settings:
    mode = os.environ.get("TRANSLATOR_MODE", "replay")
    if mode != "live":
        values = {"mode": mode}
        if "ALLOWED_ORIGIN" in os.environ:
            values["allowed_origin"] = os.environ["ALLOWED_ORIGIN"]
        return Settings.model_validate(values)

    from dotenv import dotenv_values


    environment = {**dotenv_values(BACKEND_ROOT / ".env"), **os.environ}
    values = {
        name: environment[name.upper()]
        for name in Settings.model_fields
        if name != "mode" and environment.get(name.upper()) not in (None, "")
    }
    return Settings(mode=mode, **values)
