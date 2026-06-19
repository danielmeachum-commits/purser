"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.db import init_db
from api import poller
from api.config import get_settings
from api.routers import (
    accounts as accounts_router,
    auth as auth_router,
    categories as categories_router,
    models as models_router,
    savings as savings_router,
    summary as summary_router,
    transactions as transactions_router,
    ws as ws_router,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize the DB and start the background poller."""
    init_db()
    task = asyncio.create_task(poller.run_forever(), name="db-poller")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def create_app() -> FastAPI:
    """Build the FastAPI app."""
    settings = get_settings()
    app = FastAPI(title="budget-graph API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router.router)
    app.include_router(accounts_router.router)
    app.include_router(categories_router.router)
    app.include_router(transactions_router.router)
    app.include_router(summary_router.router)
    app.include_router(savings_router.router)
    app.include_router(models_router.router)
    app.include_router(ws_router.router)

    return app


app = create_app()
