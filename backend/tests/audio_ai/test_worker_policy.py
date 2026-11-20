import asyncio
import json
from pathlib import Path

import pytest

from backend.app.audio_ai_ports import AudioWindow, RenderCandidate
from backend.app.config import Settings
from backend.app.emotion.smoothing import LABELS, classify, opacity_for_support, smooth
from backend.app.emotion.worker import BoundedEmotionWorker, window_rms
from backend.tests.fakes.emotion import (
    MIXED_ANGER_SAD, NEUTRAL, STRONG_SAD, FakeEmotionScorer, FakeScorerFailure,
)

CFG = Settings()
CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared/fixtures/pipeline_examples.json").read_text()
)["classification_cases"]


def vec(**kw):
    v = {k: 0.0 for k in LABELS}
    v.update(kw)
    return v


# ---------------- smoothing ----------------

def test_smooth_first_passthrough_and_ema():
    assert smooth(STRONG_SAD, None, CFG) == STRONG_SAD
    out = smooth(NEUTRAL, STRONG_SAD, CFG)
    for k in LABELS:
        assert out[k] == pytest.approx(0.55 * NEUTRAL[k] + 0.45 * STRONG_SAD[k])
    assert sum(out.values()) == pytest.approx(1.0)


def test_smooth_damps_adjacent_fluctuation():
    prev = STRONG_SAD
    out = smooth(vec(sad=0.1, neutral=0.9), prev, CFG)
    assert 0.1 < out["sad"] < 0.66


# ---------------- classify ----------------

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_fixture_cases(case):
    r = classify(case["scores"], None, CFG)
    exp = case["expected"]
    if exp == "suppress":
        assert r is None
        return
    assert r is not None and r.primary == case["primary"]
    if exp == "faint":
        assert r.opacity <= 0.30 and r.blend_weight is None
    elif exp == "standard":
        assert r.opacity >= 0.35 and r.secondary is None
    elif exp == "blend":
        assert r.secondary == case["secondary"]
        s = case["scores"]
        assert r.blend_weight == pytest.approx(s[r.secondary] / (s[r.primary] + s[r.secondary]))


def test_neutral_leads_or_ties_suppresses():
    assert classify(vec(sad=0.45, neutral=0.45, angry=0.1), None, CFG) is None
    assert classify(vec(sad=0.30, other=0.31, neutral=0.2, angry=0.19), None, CFG) is None
    assert classify(vec(sad=0.30, unknown=0.35, neutral=0.2, angry=0.15), None, CFG) is None


def test_neutral_threshold_veto():
    # sad leads but neutral >= 0.50 cannot lead here; use a custom lower threshold
    cfg = Settings(emotion_neutral_suppress=0.30)
    assert classify(vec(sad=0.40, neutral=0.31, angry=0.29), None, cfg) is None
    assert classify(vec(sad=0.40, neutral=0.31, angry=0.29), None, CFG) is not None


def test_faint_standard_thresholds():
    assert classify(vec(sad=0.24, neutral=0.2, angry=0.2, happy=0.2, fearful=0.16), None, CFG) is None
    f = classify(vec(sad=0.25, neutral=0.2, angry=0.2, happy=0.2, fearful=0.15), None, CFG)
    assert f is not None and f.opacity < 0.31
    s = classify(vec(sad=0.42, neutral=0.2, angry=0.2, happy=0.18), None, CFG)
    assert s is not None and s.opacity >= 0.35


