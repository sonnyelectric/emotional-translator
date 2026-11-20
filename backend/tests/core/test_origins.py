"""Origin policy: ALLOWED_ORIGIN (legacy), ALLOWED_ORIGINS and ALLOWED_ORIGIN_REGEX for WS and CORS."""

import pytest
from fastapi.testclient import TestClient
from live_helpers import command, live_client, live_settings, make_runtime
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from backend.app.config import Settings, load_settings
from backend.app.main import create_app

VERCEL = "https://hueq-ovti8l6xq-sonny1106-4950.vercel.app"
PREVIEW_REGEX = r"^https://[a-z0-9-]+-sonny1106-4950\.vercel\.app$"
REJECTED = [
    "http://evil.example",
    "https://hueq-ovti8l6xq-sonny1106-4950.vercel.app.evil.example",
    "https://evil.example/?x=-sonny1106-4950.vercel.app",
    "http://hueq-ovti8l6xq-sonny1106-4950.vercel.app",  # http, not https
    "https://other-team.vercel.app",
    "null",
]


def test_default_is_local_frontend_only():
    settings = Settings()
    assert settings.exact_origins == ("http://localhost:5173",)
    assert settings.origin_allowed("http://localhost:5173")
    assert not settings.origin_allowed(VERCEL)


def test_allowed_origins_replaces_default_and_is_normalized():
    settings = Settings(allowed_origins=f" {VERCEL}/ , https://demo.example ")
    assert settings.exact_origins == (VERCEL, "https://demo.example")
    assert not settings.origin_allowed("http://localhost:5173")


def test_explicit_legacy_origin_is_kept_alongside_list():
    settings = Settings(allowed_origin="http://localhost:5400", allowed_origins=VERCEL)
    assert settings.exact_origins == ("http://localhost:5400", VERCEL)


@pytest.mark.parametrize("bad", ["*", "https://x.example/path", "x.example", "https://a.example,*"])
def test_wildcards_and_paths_are_refused(bad):
    with pytest.raises(ValidationError):
        Settings(allowed_origins=bad)


def test_bad_regex_is_refused():
    with pytest.raises(ValidationError):
        Settings(allowed_origin_regex="^https://(")


@pytest.mark.parametrize("origin", [VERCEL, "https://hueq-abc123-sonny1106-4950.vercel.app"])
def test_regex_matches_previews(origin):
    assert Settings(allowed_origins="https://demo.example", allowed_origin_regex=PREVIEW_REGEX).origin_allowed(origin)


@pytest.mark.parametrize("origin", REJECTED)
def test_regex_requires_a_full_match(origin):
    assert not Settings(allowed_origin_regex=PREVIEW_REGEX).origin_allowed(origin)


@pytest.mark.parametrize("mode", ["replay", "live"])
def test_load_settings_reads_all_origin_variables(monkeypatch, tmp_path, mode):
    monkeypatch.setattr("backend.app.config.BACKEND_ROOT", tmp_path)  # ignore a local backend/.env
    monkeypatch.setenv("TRANSLATOR_MODE", mode)
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", f"{VERCEL},https://demo.example")
    monkeypatch.setenv("ALLOWED_ORIGIN_REGEX", PREVIEW_REGEX)
    settings = load_settings()
    assert settings.exact_origins == (VERCEL, "https://demo.example")
    assert settings.allowed_origin_regex == PREVIEW_REGEX


def test_legacy_allowed_origin_env_still_works(monkeypatch):
    monkeypatch.setenv("TRANSLATOR_MODE", "replay")
    monkeypatch.setenv("ALLOWED_ORIGIN", "http://localhost:5400")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGIN_REGEX", raising=False)
    assert load_settings().exact_origins == ("http://localhost:5400",)


def deployed(**overrides):
    return live_settings(allowed_origins="https://demo.example", allowed_origin_regex=PREVIEW_REGEX, **overrides)


@pytest.mark.parametrize("origin", ["https://demo.example", VERCEL])
def test_websocket_accepts_listed_and_regex_origins(origin):
    with live_client(make_runtime(settings=deployed())) as client:
        with client.websocket_connect("/ws/v1/session", headers={"origin": origin}) as ws:
            ws.send_text(command("session.reset"))
            assert ws.receive_json()["type"] == "session.reset"


@pytest.mark.parametrize("origin", REJECTED + ["http://localhost:5173"])
def test_websocket_rejects_everything_else(origin):
    with live_client(make_runtime(settings=deployed())) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/ws/v1/session", headers={"origin": origin}):
                pass
        assert rejected.value.code == 1008


@pytest.fixture
def replay_client():
    settings = Settings(mode="replay", allowed_origins="https://demo.example", allowed_origin_regex=PREVIEW_REGEX)
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.mark.parametrize("origin", ["https://demo.example", VERCEL])
def test_cors_grants_listed_and_regex_origins(replay_client, origin):
    response = replay_client.get("/api/v1/replay/manifest", headers={"origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    preflight = replay_client.options("/api/v1/replay/manifest",
                                      headers={"origin": origin, "access-control-request-method": "GET"})
    assert preflight.status_code == 200


@pytest.mark.parametrize("origin", REJECTED + ["http://localhost:5173"])
def test_cors_grants_nothing_else(replay_client, origin):
    response = replay_client.get("/api/v1/replay/manifest", headers={"origin": origin})
    assert "access-control-allow-origin" not in response.headers
