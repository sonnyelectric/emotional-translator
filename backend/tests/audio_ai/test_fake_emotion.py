import json
from pathlib import Path

import pytest

from backend.app.audio_ai_ports import AudioWindow
from backend.app.schemas import schema_validator
from backend.tests.fakes.emotion import (
    LABELS, MIXED_ANGER_SAD, NEUTRAL, FakeEmotionScorer, FakeScorerFailure,
)

PIPE = json.loads(
    (Path(__file__).resolve().parents[3] / "shared/fixtures/pipeline_examples.json").read_text())


def win(start, session="s", epoch=0):
    return AudioWindow(session, epoch, start, start + 32000, b"\x00" * 64000)


def test_fixture_vectors_seeded_and_valid():
    seeded = {w["start_sample"]: w["scores"] for w in PIPE["windows"]}
    f = FakeEmotionScorer(seeded)
    f.load()
    for start in (0, 16000, 32000):
        r = f.score(win(start, "sess", 3))
        assert (r.session_id, r.epoch, r.start_sample, r.end_sample) == ("sess", 3, start, start + 32000)
        assert set(r.scores) == set(LABELS)
        assert all(0 <= v <= 1 for v in r.scores.values())
        assert abs(sum(r.scores.values()) - 1) < 1e-3
        assert r.score_kind == "probability_like"
        assert dict(r.scores) == seeded[start]
        diag = {"epoch": r.epoch, "start_sample": r.start_sample, "end_sample": r.end_sample,
                "score_kind": r.score_kind, "scores": dict(r.scores)}
        schema_validator("model-window.schema.json").validate(diag)


def test_repeatable_and_cycle():
    f = FakeEmotionScorer(cycle=(NEUTRAL, MIXED_ANGER_SAD))
    assert f.score(win(0)).scores == f.score(win(0)).scores == NEUTRAL
    assert f.score(win(16000)).scores == MIXED_ANGER_SAD


def test_failure_and_block_release():
    import threading
    f = FakeEmotionScorer(fail_on={16000}, block_on={32000})
    with pytest.raises(FakeScorerFailure):
        f.score(win(16000))
    out = []
    t = threading.Thread(target=lambda: out.append(f.score(win(32000))))
    t.start()
    assert f.entered.wait(2)
    assert not out
    f.release.set()
    t.join(2)
    assert out and out[0].start_sample == 32000


def test_load_error():
    f = FakeEmotionScorer(load_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        f.load()
