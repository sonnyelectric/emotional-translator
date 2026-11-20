from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings
from .replay import FIXTURES_ROOT, ReplayCatalog, replay_router
from .schemas import SCHEMA_VERSION


def create_app(
    settings: Settings | None = None,
    *,
    fixtures_root: Path = FIXTURES_ROOT,
    live_runtime=None,
) -> FastAPI:
    """Replay mode never builds the live runtime, so B's provider/model code is not imported."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="Emotional Translator", lifespan=lifespan)
    app.state.settings = settings
    app.state.live_runtime = live_runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_methods=["GET"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"schema_version": SCHEMA_VERSION, "status": "ok"}

    app.include_router(replay_router(ReplayCatalog(fixtures_root)))
    return app
