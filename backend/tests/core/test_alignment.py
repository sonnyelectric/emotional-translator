"""A-04: commit/timed matching, overlap weighting, phrase grouping and finalization."""

import pytest
from fakes_model import ANGRY, NEUTRAL, SAD, FakePolicy, vector

from backend.app.alignment.phrases import PhraseEngine, recency, word_vector
from backend.app.alignment.segments import SegmentTracker, TimedSegment, TimedWord
from backend.app.audio.clock import Epoch
from backend.app.audio_ai_ports import ScoredWindow, ScribeNotice, TimedToken, WindowNotice
from backend.app.config import Settings
from backend.app.replay import StreamValidator

SETTINGS = Settings()


# ---- segment tracker -----------------------------------------------------------------
def notice(kind, epoch=1, **kw):
    return ScribeNotice(epoch=epoch, kind=kind, **kw)


def tokens(*items):
    return tuple(TimedToken(t, s, e) for t, s, e in items)


def epoch(origin=0, sent_end=160000, number=1):
    return Epoch(number, origin=origin, forwarded_end=sent_end, sent_end=sent_end)


def test_partial_replaces_then_commit_then_new_partial_id():
    tracker = SegmentTracker()
    a = tracker.on_partial(notice("partial", text="I thought"))
    b = tracker.on_partial(notice("partial", text="I thought you"))
    assert tracker.on_partial(notice("partial", text="I thought you")) == []  # repeated keepalive
    assert a[0][1]["partial_id"] == b[0][1]["partial_id"] == "p-1"
    commit = tracker.on_commit(notice("commit", text="I thought you would call."))
    assert commit == [("transcript.committed", {"segment_id": "seg-1", "text": "I thought you would call.",
                                                "timing_state": "pending", "language_code": None})]
    assert tracker.on_partial(notice("partial", text="Maybe"))[0][1]["partial_id"] == "p-2"


def test_delayed_timed_patches_earlier_segment_and_keeps_partial():
    tracker = SegmentTracker(timestamp_basis="connection")
    tracker.on_commit(notice("commit", text="I thought you would call."))
    tracker.on_partial(notice("partial", text="Maybe the signal"))
    events, segment = tracker.on_timed(notice("timed", tokens=tokens(
        ("I", 1600, 5120), ("thought", 5312, 8832), ("you", 9024, 12544), ("would", 12736, 16256),
        ("call.", 16448, 20160))), epoch())
    assert events[0][0] == "transcript.timed" and events[0][1]["segment_id"] == "seg-1"
    assert events[0][1]["words"][0] == {"word_id": "seg-1:w0", "text": "I", "start_ms": 100, "end_ms": 320}
    assert segment.words[-1].word_id == "seg-1:w4"
    assert tracker.partial_text == "Maybe the signal"


def test_repeated_identical_commits_are_both_kept_fifo():
    tracker = SegmentTracker(timestamp_basis="connection")
    first = tracker.on_commit(notice("commit", text="Yes."))
    second = tracker.on_commit(notice("commit", text="Yes."))
    assert [first[0][1]["segment_id"], second[0][1]["segment_id"]] == ["seg-1", "seg-2"]
    e1, _ = tracker.on_timed(notice("timed", tokens=tokens(("Yes.", 100, 900))), epoch())
    e2, _ = tracker.on_timed(notice("timed", tokens=tokens(("Yes.", 20000, 21000))), epoch())
    assert [e1[0][1]["segment_id"], e2[0][1]["segment_id"]] == ["seg-1", "seg-2"]
    # A duplicated timed notice has no pending commit left: dropped, never a second append.
    assert tracker.on_timed(notice("timed", tokens=tokens(("Yes.", 100, 900))), epoch()) == ([], None)
    assert tracker.counters["orphan_timed"] == 1


def test_duplicate_provider_key_suppressed():
    tracker = SegmentTracker()
    assert tracker.on_commit(notice("commit", text="Hi.", provider_commit_key="k1"))
    assert tracker.on_commit(notice("commit", text="Hi.", provider_commit_key="k1")) == []


@pytest.mark.parametrize("configured", ["unknown", "segment"])
def test_configured_basis_without_origin_never_guesses(configured):
    # "segment" needs a per-commit origin that Scribe does not supply, so it still warns.
    tracker = SegmentTracker(timestamp_basis=configured)
    tracker.on_commit(notice("commit", text="Hello there."))
    events, segment = tracker.on_timed(notice("timed", timestamp_basis="unknown", tokens=tokens(
        ("Hello", 0, 4000), ("there.", 4100, 8000))), epoch())
    assert segment is None and events[0][1]["code"] == "ALIGNMENT_BASIS_UNKNOWN"


