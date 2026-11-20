"""Opt-in live session recorder: emitted events -> validated replay fixture + manifest entry."""

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from fakes_model import ANGRY, FakeScorer, FakeWorker
from fakes_scribe import FakeScribeAdapter, Utterance
from live_helpers import ORIGIN, Recorder, command, live_client, live_settings, make_runtime, send_frames

from backend.app.recorder import PROVENANCE_DETAIL, to_replay_lines, write_fixture
from backend.app.replay import FIXTURES_ROOT, ReplayCatalog, validate_replay_stream
from backend.app.schemas import schema_validator

UTTERANCE = Utterance(after_samples=48000, text="I am so angry right now.", basis="unknown",
                      words=[("I", 0.20, 0.40), ("am", 0.45, 0.70), ("so", 0.75, 1.00), ("angry", 1.05, 1.60),
                             ("right", 1.65, 1.90), ("now.", 1.95, 2.40)])


@pytest.fixture
def fixtures_dir(tmp_path) -> Path:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_ROOT, target)
    return target


def _live_run(settings, frames=125):
    runtime = make_runtime(FakeScribeAdapter(utterances=[UTTERANCE]), settings=settings,
                           worker=FakeWorker(FakeScorer(lambda w: ANGRY)))
    with live_client(runtime) as client, client.websocket_connect("/ws/v1/session", headers=ORIGIN) as ws:
        rec = Recorder(ws)
        ws.send_text(command("session.start"))
        rec.until_type("session.status", state="listening")
        send_frames(ws, frames)
        if frames:
            rec.until_type("emotion.finalized")
        ws.send_text(command("session.stop"))
        rec.until_type("session.status", state="stopped")
    return rec


def test_live_session_is_recorded_as_a_valid_labelled_fixture(fixtures_dir):
    out = fixtures_dir / "replay_live_recorded.jsonl"
    rec = _live_run(live_settings(scribe_timestamp_basis="connection", record_session_events=out))
    assert out.exists()
    catalog = ReplayCatalog(fixtures_dir)
    manifest = catalog.manifest()  # schema + uniqueness checks
    entry = next(f for f in manifest["fixtures"] if f["id"] == "replay_live_recorded")
    assert entry["provenance"] == "recorded_result"
    assert entry["provenance_detail"] == PROVENANCE_DETAIL == \
        "recorded live session (text, timestamps, scores; no audio)"
    assert entry["recorded_on"] == dt.date.today().isoformat()
    assert manifest["source"] == "saved_result" and manifest["default_fixture"] == "replay_live_recorded"
    assert len(manifest["fixtures"]) == 8  # the 7 synthetic fixtures are kept
    raw = catalog.fixture("replay_live_recorded")  # full replay validation, as the endpoint does
    lines = [json.loads(line) for line in raw.decode().splitlines()]
    for line in lines:
        schema_validator("server-event.schema.json").validate(line)
    # Same transcript, timing and annotation payloads the client saw live; no audio anywhere.
    live = {e["type"]: e["payload"] for e in rec.events if e["type"] != "session.status"}
    saved = {e["type"]: e["payload"] for e in lines if e["type"] != "session.status"}
    assert saved["transcript.committed"] == live["transcript.committed"]
    assert saved["transcript.timed"] == live["transcript.timed"]
    assert saved["emotion.updated"] == live["emotion.updated"]
    assert [lines[0]["payload"]["state"], lines[-1]["payload"]["state"]] == ["listening", "stopped"]
    assert {line["payload"].get("mode") for line in lines if line["type"] == "session.status"} == {"replay"}
    assert "audio" not in raw.decode().lower()


def test_no_flag_writes_nothing(fixtures_dir):
    before = sorted(p.name for p in fixtures_dir.iterdir())
    _live_run(live_settings(scribe_timestamp_basis="connection"))
    assert sorted(p.name for p in fixtures_dir.iterdir()) == before


def test_session_without_a_commit_writes_nothing(fixtures_dir):
    out = fixtures_dir / "replay_live_recorded.jsonl"
    manifest_before = (fixtures_dir / "manifest.json").read_text()
    _live_run(live_settings(record_session_events=out), frames=0)
    assert not out.exists()
    assert (fixtures_dir / "manifest.json").read_text() == manifest_before


def _ev(seq, issued, kind, payload):
    return {"schema_version": "1.0", "type": kind, "session_id": "s-live", "seq": seq, "issued_at_ms": issued,
            "payload": payload}


LIVE_STATUS = {"mode": "live", "scribe": "connected", "emotion_model": "ready", "detail": None}


def test_conversion_drops_live_statuses_and_stops_at_an_error(tmp_path):
    events = [
        _ev(1, 0, "session.status", {"state": "connecting", **LIVE_STATUS, "scribe": "connecting"}),
        _ev(2, 300, "session.status", {"state": "listening", **LIVE_STATUS, "sample_rate_hz": 16000,
                                      "channels": 1, "sample_format": "s16le"}),
        _ev(3, 900, "transcript.committed", {"segment_id": "seg-1", "text": "Hello there.",
                                            "timing_state": "pending", "language_code": None}),
        _ev(4, 1000, "session.status", {"state": "paused", **LIVE_STATUS}),
        _ev(5, 1500, "session.error", {"code": "SCRIBE_AUTH", "message": "x", "recoverable": False}),
        _ev(6, 1600, "transcript.committed", {"segment_id": "seg-2", "text": "Lost.",
                                             "timing_state": "pending", "language_code": None}),
    ]
    lines = to_replay_lines(events, "replay_live_recorded")
    assert [(e["type"], e["issued_at_ms"]) for e in lines] == [
        ("session.status", 0), ("transcript.committed", 600), ("session.status", 600)]
    assert [e["seq"] for e in lines] == [1, 2, 3]
    raw = "".join(json.dumps(e) + "\n" for e in lines).encode()
    validate_replay_stream(raw, 600)
    out = tmp_path / "replay_live_recorded.jsonl"
    assert write_fixture(events, out, today=dt.date(2026, 11, 20))
    entry = json.loads((tmp_path / "manifest.json").read_text())["fixtures"][0]
    assert entry["recorded_on"] == "2026-11-20" and entry["case_name"] == "Recorded live session, 2026-11-20"


def test_bad_record_path_is_rejected():
    with pytest.raises(ValueError):
        live_settings(record_session_events="out.txt")
