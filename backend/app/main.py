from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings
from .replay import FIXTURES_ROOT, ReplayCatalog, replay_router
from .schemas import SCHEMA_VERSION
from .session import LiveRuntime, build_live_runtime
from .tune import tune_endpoint
from .ws import session_endpoint


def create_app(
    settings: Settings | None = None,
    *,
    fixtures_root: Path = FIXTURES_ROOT,
    live_runtime: LiveRuntime | None = None,
) -> FastAPI:
    """Replay mode never builds the live runtime, so B's provider/model code is not imported."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = live_runtime
        if runtime is None and settings.mode == "live":
            runtime = build_live_runtime(settings)
        app.state.live_runtime = runtime
        if runtime is not None:
            await runtime.start()
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.aclose()

    app = FastAPI(title="Emotional Translator", lifespan=lifespan)
    app.state.settings = settings
    app.state.live_runtime = live_runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.exact_origins),
        allow_origin_regex=settings.allowed_origin_regex,
        allow_methods=["GET"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"schema_version": SCHEMA_VERSION, "status": "ok"}

    app.include_router(replay_router(ReplayCatalog(fixtures_root)))
    app.add_api_websocket_route("/ws/v1/session", session_endpoint)
    if settings.mode == "live" and settings.enable_tune_route:
        # Dev-only tuning route (outside the v1 protocol): model scores, never transcript.
        # Off unless ENABLE_TUNE_ROUTE=1, so a public deployment does not expose it.
        app.add_api_websocket_route("/ws/dev/tune", tune_endpoint)
    return app
