"""emotion2vec+ Large scorer via funasr.AutoModel (B-04).

Heavy imports (numpy, torch, funasr) happen only inside load()/score(), so the
module is importable and unit-testable without the live stack.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..audio_ai_ports import AudioWindow, ScoredWindow

MODEL_ID = "iic/emotion2vec_plus_large"
LOCAL_DIR_NAME = "emotion2vec_plus_large"
LABELS = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "unknown")
# Proven aliases only. Tokens are bilingual ("生气/angry"); we take the part after "/".
ALIASES = {"<unk>": "unknown"}
SUM_TOLERANCE = 1e-3


class ScoringError(RuntimeError):
    """Model output was unusable (label-only, missing, negative, non-finite...)."""


def normalize_label(raw: str) -> str:
    token = raw.split("/")[-1].strip().lower()
    token = ALIASES.get(token, token)
    if token not in LABELS:
        raise ScoringError(f"unrecognised emotion label {raw!r}")
    return token


def normalize_output(result: object) -> dict[str, float]:
    """Turn the raw ``generate()`` return into nine probability-like scores.

    Expects ``[{"key":..., "labels":[...9], "scores":[...9]}]``. Scores must be
    finite, non-negative, one per label, and sum to 1 within 1e-3; they are then
    renormalized to sum exactly 1 (score_kind=probability_like).
    """
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes)) or not result:
        raise ScoringError("empty or non-list model output")
    item = result[0]
    if not isinstance(item, Mapping) or "labels" not in item:
        raise ScoringError("output has no labels")
    if "scores" not in item or item["scores"] is None:
        raise ScoringError("label-only output: no scores")
    labels, scores = list(item["labels"]), list(item["scores"])
    if len(labels) != len(scores):
        raise ScoringError(f"labels/scores length mismatch {len(labels)} vs {len(scores)}")
    out: dict[str, float] = {}
    for lab, sc in zip(labels, scores):
        name = normalize_label(str(lab))
        value = float(sc)
        if not math.isfinite(value):
            raise ScoringError(f"non-finite score for {name}")
        if value < 0:
            raise ScoringError(f"negative score for {name}")
        if name in out:
            raise ScoringError(f"duplicate label {name}")
        out[name] = value
    missing = [k for k in LABELS if k not in out]
    if missing:
        raise ScoringError(f"missing labels: {missing}")
    total = sum(out.values())
    if abs(total - 1.0) > SUM_TOLERANCE:
        raise ScoringError(f"scores sum to {total:.6f}, not probability-like")
    return {k: out[k] / total for k in LABELS}


def pcm_to_float32(pcm_s16le: bytes):
    """Mono 16 kHz s16le -> float32 in [-1, 1)."""
    import numpy as np

    if len(pcm_s16le) % 2:
        raise ScoringError("PCM length is not a whole number of samples")
    return np.frombuffer(pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0


def resolve_model_source(cache_dir: str | os.PathLike | None) -> str:
    """Local directory holding config.yaml+model.pt if available, else the hub ID."""
    raw = cache_dir or os.environ.get("EMOTION_MODEL_CACHE_DIR")
    if raw:
        base = Path(raw).expanduser()
        for cand in (base, base / LOCAL_DIR_NAME):
            if (cand / "config.yaml").is_file() and (cand / "model.pt").is_file():
                return str(cand)
    return MODEL_ID


class Emotion2vecLargeScorer:
    score_kind = "probability_like"

    def __init__(self, *, cache_dir: str | os.PathLike | None = None, device: str = "cpu") -> None:
        self._cache_dir = cache_dir
        self._device = device
        self._model = None
        self.model_source: str | None = None
        self.load_count = 0

    def load(self) -> None:
        if self._model is not None:
            return
        from funasr import AutoModel

        self.model_source = resolve_model_source(self._cache_dir)
        kwargs = {"model": self.model_source, "device": self._device, "disable_update": True}
        self._model = AutoModel(**kwargs)
        self.load_count += 1

    def score(self, window: AudioWindow) -> ScoredWindow:
        if self._model is None:
            raise ScoringError("model not loaded")
        if len(window.pcm_s16le) != 2 * (window.end_sample - window.start_sample):
            raise ScoringError("window PCM length does not match its bounds")
        wav = pcm_to_float32(window.pcm_s16le)
        raw = self._model.generate(
            wav, granularity="utterance", extract_embedding=False, disable_pbar=True
        )
        scores = normalize_output(raw)
        return ScoredWindow(
            window.session_id, window.epoch, window.start_sample, window.end_sample,
            "probability_like", scores,
        )

    def score_raw(self, wav) -> object:
        """Diagnostic: return the untouched generate() value for a numpy array/path."""
        if self._model is None:
            raise ScoringError("model not loaded")
        return self._model.generate(
            wav, granularity="utterance", extract_embedding=False, disable_pbar=True
        )
