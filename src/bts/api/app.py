"""FastAPI application factory."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bts import __version__
from bts.api.routes import router
from bts.api.sessions import SessionManager
from bts.config import Settings, get_settings
from bts.insights.foundry import make_llm
from bts.store.profiles import make_store

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(title="Beyond the Scoreline", version=__version__)
    app.state.settings = settings
    app.state.llm = make_llm(settings)
    app.state.sessions = SessionManager(app.state.llm)
    app.state.profiles = make_store(settings)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(router)

    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