def test_timestamp_basis_setting_values():
    assert Settings().scribe_timestamp_basis == "unknown"
    assert Settings(scribe_timestamp_basis="provider").scribe_timestamp_basis == "unknown"  # legacy alias
    assert Settings(scribe_timestamp_basis="connection").scribe_timestamp_basis == "connection"
    with pytest.raises(ValueError):
        Settings(scribe_timestamp_basis="seconds")


def test_unknown_basis_warns_instead_of_guessing():
    tracker = SegmentTracker()  # honour provider basis
    tracker.on_commit(notice("commit", text="Hello there."))
    events, segment = tracker.on_timed(notice("timed", timestamp_basis="unknown", tokens=tokens(
        ("Hello", 0, 4000), ("there.", 4100, 8000))), epoch())
    assert segment is None
    assert events == [("alignment.warning", {"segment_id": "seg-1", "code": "ALIGNMENT_BASIS_UNKNOWN",
                                             "message": events[0][1]["message"]})]


def test_unknown_basis_with_connection_override_uses_epoch_origin():
    tracker = SegmentTracker(timestamp_basis="connection")
    tracker.on_commit(notice("commit", text="Hello there."))
    _, segment = tracker.on_timed(notice("timed", tokens=tokens(("Hello", 0, 4000), ("there.", 4100, 8000))),
                                  epoch(origin=32000, sent_end=48000))
    assert (segment.words[0].start_sample, segment.words[1].end_sample) == (32000, 40000)


def test_segment_basis_adds_observed_origin_once():
    tracker = SegmentTracker()
    tracker.on_commit(notice("commit", text="Hello there."))
    _, segment = tracker.on_timed(notice("timed", timestamp_basis="segment", segment_origin_samples=16000,
                                         tokens=tokens(("Hello", 0, 4000), ("there.", 4100, 8000))),
                                  epoch(origin=32000, sent_end=64000))
    assert segment.words[0].start_sample == 48000


def test_spacing_tokens_are_ignored():
    tracker = SegmentTracker(timestamp_basis="connection")
    tracker.on_commit(notice("commit", text="Hello there."))
    events, segment = tracker.on_timed(notice("timed", tokens=tokens(
        ("Hello", 0, 4000), (" ", 4000, 4100), ("there.", 4100, 8000))), epoch())
    assert [w.word_id for w in segment.words] == ["seg-1:w0", "seg-1:w1"]


def test_segment_basis_without_origin_is_unresolvable():
    tracker = SegmentTracker()
    tracker.on_commit(notice("commit", text="Hello."))
    events, segment = tracker.on_timed(notice("timed", timestamp_basis="segment",
                                              tokens=tokens(("Hello.", 0, 4000))), epoch())
    assert segment is None and events[0][1]["code"] == "ALIGNMENT_BASIS_UNKNOWN"


@pytest.mark.parametrize("bad_tokens", [
    tokens(("Hello", 0, 4000), ("there.", 4100, 200000)),  # beyond sent audio
    tokens(("Hello", 4000, 4000), ("there.", 4100, 8000)),  # nonpositive
    tokens(("Hello", 5000, 6000), ("there.", 4100, 8000)),  # out of order
    tokens(("Hello", 0, 4000), ("their.", 4100, 8000)),  # text mismatch
])
def test_invalid_word_timing_warns_mismatch(bad_tokens):
    tracker = SegmentTracker(timestamp_basis="connection")
    tracker.on_commit(notice("commit", text="Hello there."))
    events, segment = tracker.on_timed(notice("timed", tokens=bad_tokens), epoch(sent_end=160000))
    assert segment is None and events[0][1]["code"] == "ALIGNMENT_TIMESTAMP_MISMATCH"


def test_missing_tokens_and_epoch_expiry_warn_missing():
    tracker = SegmentTracker()
    tracker.on_commit(notice("commit", text="One."))
    tracker.on_commit(notice("commit", text="Two."))
    events, _ = tracker.on_timed(notice("timed", tokens=()), epoch())
    assert events[0][1]["code"] == "ALIGNMENT_TIMESTAMPS_MISSING"
    expired = tracker.expire_epoch(1)
    assert [(e[1]["segment_id"], e[1]["code"]) for e in expired] == [("seg-2", "ALIGNMENT_TIMESTAMPS_MISSING")]


# ---- phrase engine --------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def words(segment_id, *items):
    return [TimedWord(f"{segment_id}:w{i}", text, s, e) for i, (text, s, e) in enumerate(items)]


