from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, load_settings
from .schemas import SCHEMA_VERSION


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Emotional Translator")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_methods=["GET"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"schema_version": SCHEMA_VERSION, "status": "ok"}

    return app
