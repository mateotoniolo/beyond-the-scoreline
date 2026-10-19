"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bts import __version__
from bts.api.routes import router
from bts.api.sessions import SessionManager
from bts.config import Settings, get_settings
from bts.insights.foundry import make_llm
from bts.insights.pipeline import InsightService

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Beyond the Scoreline", version=__version__)
    app.state.settings = settings
    app.state.llm = make_llm(settings)
    app.state.insights = InsightService(app.state.llm)
    app.state.sessions = SessionManager(app.state.insights)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(router)

    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
