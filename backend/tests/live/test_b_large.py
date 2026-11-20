"""Opt-in: RUN_LIVE_MODEL=1 scores real audio with the real model (needs live venv + cache)."""

import os
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LIVE_MODEL") != "1", reason="set RUN_LIVE_MODEL=1")

CACHE = Path(os.environ.get("EMOTION_MODEL_CACHE_DIR", "~/model-cache/emotion2vec_plus_large")).expanduser()


def test_real_model_scores_example_wav():
    from backend.app.adapters.emotion2vec import LABELS, Emotion2vecLargeScorer
    from backend.app.audio.window_scheduler import WindowScheduler
    from backend.app.audio_ai_ports import PcmFrame

    with wave.open(str(CACHE / "example" / "test.wav"), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        pcm = w.readframes(w.getnframes())
    n = len(pcm) // 2
    assert n >= 32000
    sch = WindowScheduler()
    sch.begin_epoch("live", 0, 0)
    windows = sch.push(PcmFrame("live", 0, 0, n, pcm))
    assert windows
    scorer = Emotion2vecLargeScorer(cache_dir=CACHE)
    scorer.load()
    r = scorer.score(windows[0])
    assert r.score_kind == "probability_like" and set(r.scores) == set(LABELS)
    assert abs(sum(r.scores.values()) - 1) < 1e-6
    assert all(0 <= v <= 1 for v in r.scores.values())
