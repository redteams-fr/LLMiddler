from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _decode_body(value: bytes | None) -> str:
    if value is None:
        return ""
    try:
        return value.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return f"[Donnees binaires, {len(value)} octets]"


def _tojson_pretty(value: str) -> str:
    try:
        parsed = json.loads(value)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return value


def _format_duration(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 1000:
        return f"{value / 1000:.2f} s"
    return f"{value:.1f} ms"


def _aggregate_sse(value: str) -> str:
    """Parse SSE lines and aggregate delta.content into a single message."""
    parts: list[str] = []
    for line in value.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            for choice in chunk.get("choices", []):
                content = choice.get("delta", {}).get("content")
                if content:
                    parts.append(content)
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return "".join(parts) if parts else value


def _localtime(value: datetime) -> datetime:
    """Convert a UTC datetime to the system local timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone()


templates.env.filters["localtime"] = _localtime
templates.env.filters["decode_body"] = _decode_body
templates.env.filters["tojson_pretty"] = _tojson_pretty
templates.env.filters["format_duration"] = _format_duration
templates.env.filters["aggregate_sse"] = _aggregate_sse


@router.get("/", response_class=HTMLResponse)
async def session_list(request: Request):
    store = request.app.state.store
    config = request.app.state.config
    return templates.TemplateResponse(
        "session_list.html",
        {
            "request": request,
            "sessions": [
                s for s in store.list_all() if "favico" not in s.path and "_ui" not in s.path
            ],
            "ui_prefix": config.ui.prefix,
        },
    )


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: str):
    store = request.app.state.store
    config = request.app.state.config
    session = store.get(session_id)
    if session is None:
        return HTMLResponse(content="Session introuvable", status_code=404)
    return templates.TemplateResponse(
        "session_detail.html",
        {
            "request": request,
            "session": session,
            "ui_prefix": config.ui.prefix,
        },
    )


@router.get("/api/sessions/{session_id}")
async def api_session_detail(request: Request, session_id: str):
    store = request.app.state.store
    session = store.get(session_id)
    if session is None:
        return {"error": "not found"}

    request_body = ""
    if session.request_body:
        request_body = _tojson_pretty(_decode_body(session.request_body))

    response_body = ""
    if session.response_body:
        decoded = _decode_body(session.response_body)
        if session.is_streaming:
            response_body = _aggregate_sse(decoded)
        else:
            response_body = _tojson_pretty(decoded)

    return {
        "id": session.id,
        "method": session.method,
        "path": session.path,
        "status_code": session.status_code,
        "is_streaming": session.is_streaming,
        "request_body": request_body,
        "response_body": response_body,
    }


@router.get("/api/sessions")
async def api_sessions(request: Request):
    store = request.app.state.store
    sessions = [s for s in store.list_all() if "favico" not in s.path and "_ui" not in s.path]
    return [
        {
            "id": s.id,
            "status": s.status.value,
            "created_at": _localtime(s.created_at).strftime("%H:%M:%S"),
            "method": s.method,
            "path": s.path,
            "query_string": s.query_string,
            "status_code": s.status_code,
            "duration_ms": s.duration_ms,
            "is_streaming": s.is_streaming,
        }
        for s in sessions
    ]


@router.post("/sessions/clear")
async def clear_sessions(request: Request):
    store = request.app.state.store
    config = request.app.state.config
    store.clear()
    return RedirectResponse(url=f"{config.ui.prefix}/", status_code=303)
