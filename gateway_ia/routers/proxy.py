from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import Response

from gateway_ia.services.proxy_service import handle_proxy_request

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_catch_all(request: Request, path: str) -> Response:
    client = request.app.state.http_client
    store = request.app.state.store
    return await handle_proxy_request(request, client, store)
