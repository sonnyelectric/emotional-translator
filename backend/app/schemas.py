"""Wire validation at the JSON boundary. Session semantics belong to callers."""

import json
import math
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializeAsAny,
    StringConstraints,
    field_validator,
    model_validator,
)
from referencing import Registry, Resource

SCHEMA_VERSION = "1.0"
SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "shared" / "schemas" / "v1"
MAX_SAFE_INTEGER = 2**53 - 1
WireId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}\z")]
WireType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+\z", max_length=100)]
Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,95}\z")]
Message = Annotated[str, Field(min_length=1, max_length=512)]
Text = Annotated[str, Field(min_length=1)]
Language = Annotated[str, Field(min_length=1, max_length=35)] | None


def normalize_json_integer(value: Any) -> Any:
    # Draft 2020-12 treats integral JSON decimals as integers.
    if isinstance(value, float) and value.is_integer() and 0 <= value <= MAX_SAFE_INTEGER:
        return int(value)
    return value


PositiveInteger = Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER), BeforeValidator(normalize_json_integer)]
NonnegativeInteger = Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER), BeforeValidator(normalize_json_integer)]
AudioMs = Annotated[float, Field(ge=0, le=MAX_SAFE_INTEGER)]
UnitInterval = Annotated[float, Field(ge=0, le=1)]
VisibleCategory = Literal["angry", "disgusted", "fearful", "happy", "sad", "surprised"]

PALETTE = {
    "angry": ("jagged", "#DC4545"),
    "disgusted": ("wavy", "#68A876"),
    "fearful": ("trembling", "#9975D8"),
    "happy": ("radial", "#EDB94B"),
    "sad": ("rounded", "#478CD4"),
    "surprised": ("burst", "#EF9858"),
}


def reject_nonfinite_token(token: str) -> None:
    raise ValueError(f"Non-finite JSON token: {token}")


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def parse_json(raw: str) -> Any:
    return json.loads(raw, parse_constant=reject_nonfinite_token, parse_float=finite_float)


@cache
def schema_documents() -> dict[str, dict]:
    documents = {path.name: parse_json(path.read_text(encoding="utf-8"))
                 for path in SCHEMA_ROOT.glob("*.schema.json")}
    for document in documents.values():
        Draft202012Validator.check_schema(document)
    return documents


@cache
def schema_registry() -> Registry:
    return Registry().with_resources(
        (document["$id"], Resource.from_contents(document))
        for document in schema_documents().values()
    ).crawl()


@cache
def schema_validator(filename: str) -> Draft202012Validator:
    return Draft202012Validator(schema_documents()[filename], registry=schema_registry())


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EmptyPayload(WireModel):
    pass


class StartPayload(WireModel):
    mode: Literal["live"]


class CommandEnvelope(WireModel):
    schema_version: Literal["1.0"]
    type: WireType
    payload: dict[str, Any]


class ClientCommand(CommandEnvelope):
    type: Literal["session.start", "session.pause", "session.resume", "session.stop", "session.reset"]
    payload: StartPayload | EmptyPayload

    @model_validator(mode="after")
    def check_payload(self):
        if (self.type == "session.start") != isinstance(self.payload, StartPayload):
            raise ValueError("Incorrect payload for command")
        return self


class EventEnvelope(WireModel):
    schema_version: Literal["1.0"]
    type: WireType
    session_id: WireId
    seq: PositiveInteger
    issued_at_ms: NonnegativeInteger
    payload: dict[str, Any]


class StatusPayload(WireModel):
    state: Literal["idle", "connecting", "listening", "paused", "stopping", "stopped", "error"]
    mode: Literal["live", "replay"]
    scribe: Literal["disconnected", "connecting", "connected", "reconnecting", "failed", "not_required"]
    emotion_model: Literal["loading", "ready", "degraded", "failed", "not_required"]
    detail: Message | None
    sample_rate_hz: Literal[16000] | None = None
    channels: Literal[1] | None = None
    sample_format: Literal["s16le"] | None = None

    @field_validator("sample_rate_hz", "channels", "sample_format", mode="before")
    @classmethod
    def check_format_constant(cls, value):
        if value is None or isinstance(value, bool):
            raise ValueError("Invalid PCM format")
        return value

    @model_validator(mode="after")
    def check_mode(self):
        fields = {"sample_rate_hz", "channels", "sample_format"}
        present = self.model_fields_set & fields
        required = fields if self.mode == "live" and self.state == "listening" else set()
        if present != required:
            raise ValueError("PCM format fields must match session mode and state")
        replay = self.mode == "replay"
        if (self.scribe == "not_required") != replay or (self.emotion_model == "not_required") != replay:
            raise ValueError("Service status must match session mode")
        return self


