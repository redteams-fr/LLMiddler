from __future__ import annotations

import time

import httpx
from loguru import logger
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from gateway_ia.models import Session, SessionStatus
from gateway_ia.store import SessionStore

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)


def _filter_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _prepare_upstream_headers(
    incoming_headers: dict[str, str],
    backend_host: str,
) -> dict[str, str]:
    headers = _filter_headers(incoming_headers)
    headers["host"] = backend_host
    return headers


async def handle_proxy_request(
    request: Request,
    client: httpx.AsyncClient,
    store: SessionStore,
) -> Response:
    start = time.monotonic()

    body = await request.body()

    session = Session(
        method=request.method,
        path=request.url.path,
        query_string=str(request.query_params),
        request_headers=dict(request.headers),
        request_body=body if body else None,
    )
    store.add(session)

    target_url = request.url.path
    if request.url.query:
        target_url += f"?{request.url.query}"

    backend_host = str(client.base_url.host)
    if client.base_url.port:
        backend_host += f":{client.base_url.port}"

    upstream_headers = _prepare_upstream_headers(
        dict(request.headers), backend_host
    )

    upstream_request = client.build_request(
        method=request.method,
        url=target_url,
        headers=upstream_headers,
        content=body,
    )

    logger.debug("→ %s %s", request.method, target_url)

    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        session.status = SessionStatus.ERROR
        session.error_message = str(exc)
        session.duration_ms = (time.monotonic() - start) * 1000
        logger.error("✗ %s %s : %s", request.method, target_url, exc)
        return Response(content=f"Proxy error: {exc}", status_code=502)

    content_type = upstream_response.headers.get("content-type", "")
    is_sse = "text/event-stream" in content_type

    session.status_code = upstream_response.status_code
    session.response_headers = dict(upstream_response.headers)

    if is_sse:
        return _build_streaming_response(upstream_response, session, start)

    return await _build_regular_response(upstream_response, session, start)


async def _build_regular_response(
    upstream_response: httpx.Response,
    session: Session,
    start: float,
) -> Response:
    body = await upstream_response.stream.read()
    await upstream_response.aclose()

    session.response_body = body
    session.is_streaming = False
    session.status = SessionStatus.COMPLETED
    session.duration_ms = (time.monotonic() - start) * 1000
    logger.debug(
        "← %s %s (%.0fms)",
        upstream_response.status_code,
        session.path,
        session.duration_ms,
    )

    return Response(
        content=body,
        status_code=upstream_response.status_code,
        headers=_filter_headers(dict(upstream_response.headers)),
    )


def _build_streaming_response(
    upstream_response: httpx.Response,
    session: Session,
    start: float,
) -> StreamingResponse:
    session.is_streaming = True
    accumulated = bytearray()

    async def stream_generator():
        try:
            async for chunk in upstream_response.aiter_raw():
                accumulated.extend(chunk)
                yield chunk
        except Exception as exc:
            session.error_message = str(exc)
            session.status = SessionStatus.ERROR
        finally:
            session.response_body = bytes(accumulated)
            if session.status != SessionStatus.ERROR:
                session.status = SessionStatus.COMPLETED
            session.duration_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "← %s %s (%.0fms, streaming)",
                upstream_response.status_code,
                session.path,
                session.duration_ms,
            )
            await upstream_response.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=upstream_response.status_code,
        headers=_filter_headers(dict(upstream_response.headers)),
        media_type=upstream_response.headers.get("content-type"),
    )
