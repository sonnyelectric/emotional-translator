import math

import pytest

from backend.app.adapters.emotion2vec import (
    LABELS, Emotion2vecLargeScorer, ScoringError, normalize_label, normalize_output,
    resolve_model_source,
)
from backend.app.audio.window_scheduler import WindowScheduler
from backend.app.audio_ai_ports import PcmFrame

TOKENS = ["生气/angry", "厌恶/disgusted", "恐惧/fearful", "开心/happy", "中立/neutral",
          "其他/other", "难过/sad", "吃惊/surprised", "<unk>"]


def frame(start, n, session="s", epoch=0, fill=1):
    return PcmFrame(session, epoch, start, start + n, bytes([fill]) * (2 * n))


def feed(sch, total, chunk, **kw):
    out, pos = [], kw.pop("origin", 0)
    end = pos + total
    while pos < end:
        n = min(chunk, end - pos)
        out += sch.push(frame(pos, n, **kw))
        pos += n
    return out


def bounds(ws):
    return [(w.start_sample, w.end_sample) for w in ws]


def test_windows_and_hops():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    ws = feed(sch, 64000, 640)
    assert bounds(ws) == [(0, 32000), (16000, 48000), (32000, 64000)]
    assert all(len(w.pcm_s16le) == 64000 for w in ws)


def test_nonzero_origin_and_odd_frames():
    sch = WindowScheduler()
    sch.begin_epoch("s", 1, 5000)
    ws = feed(sch, 40000, 1234, epoch=1, origin=5000)
    assert bounds(ws) == [(5000, 37000)]  # 45000 end: second window needs 53000


def test_multiple_windows_from_one_big_frame_and_tail_not_padded():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    ws = sch.push(frame(0, 60000))
    assert bounds(ws) == [(0, 32000), (16000, 48000)]  # 12000-sample tail not padded
    assert bounds(sch.push(frame(60000, 4000))) == [(32000, 64000)]


def test_window_pcm_content_and_copy():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    sch.push(PcmFrame("s", 0, 0, 16000, b"\x01\x00" * 16000))
    ws = sch.push(PcmFrame("s", 0, 16000, 32000, b"\x02\x00" * 16000))
    first = ws[0].pcm_s16le
    assert first[:2] == b"\x01\x00" and first[-2:] == b"\x02\x00"
    feed(sch, 200000, 16000, origin=32000, fill=7)  # ring wraps; earlier copy unchanged
    assert ws[0].pcm_s16le == first


def test_epoch_change_never_joins():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    assert bounds(feed(sch, 48000, 1600)) == [(0, 32000)]
    sch.begin_epoch("s", 1, 48000)  # pause/reconnect
    assert sch.push(frame(48000, 16000, epoch=0)) == []  # stale epoch ignored
    ws = feed(sch, 40000, 1600, epoch=1, origin=48000)
    assert bounds(ws) == [(48000, 80000)]
    assert ws[0].epoch == 1 and ws[0].start_sample == 48000


def test_gap_restarts_origin():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    feed(sch, 20000, 1000)
    ws = feed(sch, 32000, 1000, origin=100000)  # forward gap: no joining
    assert bounds(ws) == [(100000, 132000)]


def test_ring_bounded():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    feed(sch, 16000 * 30, 640)
    assert len(sch._state["s"].buf) // 2 <= 8 * 16000


def test_bad_frame_rejected():
    sch = WindowScheduler()
    sch.begin_epoch("s", 0, 0)
    with pytest.raises(ValueError):
        sch.push(PcmFrame("s", 0, 0, 10, b"\x00" * 3))


# ---- adapter output normalisation (injected return values) ----

def good(scores=None):
    scores = scores or [0.01, 0.002, 0.003, 0.005, 0.97, 0.004, 0.003, 0.002, 0.001]
    return [{"key": "k", "labels": TOKENS, "scores": scores}]


def test_alias_and_labels():
    assert normalize_label("生气/angry") == "angry"
    assert normalize_label("<unk>") == "unknown"
    assert normalize_label("中立/neutral") == "neutral"
    out = normalize_output(good())
    assert tuple(out) == LABELS and abs(sum(out.values()) - 1) < 1e-9
    assert out["neutral"] > 0.9 and out["unknown"] == pytest.approx(0.001, rel=0.01)


def test_label_order_independent():
    r = good()
    r[0]["labels"] = list(reversed(TOKENS))
    r[0]["scores"] = list(reversed(r[0]["scores"]))
    assert normalize_output(r)["neutral"] > 0.9


@pytest.mark.parametrize("bad", [
    [], None, [{"labels": TOKENS}], [{"labels": TOKENS, "scores": None}],
    [{"labels": TOKENS, "scores": [0.1] * 8}],
    good([-0.1, 0.2, 0.1, 0.1, 0.4, 0.1, 0.1, 0.1, 0.0]),
    good([math.nan] + [0.1] * 8),
    good([math.inf] + [0.1] * 8),
    good([0.2] * 9),  # sums to 1.8
    [{"labels": ["生气/angry"] * 9, "scores": [1 / 9] * 9}],  # duplicate
    [{"labels": TOKENS[:-1] + ["bogus"], "scores": [1 / 9] * 9}],  # unknown alias
    [{"labels": TOKENS[:4], "scores": [0.25] * 4}],  # label subset (5-label style)
])
def test_rejects_unusable(bad):
    with pytest.raises(ScoringError):
        normalize_output(bad)


def test_score_requires_load_and_one_load():
    s = Emotion2vecLargeScorer(cache_dir="/nonexistent")
    with pytest.raises(ScoringError):
        s.score(None)  # type: ignore[arg-type]
    assert resolve_model_source("/nonexistent") == "iic/emotion2vec_plus_large"


def test_injected_model_scoring_and_pcm_normalisation():
    np = pytest.importorskip("numpy")
    from backend.app.adapters.emotion2vec import pcm_to_float32
    from backend.app.audio_ai_ports import AudioWindow
    arr = pcm_to_float32(np.array([0, 16384, -32768, 32767], dtype="<i2").tobytes())
    assert arr.dtype == np.float32 and list(arr[:3]) == [0.0, 0.5, -1.0]

    class M:
        calls = 0

        def generate(self, wav, **kw):
            M.calls += 1
            assert wav.dtype == np.float32 and wav.shape == (32000,)
            assert kw["granularity"] == "utterance" and kw["extract_embedding"] is False
            return good()

    s = Emotion2vecLargeScorer()
    s._model = M()
    r = s.score(AudioWindow("x", 2, 16000, 48000, b"\x00\x01" * 32000))
    assert (r.session_id, r.epoch, r.start_sample, r.end_sample, r.score_kind) == (
        "x", 2, 16000, 48000, "probability_like")
    assert set(r.scores) == set(LABELS)
