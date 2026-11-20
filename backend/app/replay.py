"""Saved-result replay: manifest/fixture validation and the two local HTTP routes.

The stream validator is also used by tests to check live output semantics.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from .schemas import (
    EVENT_PAYLOADS,
    EventEnvelope,
    ServerEvent,
    parse_json,
    schema_validator,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
NDJSON = "application/x-ndjson"
NO_STORE = {"Cache-Control": "no-store"}
MAX_FIXTURE_BYTES = 8 * 1024 * 1024

NOT_FOUND = {"code": "REPLAY_NOT_FOUND", "message": "That saved fixture is unavailable."}
INVALID = {"code": "REPLAY_INVALID", "message": "A saved fixture failed validation."}


class StreamError(ValueError):
    """A known event violates the v1 stream semantics."""


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split()))


@dataclass
class _Segment:
    text: str
    words: list[dict[str, Any]] | None = None


@dataclass
class _Annotation:
    segment_id: str
    start_word_id: str
    end_word_id: str
    revision: int
    visible: bool = True
    final: bool = False


@dataclass
class StreamValidator:
    """Sequential semantic checks from PROTOCOL 'Validation order' step 3.

    `check` returns one of: accept, ignore_session, ignore_duplicate_or_older,
    ignore_unknown_type; it raises StreamError for invalid known data. A rejected
    event never mutates the validator state.
    """

    session_id: str | None = None
    last_seq: int = 0
    last_issued: int = 0
    segments: dict[str, _Segment] = field(default_factory=dict)
    word_ids: set[str] = field(default_factory=set)
    annotations: dict[str, _Annotation] = field(default_factory=dict)
    events: list[ServerEvent] = field(default_factory=list)

    def check(self, data: Any) -> str:
        try:
            envelope = EventEnvelope.model_validate(data)
        except ValidationError as exc:
            raise StreamError(f"Invalid envelope: {exc.errors()[0]['msg']}") from None
        if self.session_id is None:
            if envelope.type not in ("session.status", "session.reset"):
                raise StreamError("Stream must open with a session status")
        elif envelope.session_id != self.session_id:
            return "ignore_session"
        if envelope.seq <= self.last_seq:
            return "ignore_duplicate_or_older"
        if envelope.issued_at_ms < self.last_issued:
            raise StreamError("Decreasing issued_at_ms")
        if envelope.type not in EVENT_PAYLOADS:
            self._advance(envelope)
            return "ignore_unknown_type"
        try:
            event = ServerEvent.model_validate(data)
        except ValidationError as exc:
            raise StreamError(f"Invalid {envelope.type}: {exc.errors()[0]['msg']}") from None
        commit = getattr(self, "_check_" + envelope.type.replace(".", "_"), None)
        apply = commit(event.payload) if commit else None
        self._advance(envelope)
        if apply:
            apply()
        self.events.append(event)
        return "accept"

    def _advance(self, envelope: EventEnvelope) -> None:
        self.session_id = envelope.session_id
        self.last_seq = envelope.seq
        self.last_issued = envelope.issued_at_ms

    # Each _check_* validates without mutating and returns a mutation closure.

    def _check_transcript_committed(self, p):
        if p.segment_id in self.segments:
            raise StreamError("Duplicate committed segment")
        return lambda: self.segments.__setitem__(p.segment_id, _Segment(p.text))

    def _check_transcript_timed(self, p):
        segment = self.segments.get(p.segment_id)
        if segment is None:
            raise StreamError("Timing for a nonexistent segment")
        if segment.words is not None:
            raise StreamError("Segment already timed")
        ids = [w.word_id for w in p.words]
        if len(set(ids)) != len(ids) or self.word_ids.intersection(ids):
            raise StreamError("Duplicate word ID")
        previous = None
        for word in p.words:
            if not word.end_ms > word.start_ms:
                raise StreamError("Nonpositive word interval")
            if previous and (word.start_ms < previous.start_ms or word.end_ms < previous.end_ms):
                raise StreamError("Out-of-order word times")
            previous = word
        # An explicit timed `text` (provider revision) replaces the committed text.
        target = p.text if p.text is not None else segment.text
        if normalize_text(" ".join(w.text for w in p.words)) != normalize_text(target):
            raise StreamError("Timed words do not match committed text")
        words = [w.model_dump() for w in p.words]

        def apply():
            segment.text = target
            segment.words = words
            self.word_ids.update(ids)
        return apply

    def _anchor_indexes(self, segment_id, start_id, end_id):
        segment = self.segments.get(segment_id)
        if segment is None or segment.words is None:
            raise StreamError("Annotation references an untimed segment")
        ids = [w["word_id"] for w in segment.words]
        if start_id not in ids or end_id not in ids:
            raise StreamError("Annotation references a missing word")
        start, end = ids.index(start_id), ids.index(end_id)
        if start > end:
            raise StreamError("Annotation anchors out of order")
        return segment.words[start], segment.words[end]

    def _check_emotion_updated(self, p):
        first, last = self._anchor_indexes(p.segment_id, p.start_word_id, p.end_word_id)
        if not (math.isclose(p.start_ms, first["start_ms"], abs_tol=1e-6)
                and math.isclose(p.end_ms, last["end_ms"], abs_tol=1e-6)):
            raise StreamError("Annotation interval differs from its outer words")
        if abs(p.support - getattr(p.scores, p.primary)) > 1e-4:
            raise StreamError("Support differs from the primary score")
        if p.blend is not None and p.blend.secondary != p.secondary:
            raise StreamError("Blend secondary disagrees")
        current = self.annotations.get(p.annotation_id)
        if current is None:
            if p.revision != 1:
                raise StreamError("First visible revision must be 1")
            return lambda: self.annotations.__setitem__(
                p.annotation_id, _Annotation(p.segment_id, p.start_word_id, p.end_word_id, 1))
        if current.final:
            raise StreamError("Update after finalization")
        if p.revision <= current.revision:
            raise StreamError("Stale annotation revision")
        if (current.segment_id, current.start_word_id, current.end_word_id) != (
                p.segment_id, p.start_word_id, p.end_word_id):
            raise StreamError("Annotation anchors changed")

        def apply():
            current.revision = p.revision
            current.visible = True
        return apply

    def _check_emotion_retracted(self, p):
        current = self.annotations.get(p.annotation_id)
        if current is None or current.final or not current.visible:
            raise StreamError("Retract requires a visible draft")
        if p.revision <= current.revision:
            raise StreamError("Stale annotation revision")

        def apply():
            current.revision = p.revision
            current.visible = False
        return apply

    def _check_emotion_finalized(self, p):
        current = self.annotations.get(p.annotation_id)
        if current is None or current.final:
            raise StreamError("Finalize requires an unfinalized annotation")
        if p.revision <= current.revision:
            raise StreamError("Stale annotation revision")

        def apply():
            current.revision = p.revision
            current.final = True
        return apply

    def _check_alignment_warning(self, p):
        if p.segment_id not in self.segments:
            raise StreamError("Alignment warning for a nonexistent segment")
        return None


def validate_replay_stream(raw: bytes, duration_ms: int | None = None) -> StreamValidator:
    """Validate a whole saved JSONL fixture before any byte is served."""
    if len(raw) > MAX_FIXTURE_BYTES:
        raise StreamError("Fixture too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise StreamError("Fixture is not UTF-8") from None
    if not text.endswith("\n"):
        raise StreamError("Fixture must end with a newline")
    lines = text[:-1].split("\n")
    validator = StreamValidator()
    first_issued = last_issued = None
    stopped = False
    for index, line in enumerate(lines):
        if not line.strip():
            raise StreamError("Blank line in fixture")
        if stopped:
            raise StreamError("Event after terminal status")
        try:
            data = parse_json(line)
        except ValueError:
            raise StreamError(f"Line {index + 1} is not strict JSON") from None
        outcome = validator.check(data)
        if outcome not in ("accept", "ignore_unknown_type"):
            raise StreamError(f"Line {index + 1}: {outcome}")
        if outcome == "accept":
            event = validator.events[-1]
            if event.type == "session.reset":
                raise StreamError("Replay fixtures hold a single session")
            if event.type == "session.status":
                if event.payload.mode != "replay":
                    raise StreamError("Replay status must use replay mode")
                if index == 0 and event.payload.state != "listening":
                    raise StreamError("Replay must open with listening")
                stopped = event.payload.state == "stopped"
        if index == 0 and not (outcome == "accept" and validator.events[0].type == "session.status"):
            raise StreamError("Replay must open with a status")
        if first_issued is None:
            first_issued = data["issued_at_ms"]
        last_issued = data["issued_at_ms"]
    if not stopped:
        raise StreamError("Replay must end with a stopped status")
    if duration_ms is not None and last_issued - first_issued != duration_ms:
        raise StreamError("Declared duration differs from the event span")
    return validator


class ReplayCatalog:
    """Reads the tracked manifest and fixture files. Nothing is cached, so edits are seen."""

    def __init__(self, root: Path = FIXTURES_ROOT):
        self.root = root

    def manifest(self) -> dict:
        raw = (self.root / "manifest.json").read_bytes()
        try:
            manifest = parse_json(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise StreamError("Manifest is not strict JSON") from None
        errors = list(schema_validator("replay-manifest.schema.json").iter_errors(manifest))
        if errors:
            raise StreamError("Manifest fails its schema")
        ids = [f["id"] for f in manifest["fixtures"]]
        files = [f["file"] for f in manifest["fixtures"]]
        if len(set(ids)) != len(ids) or len(set(files)) != len(files):
            raise StreamError("Manifest IDs and files must be unique")
        if any(f["file"] != f["id"] + ".jsonl" for f in manifest["fixtures"]):
            raise StreamError("Fixture file must equal id + .jsonl")
        if manifest["default_fixture"] not in ids:
            raise StreamError("Default fixture missing")
        return manifest

    def fixture(self, fixture_id: str) -> bytes | None:
        """Return validated bytes, None for an unknown ID; raise StreamError if invalid."""
        manifest = self.manifest()
        entry = next((f for f in manifest["fixtures"] if f["id"] == fixture_id), None)
        if entry is None:
            return None
        path = self.root / entry["file"]
        try:
            raw = path.read_bytes()
        except OSError:
            raise StreamError("Fixture file unreadable") from None
        validate_replay_stream(raw, entry["duration_ms"])
        return raw


def replay_router(catalog: ReplayCatalog) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/replay/manifest")
    def manifest():
        try:
            return JSONResponse(catalog.manifest(), headers=NO_STORE)
        except (StreamError, OSError):
            return JSONResponse(INVALID, status_code=422, headers=NO_STORE)

    @router.get("/api/v1/replay/{fixture_id}")
    def fixture(fixture_id: str):
        try:
            raw = catalog.fixture(fixture_id)
        except (StreamError, OSError):
            return JSONResponse(INVALID, status_code=422, headers=NO_STORE)
        if raw is None:
            return JSONResponse(NOT_FOUND, status_code=404, headers=NO_STORE)
        return Response(raw, media_type=NDJSON, headers=NO_STORE)

    return router
