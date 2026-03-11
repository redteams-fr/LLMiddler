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
        return f"[Binary data, {len(value)} bytes]"


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


def _aggregate_sse(value: str) -> tuple[str, list[dict] | None, dict | None]:
    """Parse SSE lines and aggregate delta.content and delta.tool_calls."""
    parts: list[str] = []
    tool_calls: dict[int, dict] = {}
    usage = None
    for line in value.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            u = chunk.get("usage")
            if u:
                usage = u
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                content = delta.get("content")
                if content:
                    parts.append(content)
                for tc in delta.get("tool_calls", []):
                    idx = tc.get("index", 0)
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.get("id", ""),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "",
                            },
                        }
                    else:
                        if tc.get("id"):
                            tool_calls[idx]["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            tool_calls[idx]["function"]["name"] = tc["function"]["name"]
                    args = tc.get("function", {}).get("arguments")
                    if args is not None:
                        tool_calls[idx]["function"]["arguments"] += args
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    tc_list = [tool_calls[i] for i in sorted(tool_calls)] if tool_calls else None
    text = "".join(parts) if parts else ("" if tc_list else value)
    return (text, tc_list, usage)


def _extract_tool_call_names(session) -> list[str]:
    """Extract function names from tool_calls in a session's response."""
    if not session.response_body:
        return []
    try:
        decoded = _decode_body(session.response_body)
        if session.is_streaming:
            names: list[str] = []
            for line in decoded.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    for choice in chunk.get("choices", []):
                        for tc in choice.get("delta", {}).get("tool_calls", []):
                            name = tc.get("function", {}).get("name")
                            if name and name not in names:
                                names.append(name)
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
            return names
        else:
            parsed = json.loads(decoded)
            msg = parsed.get("choices", [{}])[0].get("message", {})
            tc_list = msg.get("tool_calls") or []
            return [
                tc.get("function", {}).get("name", "")
                for tc in tc_list
                if tc.get("function", {}).get("name")
            ]
    except Exception:
        return []


def _extract_tool_calls_detail(session) -> list[dict]:
    """Extract full tool call objects (name + arguments) from a session's response."""
    if not session.response_body:
        return []
    try:
        decoded = _decode_body(session.response_body)
        if session.is_streaming:
            _, tc_list, _ = _aggregate_sse(decoded)
            return tc_list or []
        else:
            parsed = json.loads(decoded)
            msg = parsed.get("choices", [{}])[0].get("message", {})
            return msg.get("tool_calls") or []
    except Exception:
        return []


def _has_tool_calls(session) -> bool:
    """Check if a session's response contains tool_calls."""
    return bool(_extract_tool_call_names(session))


def _extract_usage(session) -> dict | None:
    """Extract usage dict from a session's response body (streaming or not)."""
    if not session.response_body:
        return None
    try:
        decoded = _decode_body(session.response_body)
        if session.is_streaming:
            for line in reversed(decoded.splitlines()):
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    continue
                chunk = json.loads(payload)
                u = chunk.get("usage")
                if u:
                    return u
        else:
            parsed = json.loads(decoded)
            u = parsed.get("usage")
            if u:
                return u
    except Exception:
        pass
    return None


def _extract_usage_total(session) -> int | None:
    """Extract total_tokens from a session's response body."""
    u = _extract_usage(session)
    return u.get("total_tokens") if u else None


def _localtime(value: datetime) -> datetime:
    """Convert a UTC datetime to the system local timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone()


templates.env.filters["localtime"] = _localtime
templates.env.filters["decode_body"] = _decode_body
templates.env.filters["tojson_pretty"] = _tojson_pretty
templates.env.filters["format_duration"] = _format_duration
templates.env.filters["aggregate_sse"] = lambda v: _aggregate_sse(v)[0]
templates.env.filters["usage_total"] = _extract_usage_total
templates.env.filters["has_tool_calls"] = _has_tool_calls
templates.env.filters["tool_call_names"] = _extract_tool_call_names


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
        return HTMLResponse(content="Session not found", status_code=404)
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
    response_body_raw = ""
    usage = None
    tool_calls = None
    if session.response_body:
        decoded = _decode_body(session.response_body)
        response_body_raw = decoded
        if session.is_streaming:
            text, tool_calls, usage = _aggregate_sse(decoded)
            # Reconstruct a clean JSON message from the aggregated parts
            msg: dict = {"role": "assistant"}
            if text:
                msg["content"] = text
            if tool_calls:
                msg["tool_calls"] = tool_calls
            reconstructed: dict = {"message": msg}
            if usage:
                reconstructed["usage"] = usage
            response_body = json.dumps(reconstructed, indent=2, ensure_ascii=False)
        else:
            response_body = _tojson_pretty(decoded)
            try:
                parsed = json.loads(decoded)
                msg = parsed.get("choices", [{}])[0].get("message", {})
                tc = msg.get("tool_calls")
                if tc:
                    tool_calls = tc
            except (json.JSONDecodeError, TypeError, KeyError, IndexError):
                pass

    return {
        "id": session.id,
        "method": session.method,
        "path": session.path,
        "status_code": session.status_code,
        "is_streaming": session.is_streaming,
        "request_body": request_body,
        "response_body": response_body,
        "response_body_raw": response_body_raw,
        "tool_calls": tool_calls,
        "usage": usage,
    }


@router.get("/api/sessions")
async def api_sessions(request: Request):
    store = request.app.state.store
    sessions = [s for s in store.list_all() if "favico" not in s.path and "_ui" not in s.path]
    total_prompt = 0
    total_completion = 0
    items = []
    for s in sessions:
        usage = _extract_usage(s)
        if usage:
            total_prompt += usage.get("prompt_tokens", 0)
            total_completion += usage.get("completion_tokens", 0)
        items.append({
            "id": s.id,
            "status": s.status.value,
            "created_at": _localtime(s.created_at).strftime("%H:%M:%S"),
            "method": s.method,
            "path": s.path,
            "query_string": s.query_string,
            "status_code": s.status_code,
            "duration_ms": s.duration_ms,
            "is_streaming": s.is_streaming,
            "has_tool_calls": _has_tool_calls(s),
            "tool_call_names": _extract_tool_call_names(s),
            "total_tokens": usage.get("total_tokens") if usage else None,
        })
    return {
        "sessions": items,
        "totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        },
    }


@router.get("/api/tool-calls-summary")
async def api_tool_calls_summary(request: Request):
    store = request.app.state.store
    sessions = [s for s in store.list_all() if "favico" not in s.path and "_ui" not in s.path]
    grouped: dict[str, list[dict]] = {}
    for s in sessions:
        session_time = _localtime(s.created_at).strftime("%H:%M:%S")
        for tc in _extract_tool_calls_detail(s):
            fn = tc.get("function", {})
            name = fn.get("name", "")
            if not name:
                continue
            args_raw = fn.get("arguments", "")
            try:
                args = json.loads(args_raw) if args_raw else {}
            except (json.JSONDecodeError, TypeError):
                args = args_raw
            grouped.setdefault(name, []).append({
                "time": session_time,
                "arguments": args,
            })
    summary = sorted(
        [{"name": name, "count": len(calls), "calls": calls} for name, calls in grouped.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    total_calls = sum(item["count"] for item in summary)
    return {
        "tools": summary,
        "total_calls": total_calls,
        "unique_functions": len(summary),
    }


@router.post("/sessions/clear")
async def clear_sessions(request: Request):
    store = request.app.state.store
    config = request.app.state.config
    store.clear()
    return RedirectResponse(url=f"{config.ui.prefix}/", status_code=303)
