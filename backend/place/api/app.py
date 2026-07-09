"""FastAPI application factory. Run: uvicorn place.api.app:app"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from place.api.packs import PackStaticFiles
from place.api.routes import all_routers
from place.config import get_settings
from place.db import get_async_engine


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_async_engine()
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Place API",
        version="0.1.0",
        description="The experience graph: temporal feed, place pages, verdicts.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in all_routers:
        app.include_router(router)

    # Static pack artifacts (the shadow read path; evaluator/publish.py is
    # the writer). check_dir=False + mkdir: the API must boot on a fresh
    # box before the evaluator's first publish creates any content.
    settings.packs_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/packs",
        PackStaticFiles(directory=str(settings.packs_dir), check_dir=False),
        name="packs",
    )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