def test_hysteresis():
    base = dict(neutral=0.2, angry=0.2, happy=0.1)
    std = classify(vec(sad=0.45, **base), None, CFG)
    assert std.support >= 0.42
    # 0.38 sits inside the 0.06 band below 0.42: stays visible with previous standard...
    kept = classify(vec(sad=0.38, neutral=0.2, angry=0.2, happy=0.15), std, CFG)
    assert kept is not None
    # ...but opacity still follows support breakpoints (faint range), not the tier
    assert kept.opacity <= 0.30
    # exits below the band
    assert classify(vec(sad=0.17, neutral=0.2, angry=0.1, happy=0.1), kept, CFG) is None
    # faint exit band: 0.25-0.06
    faint = classify(vec(sad=0.26, neutral=0.2, angry=0.2, happy=0.2), None, CFG)
    assert classify(vec(sad=0.20, neutral=0.19, angry=0.19, happy=0.19), faint, CFG) is not None
    assert classify(vec(sad=0.20, neutral=0.19, angry=0.19, happy=0.19), None, CFG) is None
    # neutral bypasses hysteresis
    assert classify(vec(sad=0.30, neutral=0.31, angry=0.2), std, CFG) is None


def test_visible_tie_resolved_in_label_order():
    r = classify(vec(angry=0.40, sad=0.40, neutral=0.2), None, CFG)
    assert r.primary == "angry"


def test_blend_rules():
    r = classify(MIXED_ANGER_SAD, None, CFG)
    assert (r.primary, r.secondary) == ("angry", "sad")
    # weak secondary
    assert classify(vec(angry=0.5, sad=0.29, neutral=0.2), None, CFG).secondary is None
    # gap too large
    assert classify(vec(angry=0.6, sad=0.31, neutral=0.09), None, CFG).secondary is None
    # secondary neutral never blends
    assert classify(vec(angry=0.5, neutral=0.4), None, CFG).secondary is None
    # primary below standard entry
    assert classify(vec(angry=0.40, sad=0.35, neutral=0.25), None, CFG).secondary is None
    # at most two: third category never appears
    r3 = classify(vec(angry=0.44, sad=0.31, happy=0.25), None, CFG)
    assert r3.secondary == "sad" and r3.blend_weight == pytest.approx(0.31 / 0.75)


def test_intensity_bounds_and_opacity_monotonic():
    r = classify(STRONG_SAD, None, CFG)
    assert 0 <= r.visual_intensity <= 1
    assert r.visual_intensity == 1.0  # (0.66-0.09+0.25)/0.75 = 1.09 clipped
    weak = classify(vec(sad=0.44, neutral=0.30, angry=0.26), None, CFG)
    assert weak.visual_intensity == pytest.approx((0.44 - 0.30 + 0.25) / 0.75)
    xs = [i / 200 for i in range(0, 201)]
    ops = [opacity_for_support(x, CFG) for x in xs]
    assert all(b >= a - 1e-12 for a, b in zip(ops, ops[1:]))
    assert min(ops) == pytest.approx(0.14) and max(ops) == pytest.approx(0.75)


# ---------------- worker ----------------

def pcm(loud=True):
    return (b"\x00\x20" if loud else b"\x00\x00") * 32000


def mk(start, session="s", epoch=0, loud=True):
    return AudioWindow(session, epoch, start, start + 32000, pcm(loud))


async def drain(w, n, timeout=3):
    got = []

    async def go():
        async for x in w.results():
            got.append(x)
            if len(got) >= n:
                return

    await asyncio.wait_for(go(), timeout)
    return got


def run(coro):
    return asyncio.run(coro)


def test_rms():
    assert window_rms(pcm(False)) == 0 and window_rms(pcm(True)) > 0.2


def test_load_once_and_scored_with_tags_and_timing():
    async def go():
        f = FakeEmotionScorer({0: STRONG_SAD})
        w = BoundedEmotionWorker(f)
        await w.start()
        await w.start()
        assert f.load_count == 1
        w.offer(mk(0, "sess", 4))
        (n,) = await drain(w, 1)
        assert n.kind == "scored" and (n.session_id, n.epoch, n.start_sample) == ("sess", 4, 0)
        assert n.scored.scores == STRONG_SAD
        assert n.started_at_ms is not None and n.settled_at_ms >= n.started_at_ms >= n.enqueued_at_ms
        await w.aclose()
    run(go())