def scored(start, scores, epoch_number=1):
    window = ScoredWindow("s", epoch_number, start, start + 32000, "probability_like", scores)
    return WindowNotice("s", epoch_number, start, start + 32000, "scored", 0.0, 1.0, 0.5, window)


def engine(audio_end=160000, origin=0):
    clock = Clock()
    e = PhraseEngine(SETTINGS, FakePolicy(), now=clock)
    e.begin_epoch(1, origin)
    e.extend_epoch(1, audio_end)
    return e, clock


SENTENCE = words("seg-1", ("I", 3200, 6400), ("am", 7000, 9000), ("so", 9600, 12000), ("angry.", 12800, 20800))


def test_recency_and_overlap_weights():
    assert recency(16000, 16000) == 1
    assert recency(0, 16000) == pytest.approx(0.75)  # 1000 ms apart
    assert recency(0, 64000) == pytest.approx(0.5)  # capped at 2 s
    word = TimedWord("w", "x", 8000, 16000)
    a, b = vector(angry=0.8, neutral=0.1), vector(sad=0.8, neutral=0.1)
    result = word_vector(word, [(0, 32000, a), (16000, 48000, b), (-16000, 16000, None)])
    assert result["angry"] == pytest.approx(0.8)  # b does not overlap; the unusable window weighs 0
    result = word_vector(TimedWord("w", "x", 8000, 24000), [(0, 32000, a), (16000, 48000, b)])
    wa = 1.0 * recency(16000, 16000)  # full overlap, same midpoint
    wb = 0.5 * recency(32000, 16000)  # half overlap, 1000 ms away
    assert result["angry"] == pytest.approx((wa * a["angry"] + wb * b["angry"]) / (wa + wb))
    assert sum(result.values()) == pytest.approx(1.0)


def run(order):
    e, _ = engine()
    events = []
    windows = [scored(0, ANGRY), scored(16000, ANGRY)]
    if order == "model_first":
        for w in windows:
            events += e.window_notice(w)
        events += e.add_segment(TimedSegment("seg-1", 1, SENTENCE))
    else:
        events += e.add_segment(TimedSegment("seg-1", 1, SENTENCE))
        assert events == []  # plain until evidence settles
        for w in windows:
            events += e.window_notice(w)
    return events


def test_arrival_order_gives_same_annotations():
    model_first, timed_first = run("model_first"), run("timed_first")
    assert model_first == timed_first
    kinds = [k for k, _ in model_first]
    assert kinds == ["emotion.updated", "emotion.finalized"]
    payload = model_first[0][1]
    assert (payload["start_word_id"], payload["end_word_id"]) == ("seg-1:w0", "seg-1:w3")
    assert (payload["start_ms"], payload["end_ms"]) == (200, 1300)
    assert model_first[1][1] == {"annotation_id": payload["annotation_id"], "revision": 2}


def validate_against_stream(segment_words, events):
    """Annotations must satisfy the shared stream semantics against their timed words."""
    v = StreamValidator()
    seq = 1
    v.check({"schema_version": "1.0", "type": "session.status", "session_id": "s", "seq": seq, "issued_at_ms": 0,
             "payload": {"state": "listening", "mode": "replay", "scribe": "not_required",
                         "emotion_model": "not_required", "detail": None}})
    by_segment = {}
    for w in segment_words:
        by_segment.setdefault(w.word_id.split(":")[0], []).append(w)
    for segment_id, ws in by_segment.items():
        for kind, payload in [("transcript.committed", {"segment_id": segment_id, "text": " ".join(w.text for w in ws),
                                                        "timing_state": "pending", "language_code": None}),
                              ("transcript.timed", {"segment_id": segment_id, "language_code": None, "words": [
                                  {"word_id": w.word_id, "text": w.text, "start_ms": w.start_sample / 16,
                                   "end_ms": w.end_sample / 16} for w in ws]})]:
            seq += 1
            assert v.check({"schema_version": "1.0", "type": kind, "session_id": "s", "seq": seq,
                            "issued_at_ms": 0, "payload": payload}) == "accept"
    for kind, payload in events:
        seq += 1
        assert v.check({"schema_version": "1.0", "type": kind, "session_id": "s", "seq": seq,
                        "issued_at_ms": 0, "payload": payload}) == "accept"


