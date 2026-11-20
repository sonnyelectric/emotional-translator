"""A-02: keyless replay over local HTTP with sequential fixture validation."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.replay import StreamError, StreamValidator, validate_replay_stream
from backend.app.schemas import parse_json, schema_validator

FIXTURES = Path(__file__).resolve().parents[3] / "shared" / "fixtures"
MANIFEST = parse_json((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    with TestClient(create_app(Settings(mode="replay"))) as test_client:
        yield test_client


@pytest.fixture
def copied(tmp_path):
    root = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


def client_for(root):
    return TestClient(create_app(Settings(mode="replay"), fixtures_root=root))


def test_manifest_route(client):
    response = client.get("/api/v1/replay/manifest", headers={"origin": ORIGIN})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.json() == MANIFEST
    schema_validator("replay-manifest.schema.json").validate(response.json())
    assert client.get("/api/v1/replay/manifest").json() == response.json()  # stable catalog


@pytest.mark.parametrize("entry", MANIFEST["fixtures"], ids=lambda e: e["id"])
def test_every_fixture_served_byte_for_byte(client, entry):
    response = client.get(f"/api/v1/replay/{entry['id']}", headers={"origin": ORIGIN})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.content == (FIXTURES / entry["file"]).read_bytes()


def test_foreign_origin_gets_no_cors_grant(client):
    response = client.get("/api/v1/replay/manifest", headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("fixture_id", ["missing", "manifest.json", "replay_demo.jsonl", "...", "REPLAY_DEMO"])
def test_unknown_or_path_ids_rejected(client, fixture_id):
    response = client.get(f"/api/v1/replay/{fixture_id}")
    assert response.status_code == 404
    assert response.json() == {"code": "REPLAY_NOT_FOUND", "message": "That saved fixture is unavailable."}
    schema_validator("http-error.schema.json").validate(response.json())


def test_traversal_never_leaves_route(client):
    assert client.get("/api/v1/replay/../../backend/app/config.py").status_code == 404
    assert client.get("/api/v1/replay/..%2Fmanifest").status_code == 404


def test_health(client):
    assert client.get("/healthz").json() == {"schema_version": "1.0", "status": "ok"}


def test_replay_mode_does_not_import_live_runtime():
    assert "backend.app.adapters.scribe" not in sys.modules
    assert "backend.app.emotion.worker" not in sys.modules
    assert "funasr" not in sys.modules


def corrupt(root, name, mutate):
    path = root / name
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(mutate(lines)) + "\n", encoding="utf-8")


def mutate_event(index, change):
    def mutate(lines):
        event = json.loads(lines[index])
        change(event)
        lines[index] = json.dumps(event, separators=(",", ":"))
        return lines
    return mutate


INVALID_EDITS = {
    "nan": lambda lines: [lines[0].replace('"seq":1', '"seq":NaN')] + lines[1:],
    "truncated": lambda lines: lines[:-1],
    "cross_session": mutate_event(3, lambda e: e.update(session_id="other")),
    "decreasing_time": mutate_event(4, lambda e: e.update(issued_at_ms=1)),
    "duplicate_seq": mutate_event(2, lambda e: e.update(seq=2)),
    "wrong_anchor": mutate_event(8, lambda e: e["payload"].update(start_word_id="seg-2:w4")),
    "support_mismatch": mutate_event(8, lambda e: e["payload"].update(support=0.5)),
    "live_status": mutate_event(0, lambda e: e["payload"].update(mode="live", scribe="connected",
                                                                  emotion_model="ready")),
    "blank_line": lambda lines: lines[:3] + [""] + lines[3:],
    "timed_text_mismatch": mutate_event(4, lambda e: e["payload"]["words"][0].update(text="Fur")),
}


@pytest.mark.parametrize("edit", INVALID_EDITS, ids=str)
def test_invalid_fixture_returns_422_without_startup_crash(copied, edit):
    corrupt(copied, "replay_demo.jsonl", INVALID_EDITS[edit])
    with client_for(copied) as client:
        response = client.get("/api/v1/replay/replay_demo")
        assert response.status_code == 422
        assert response.json()["code"] == "REPLAY_INVALID"
        assert client.get("/api/v1/replay/replay_neutral").status_code == 200


def test_declared_duration_must_match(copied):
    manifest = json.loads((copied / "manifest.json").read_text())
    manifest["fixtures"][0]["duration_ms"] += 1
    (copied / "manifest.json").write_text(json.dumps(manifest))
    with client_for(copied) as client:
        assert client.get("/api/v1/replay/replay_demo").status_code == 422
        assert client.get("/api/v1/replay/manifest").status_code == 200


@pytest.mark.parametrize("change", [
    lambda m: m.update(default_fixture="absent"),
    lambda m: m["fixtures"][1].update(file="replay_demo.jsonl"),
    lambda m: m["fixtures"].append(dict(m["fixtures"][0])),
    lambda m: m.update(source="live"),
])
def test_bad_manifest_returns_422(copied, change):
    manifest = json.loads((copied / "manifest.json").read_text())
    change(manifest)
    (copied / "manifest.json").write_text(json.dumps(manifest))
    with client_for(copied) as client:
        assert client.get("/api/v1/replay/manifest").status_code == 422
        assert client.get("/api/v1/replay/replay_demo").status_code == 422


def test_unparseable_manifest_returns_422(copied):
    (copied / "manifest.json").write_text("{not json")
    with client_for(copied) as client:
        assert client.get("/api/v1/replay/manifest").json()["code"] == "REPLAY_INVALID"


def test_delayed_timing_patches_earlier_segment():
    raw = (FIXTURES / "replay_delayed_timing.jsonl").read_bytes()
    validator = validate_replay_stream(raw, 4850)
    assert validator.segments["seg-1"].words is not None
    assert validator.segments["seg-2"].words is None  # stays plain after the warning


def test_retraction_then_hidden_finalization():
    validator = validate_replay_stream((FIXTURES / "replay_retraction.jsonl").read_bytes())
    annotation = validator.annotations["a-faint"]
    assert (annotation.visible, annotation.final, annotation.revision) == (False, True, 3)


def test_demo_revisions_freeze():
    validator = validate_replay_stream((FIXTURES / "replay_demo.jsonl").read_bytes(), 18600)
    assert validator.annotations["a-seg-2"].revision == 3 and validator.annotations["a-seg-2"].final


STREAM_CASES = [c for c in parse_json((FIXTURES / "invalid" / "cases.json").read_text()) if c["layer"] == "stream"]


@pytest.mark.parametrize("case", STREAM_CASES, ids=lambda c: c["id"])
def test_stream_cases(case):
    validator = StreamValidator()
    for event in case["prefix"]:
        assert validator.check(event) == "accept"
    before = (validator.last_seq, {k: vars(v).copy() for k, v in validator.annotations.items()})
    if case["expected"] == "reject":
        with pytest.raises(StreamError):
            validator.check(case["event"])
        assert (validator.last_seq, {k: vars(v).copy() for k, v in validator.annotations.items()}) == before
    else:
        assert validator.check(case["event"]) == case["expected"]