def test_load_failure_raises():
    async def go():
        w = BoundedEmotionWorker(FakeEmotionScorer(load_error=RuntimeError("no model")))
        with pytest.raises(RuntimeError):
            await w.start()
        await w.aclose()
    run(go())


def test_overflow_drops_oldest_pending_while_loop_runs():
    async def go():
        f = FakeEmotionScorer(block_on={0})
        w = BoundedEmotionWorker(f, max_pending=2)
        await w.start()
        w.offer(mk(0))
        await asyncio.get_running_loop().run_in_executor(None, f.entered.wait, 2)
        for s in (16000, 32000, 48000, 64000):  # pending cap 2 -> 16000, 32000 evicted
            w.offer(mk(s))
        ticks = 0
        for _ in range(5):  # event loop is not blocked by the running inference
            await asyncio.sleep(0.01)
            ticks += 1
        assert ticks == 5
        f.release.set()
        got = await drain(w, 5)
        kinds = [(n.start_sample, n.kind) for n in got]
        assert kinds[:2] == [(16000, "dropped"), (32000, "dropped")]
        assert sorted(k for k in kinds[2:]) == [(0, "scored"), (48000, "scored"), (64000, "scored")]
        assert w.stats.dropped == 2 and w.stats.max_queue_depth == 2
        # same-epoch ordering preserved among scored
        scored = [n.start_sample for n in got if n.kind == "scored"]
        assert scored == sorted(scored)
        await w.aclose()
    run(go())


def test_silence_failure_notices_and_continue():
    async def go():
        f = FakeEmotionScorer(fail_on={16000})
        w = BoundedEmotionWorker(f)
        await w.start()
        w.offer(mk(0, loud=False))
        w.offer(mk(16000))
        got = await drain(w, 2)
        assert [(n.start_sample, n.kind) for n in got] == [(0, "silence"), (16000, "failed")]
        assert got[0].started_at_ms is None and f.calls == [("s", 0, 16000)]
        w.offer(mk(32000))
        (n,) = await drain(w, 1)
        assert n.kind == "scored"  # worker survives failure
        await w.aclose()
    run(go())


def test_discard_scope_and_quarantine():
    async def go():
        f = FakeEmotionScorer(block_on={0})
        w = BoundedEmotionWorker(f, max_pending=3)
        await w.start()
        w.offer(mk(0, "a", 0))
        await asyncio.get_running_loop().run_in_executor(None, f.entered.wait, 2)
        w.offer(mk(16000, "a", 0))
        w.offer(mk(16000, "b", 0))
        w.offer(mk(32000, "a", 1))
        w.discard("a", epoch=0)  # drops pending a/0 and quarantines running a/0
        assert w.stats.discarded == 1
        f.release.set()
        got = await drain(w, 2)
        keys = {(n.session_id, n.epoch, n.start_sample) for n in got}
        assert keys == {("b", 0, 16000), ("a", 1, 32000)}  # no a/0 result leaked
        assert w.stats.stale_results == 1
        assert not any(n.session_id == "a" and n.epoch == 0 for n in got)
        await w.aclose()
    run(go())


def test_close_ends_results_and_ignores_offers():
    async def go():
        w = BoundedEmotionWorker(FakeEmotionScorer())
        await w.start()
        await w.aclose()
        w.offer(mk(0))
        assert [x async for x in w.results()] == []
    run(go())


def test_fake_clock_queue_wait():
    async def go():
        t = {"v": 100.0}

        def clock():
            t["v"] += 10
            return t["v"]
        f = FakeEmotionScorer()
        w = BoundedEmotionWorker(f, clock_ms=clock)
        await w.start()
        w.offer(mk(0))
        (n,) = await drain(w, 1)
        assert n.enqueued_at_ms == 110 and n.started_at_ms == 120 and n.settled_at_ms == 130
        assert w.stats.queue_wait_ms == [10] and w.stats.run_ms == [10]
        await w.aclose()
    run(go())
