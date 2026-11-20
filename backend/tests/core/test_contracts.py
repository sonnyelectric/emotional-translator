import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from referencing.exceptions import Unresolvable

from backend.app.schemas import (
    EVENT_PAYLOADS,
    ClientCommand,
    CommandEnvelope,
    EventEnvelope,
    ServerEvent,
    parse_command,
    parse_event,
    parse_json,
    schema_registry,
    schema_validator,
)

FIXTURES = Path(__file__).resolve().parents[3] / "shared" / "fixtures"


def fixture(name):
    return parse_json((FIXTURES / name).read_text(encoding="utf-8"))


def check_event(data):
    schema_validator("server-event.schema.json").validate(data)
    event = parse_event(json.dumps(data))
    assert isinstance(event, ServerEvent)
    assert event.model_dump(exclude_unset=True) == data


@pytest.mark.parametrize("event", fixture("server_examples.json"), ids=lambda event: event["type"])
def test_server_example(event):
    check_event(event)


@pytest.mark.parametrize("command", fixture("client_commands.json"), ids=lambda cmd: cmd["type"])
def test_client_command(command):
    schema_validator("client-command.schema.json").validate(command)
    parsed = parse_command(json.dumps(command))
    assert isinstance(parsed, ClientCommand)
    assert parsed.model_dump() == command


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.jsonl")), ids=lambda path: path.stem)
def test_replay_structure(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        check_event(parse_json(line))


def test_manifest_structure():
    schema_validator("replay-manifest.schema.json").validate(fixture("manifest.json"))


def test_http_example_structure():
    examples = fixture("http_examples.json")
    schema_validator("health.schema.json").validate(examples["health"])
    for error in examples["errors"]:
        schema_validator("http-error.schema.json").validate(error)


def test_model_window_structure():
    for window in fixture("pipeline_examples.json")["windows"]:
        schema_validator("model-window.schema.json").validate(window)


@pytest.mark.parametrize(
    "case",
    [case for case in fixture("invalid/cases.json") if "prefix" not in case],
    ids=lambda case: case["id"],
)
def test_invalid_structure(case):
    if "raw" in case:
        with pytest.raises(ValueError):
            parse_json(case["raw"])
        return

    data = case["instance"]
    assert not schema_validator(case["schema"] + ".schema.json").is_valid(data)
    model = {
        "client-command": ClientCommand,
        "event-envelope": EventEnvelope,
        "server-event": ServerEvent,
    }[case["schema"]]
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("invalid_seq", [True, "1", 0, 2**53, 1.5])
def test_sequence_parity(invalid_seq):
    event = {**fixture("server_examples.json")[0], "seq": invalid_seq}
    assert not schema_validator("server-event.schema.json").is_valid(event)
    with pytest.raises(ValidationError):
        parse_event(json.dumps(event))


def test_integral_decimal_parity():
    lines = (FIXTURES / "replay_demo.jsonl").read_text(encoding="utf-8").splitlines()
    event = next(item for item in map(parse_json, lines) if item["type"] == "emotion.updated")
    event["seq"] = float(event["seq"])
    event["payload"]["revision"] = float(event["payload"]["revision"])
    check_event(event)


def test_unknown_server_event():
    case = next(case for case in fixture("invalid/cases.json") if case["id"] == "unknown_type_compatible")
    event = case["event"]
    assert event["type"] not in EVENT_PAYLOADS
    schema_validator("event-envelope.schema.json").validate(event)
    assert type(parse_event(json.dumps(event))) is EventEnvelope


def test_unknown_client_command():
    data = {"schema_version": "1.0", "type": "future.command", "payload": {}}
    assert type(parse_command(json.dumps(data))) is CommandEnvelope
    with pytest.raises(ValidationError):
        parse_command(json.dumps({**data, "schema_version": "2.0"}))


def test_references_resolve_locally():
    registry = schema_registry()
    resolver = registry.resolver("https://emotional-translator.invalid/schemas/v1/server-event.schema.json")
    resolved = resolver.lookup("common.schema.json#/$defs/id")
    assert resolved.contents["type"] == "string"
    with pytest.raises(Unresolvable):
        resolver.lookup("https://example.invalid/missing.schema.json")
