from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from gateway_ia.config import AppConfig
from gateway_ia.routers import proxy, ui
from gateway_ia.store import SessionStore


class _UIAccessFilter(logging.Filter):
    """Filter out /_ui requests from uvicorn access logs."""

    def __init__(self, ui_prefix: str) -> None:
        super().__init__()
        self._prefix = ui_prefix

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return self._prefix not in msg


def create_app(config: AppConfig) -> FastAPI:

    if not config.logging.quiet:
        logging.getLogger("uvicorn.access").addFilter(
            _UIAccessFilter(config.ui.prefix)
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = config
        app.state.store = SessionStore()
        app.state.http_client = httpx.AsyncClient(
            base_url=config.backend.base_url,
            timeout=httpx.Timeout(config.backend.timeout, connect=10),
        )
        yield
        await app.state.http_client.aclose()

    app = FastAPI(
        title="gateway-ia",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url=config.ui.prefix + "/")

    app.include_router(ui.router, prefix=config.ui.prefix)
    app.include_router(proxy.router)

    return app