class PartialPayload(WireModel):
    partial_id: WireId
    text: str
    language_code: Language


class CommittedPayload(WireModel):
    segment_id: WireId
    text: Text
    timing_state: Literal["pending"]
    language_code: Language


class Word(WireModel):
    word_id: WireId
    text: Text
    start_ms: AudioMs
    end_ms: AudioMs


class TimedPayload(WireModel):
    segment_id: WireId
    language_code: Language
    words: Annotated[list[Word], Field(min_length=1)]
    # Present only when the provider's timed words differ from the committed text in more
    # than case, punctuation or spacing: the timed text then replaces the segment text.
    text: Text | None = None

    @field_validator("text", mode="before")
    @classmethod
    def text_omitted_not_null(cls, value):
        if value is None:
            raise ValueError("text must be omitted, not null")
        return value

    @field_validator("words")
    @classmethod
    def unique_words(cls, words):
        if len({(w.word_id, w.text, w.start_ms, w.end_ms) for w in words}) != len(words):
            raise ValueError("Duplicate word objects")
        return words


class Scores(WireModel):
    angry: UnitInterval
    disgusted: UnitInterval
    fearful: UnitInterval
    happy: UnitInterval
    neutral: UnitInterval
    other: UnitInterval
    sad: UnitInterval
    surprised: UnitInterval
    unknown: UnitInterval


class RevisionPayload(WireModel):
    annotation_id: WireId
    revision: PositiveInteger


class Blend(WireModel):
    secondary: VisibleCategory
    weight: Annotated[float, Field(gt=0, le=0.5)]


class AnnotationPayload(RevisionPayload):
    segment_id: WireId
    start_word_id: WireId
    end_word_id: WireId
    start_ms: AudioMs
    end_ms: AudioMs
    state: Literal["draft"]
    primary: VisibleCategory
    secondary: VisibleCategory | None
    scores: Scores
    support: UnitInterval
    visual_intensity: UnitInterval
    opacity: Annotated[float, Field(gt=0, le=1)]
    shape: str
    color: str
    blend: Blend | None

    @model_validator(mode="after")
    def check_presentation(self):
        if (self.shape, self.color) != PALETTE[self.primary]:
            raise ValueError("Shape and color must match the primary category")
        if self.secondary == self.primary or (self.secondary is None) != (self.blend is None):
            raise ValueError("Invalid secondary category or blend presence")
        return self


class NoticePayload(WireModel):
    code: Code
    message: Message


class AlignmentWarningPayload(NoticePayload):
    segment_id: WireId


class SessionWarningPayload(NoticePayload):
    recoverable: Literal[True]

    @field_validator("recoverable", mode="before")
    @classmethod
    def check_boolean(cls, value):
        if type(value) is not bool:
            raise ValueError("Expected a JSON boolean")
        return value


class SessionErrorPayload(SessionWarningPayload):
    recoverable: Literal[False]


EVENT_PAYLOADS: dict[str, type[WireModel]] = {
    "session.status": StatusPayload,
    "transcript.partial": PartialPayload,
    "transcript.committed": CommittedPayload,
    "transcript.timed": TimedPayload,
    "emotion.updated": AnnotationPayload,
    "emotion.retracted": RevisionPayload,
    "emotion.finalized": RevisionPayload,
    "alignment.warning": AlignmentWarningPayload,
    "session.warning": SessionWarningPayload,
    "session.error": SessionErrorPayload,
    "session.reset": EmptyPayload,
}
COMMAND_TYPES = {"session.start", "session.pause", "session.resume", "session.stop", "session.reset"}


class ServerEvent(EventEnvelope):
    payload: SerializeAsAny[WireModel]

    @model_validator(mode="before")
    @classmethod
    def check_payload(cls, data):
        envelope = EventEnvelope.model_validate(data)
        model = EVENT_PAYLOADS.get(envelope.type)
        if model is None:
            raise ValueError("Unknown server event type")
        return {**envelope.model_dump(), "payload": model.model_validate(envelope.payload)}


def parse_event(raw: str) -> ServerEvent | EventEnvelope:
    """Return a bare envelope for a compatible, unrecognized v1 event."""
    data = parse_json(raw)
    envelope = EventEnvelope.model_validate(data)
    if envelope.type in EVENT_PAYLOADS:
        return ServerEvent.model_validate(data)
    return envelope


def parse_command(raw: str) -> ClientCommand | CommandEnvelope:
    data = parse_json(raw)
    envelope = CommandEnvelope.model_validate(data)
    if envelope.type in COMMAND_TYPES:
        return ClientCommand.model_validate(data)
    return envelope
