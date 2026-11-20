"""Opt-in live session recorder (RECORD_SESSION_EVENTS=/path/to/replay_<name>.jsonl).

Records the server events one live session emitted (text, word timestamps, model scores
and annotations; never audio) and, when the session ends, writes them as a replay fixture
plus a manifest entry labelled as a recorded live session. Nothing is stored unless the
flag is set. Conversion rules (needed because replay rejects live status payloads):

- every live `session.status` is dropped and replaced by one replay `listening` status at
  the first live `listening` and one replay `stopped` status at the end;
- `session.reset` and `session.error` are dropped (a fixture holds one session; an error
  ends the recording at that point);
- session id becomes the fixture id, `seq` is renumbered from 1, and `issued_at_ms` is
  rebased so the fixture starts at 0. Payloads are otherwise byte-for-byte what was sent.

The result is validated with the same checks the replay endpoint uses before anything is
written. An invalid or empty recording writes nothing and logs why.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path

from .replay import StreamError, validate_replay_stream
from .schemas import SCHEMA_VERSION, schema_validator

log = logging.getLogger(__name__)

PROVENANCE_DETAIL = "recorded live session (text, timestamps, scores; no audio)"
KEEP = {"transcript.partial", "transcript.committed", "transcript.timed", "emotion.updated",
        "emotion.retracted", "emotion.finalized", "alignment.warning", "session.warning"}
REPLAY_STATUS = {"mode": "replay", "scribe": "not_required", "emotion_model": "not_required", "detail": None}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def fixture_id_for(path: Path) -> str:
    fixture_id = path.stem
    if path.suffix != ".jsonl" or not ID_PATTERN.match(fixture_id):
        raise ValueError("RECORD_SESSION_EVENTS must name a .jsonl file like replay_live_recorded.jsonl "
                         "(lowercase letters, digits and underscores)")
    return fixture_id


def to_replay_lines(events: list[dict], fixture_id: str) -> list[dict] | None:
    """Convert emitted live events to replay fixture events, or None if nothing to keep."""
    start = next((e["issued_at_ms"] for e in events if e["type"] == "session.status"
                  and e["payload"].get("state") == "listening"), None)
    body: list[tuple[str, int, dict]] = []
    for event in events:
        if event["type"] == "session.error":
            break
        if event["type"] in KEEP and start is not None:
            body.append((event["type"], max(0, event["issued_at_ms"] - start), event["payload"]))
    if not any(kind == "transcript.committed" for kind, _, _ in body):
        return None
    end = max([issued for _, issued, _ in body] + [1])
    stream = [("session.status", 0, {"state": "listening", **REPLAY_STATUS}), *body,
              ("session.status", end, {"state": "stopped", **REPLAY_STATUS})]
    return [{"schema_version": SCHEMA_VERSION, "type": kind, "session_id": fixture_id.replace("_", "-"),
             "seq": index, "issued_at_ms": issued, "payload": payload}
            for index, (kind, issued, payload) in enumerate(stream, start=1)]


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_fixture(events: list[dict], path: Path, today: dt.date | None = None) -> bool:
    """Validate and write the fixture and its manifest entry. Returns True if written."""
    fixture_id = fixture_id_for(path)
    lines = to_replay_lines(events, fixture_id)
    if lines is None:
        log.warning("Session recorder: no committed transcript, nothing written to %s", path)
        return False
    raw = "".join(json.dumps(line, separators=(",", ":"), ensure_ascii=False) + "\n" for line in lines)
    duration = lines[-1]["issued_at_ms"]
    try:
        validate_replay_stream(raw.encode("utf-8"), duration)
    except StreamError as exc:
        log.error("Session recorder: recording failed replay validation (%s); nothing written", exc)
        return False
    date = (today or dt.date.today()).isoformat()
    entry = {"id": fixture_id, "file": path.name, "case_name": f"Recorded live session, {date}",
             "duration_ms": duration, "provenance": "recorded_result",
             "provenance_detail": PROVENANCE_DETAIL, "recorded_on": date}
    manifest_path = path.parent / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["fixtures"] = [f for f in manifest["fixtures"] if f["id"] != fixture_id] + [entry]
    else:
        manifest = {"schema_version": SCHEMA_VERSION, "source": "saved_result", "fixtures": [entry]}
    # A real recording is the honest fallback, so it becomes the default replay.
    manifest["default_fixture"] = fixture_id
    manifest = {k: manifest[k] for k in ("schema_version", "source", "default_fixture", "fixtures")}
    errors = list(schema_validator("replay-manifest.schema.json").iter_errors(manifest))
    if errors:
        log.error("Session recorder: manifest entry fails its schema (%s); nothing written", errors[0].message)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, raw.encode("utf-8"))
    _write_atomic(manifest_path, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    log.info("Session recorder: wrote %d events (%d ms) to %s and updated %s",
             len(lines), duration, path, manifest_path)
    return True


class SessionRecorder:
    """Collects one session's emitted events; `finish` writes them once."""

    def __init__(self, path: Path):
        fixture_id_for(path)  # fail fast on a bad name
        self.path = path
        self.events: list[dict] = []
        self.finished = False

    def record(self, event: dict) -> None:
        if not self.finished:
            self.events.append(event)

    def finish(self) -> bool:
        if self.finished:
            return False
        self.finished = True
        try:
            return write_fixture(self.events, self.path)
        except (OSError, ValueError) as exc:
            log.error("Session recorder: could not write %s (%s)", self.path, exc)
            return False
