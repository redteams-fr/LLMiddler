from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from gateway_ia.config import AppConfig
from gateway_ia.routers import proxy, ui
from gateway_ia.store import SessionStore


def create_app(config: AppConfig) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = config
        app.state.store = SessionStore()
        app.state.http_client = httpx.AsyncClient(
            base_url=config.backend.base_url,
            timeout=httpx.Timeout(config.backend.timeout, connect=10),
            verify=config.backend.verify_ssl,
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