def test_punctuation_and_pause_boundaries():
    e, _ = engine()
    ws = words("seg-1", ("Fine,", 1600, 4800), ("then", 5000, 8000), ("go", 8200, 11000),
               ("now", 20000, 24000), ("please", 24200, 28000))  # 562 ms pause before "now"
    events = []
    for start in (0, 16000):
        events += e.window_notice(scored(start, ANGRY))
    events += e.add_segment(TimedSegment("seg-1", 1, ws))
    spans = [(p["start_word_id"], p["end_word_id"]) for k, p in events if k == "emotion.updated"]
    assert spans == [("seg-1:w0", "seg-1:w0"), ("seg-1:w1", "seg-1:w2"), ("seg-1:w3", "seg-1:w4")]
    validate_against_stream(ws, events)


def test_sustained_cue_change_splits_phrase():
    e, _ = engine(audio_end=200000)
    ws = words("seg-1", ("a", 2000, 6000), ("b", 6200, 10000), ("c", 10200, 14000),
               ("d", 50000, 54000), ("e", 54200, 58000), ("f", 58200, 62000))
    ws = [TimedWord(w.word_id, w.text, w.start_sample, w.end_sample) for w in ws]
    # keep one coarse group: no punctuation, close the 36000-sample gap by raising the threshold
    settings = Settings(phrase_gap_ms=5000)
    e = PhraseEngine(settings, FakePolicy(), now=Clock())
    e.begin_epoch(1, 0)
    e.extend_epoch(1, 200000)
    events = []
    for start in range(0, 64000, 16000):
        events += e.window_notice(scored(start, ANGRY if start < 16000 else SAD))
    events += e.add_segment(TimedSegment("seg-1", 1, ws))
    updates = [p for k, p in events if k == "emotion.updated"]
    assert [(p["primary"], p["start_word_id"], p["end_word_id"]) for p in updates] == [
        ("angry", "seg-1:w0", "seg-1:w2"), ("sad", "seg-1:w3", "seg-1:w5")]
    validate_against_stream(ws, events)


def test_neutral_leaves_phrase_plain():
    e, _ = engine()
    events = [ev for w in (scored(0, NEUTRAL), scored(16000, NEUTRAL)) for ev in e.window_notice(w)]
    events += e.add_segment(TimedSegment("seg-1", 1, SENTENCE))
    assert events == [] and e.pending_segments() == 0


def test_no_evidence_stays_plain_and_deadline_finalizes():
    e, clock = engine()
    assert e.add_segment(TimedSegment("seg-1", 1, SENTENCE)) == []
    clock.t = 10.0
    assert e.tick() == []  # deadline reached, but no evidence: no cloud ever
    assert e.pending_segments() == 0 and e.counters["deadline_finalizations"] == 1


def test_deadline_uses_best_available_evidence():
    e, clock = engine()
    e.window_notice(scored(0, ANGRY))  # [16000, 48000) never settles
    assert e.add_segment(TimedSegment("seg-1", 1, SENTENCE)) == []
    clock.t = 10.0
    kinds = [k for k, _ in e.tick()]
    assert kinds == ["emotion.updated", "emotion.finalized"]


def test_finalized_history_is_immutable_and_late_results_counted():
    e, _ = engine()
    events = run("model_first")
    assert events
    e2, _ = engine()
    for w in (scored(0, ANGRY), scored(16000, ANGRY)):
        e2.window_notice(w)
    e2.add_segment(TimedSegment("seg-1", 1, SENTENCE))
    assert e2.window_notice(scored(0, SAD)) == []
    assert e2.counters["late_results_discarded"] == 1


def test_windows_only_bind_within_their_epoch():
    e, _ = engine()
    e.begin_epoch(2, 160000)
    e.extend_epoch(2, 240000)
    e.window_notice(scored(0, ANGRY, epoch_number=1))
    e.window_notice(scored(16000, ANGRY, epoch_number=1))
    later = words("seg-2", ("Hi", 163200, 166400), ("there.", 167000, 170000))
    assert e.add_segment(TimedSegment("seg-2", 2, later)) == []  # epoch-1 windows never apply
    events = e.window_notice(scored(160000, SAD, epoch_number=2))
    assert [p["primary"] for k, p in events if k == "emotion.updated"] == ["sad"]


def test_closed_epoch_completes_without_unproduced_windows():
    e, _ = engine(audio_end=24000)  # audio stopped before any full window
    assert e.add_segment(TimedSegment("seg-1", 1, SENTENCE)) == []
    assert e.pending_segments() == 1
    assert e.close_epoch(1) == [] and e.pending_segments() == 0


def test_invalid_scores_are_unusable():
    e, _ = engine()
    bad = dict(ANGRY)
    bad.pop("unknown")
    e.window_notice(scored(0, bad))
    assert e.counters["invalid_scores"] == 1
