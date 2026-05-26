from __future__ import annotations

import hmac
import json
import os
import time
from typing import Any, Callable, Awaitable

from .auth import require_request_allowed
from .config import load_config
from .observability import begin_span, prometheus_text, record_request_metric, structured_log
from .server import ShadowProofHandler
from .tool_api import call_tool
from .schema_validation import validate_tool_payload


async def _read_body(receive, max_bytes: int) -> tuple[bytes | None, bool]:
    chunks: list[bytes] = []
    total = 0
    more = True
    while more:
        event = await receive()
        if event["type"] != "http.request":
            continue
        chunk = event.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            return None, True
        chunks.append(chunk)
        more = bool(event.get("more_body", False))
    return b"".join(chunks), False


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}


async def _send_json(send, code: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    await send({"type": "http.response.start", "status": code, "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


async def _send_text(send, code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
    raw = body.encode("utf-8")
    await send({"type": "http.response.start", "status": code, "headers": [(b"content-type", content_type.encode()), (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


def _is_admin_request(headers: dict[str, str], cfg, payload: dict[str, Any]) -> bool:
    if not getattr(cfg, "enable_admin_http", False):
        return False
    supplied = payload.get("admin_bearer_token") or payload.get("admin_authorization")
    if not supplied:
        supplied = headers.get("x-shadowproof-admin-token") or headers.get("authorization")
    if isinstance(supplied, str) and supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    supplied = str(supplied or "")
    if not supplied:
        return False
    raw = os.environ.get(getattr(cfg, "admin_bearer_tokens_env", "SHADOWPROOF_ADMIN_BEARER_TOKENS"), "")
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    return any(hmac.compare_digest(supplied, token) for token in tokens)


async def app(scope, receive, send):
    """Dependency-light ASGI app for production servers.

    Run with: uvicorn shadowproof_core.asgi:app --host 0.0.0.0 --port 8765
    FastAPI can be layered above this later; this preserves the existing JSON
    contract while giving deployments graceful ASGI process management.
    """
    if scope["type"] != "http":
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        return

    path = scope.get("path", "/")
    method = scope.get("method", "GET").upper()
    cfg = load_config({})
    started = time.monotonic()

    if method == "GET":
        if path in {"/health", "/livez"}:
            return await _send_json(send, 200, {"ok": True, "service": "shadowproof_bridge", "version": "0.25.6"})
        if path == "/readyz":
            return await _send_json(send, 200, call_tool("shadowproof_readiness", {}))
        if path == "/metrics":
            return await _send_text(send, 200, prometheus_text(cfg), "text/plain; version=0.0.4; charset=utf-8")
        return await _send_json(send, 404, {"error": "not_found"})

    if method != "POST" or path not in ShadowProofHandler.routes:
        return await _send_json(send, 404, {"error": "not_found"})

    headers = _headers(scope)
    body, too_large = await _read_body(receive, int(getattr(cfg, "max_request_bytes", 1_000_000)))
    if too_large or body is None:
        return await _send_json(send, 413, {"status": "error", "error": "request_too_large", "max_request_bytes": cfg.max_request_bytes})
    try:
        payload = json.loads(body.decode("utf-8")) if body.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
    except Exception as e:
        return await _send_json(send, 400, {"error": "bad_json", "message": str(e)})

    tool_name = ShadowProofHandler.routes[path]
    schema_errors = validate_tool_payload(tool_name, payload)
    if schema_errors:
        return await _send_json(send, 400, {"status": "error", "error": "schema_validation_failed", "diagnostics": schema_errors})

    if path in ShadowProofHandler.admin_routes and not _is_admin_request(headers, cfg, payload):
        return await _send_json(send, 403, {"status": "forbidden", "error": "admin_scope_required", "message": "This route is disabled unless SHADOWPROOF_ENABLE_ADMIN_HTTP=true and a matching admin bearer token is supplied."})

    if "authorization" in headers and "authorization" not in payload and "bearer_token" not in payload:
        payload["authorization"] = headers["authorization"]
    allowed, ctx, auth_error = require_request_allowed(payload, cfg)
    if not allowed:
        return await _send_json(send, 429 if not ctx.quota_allowed else 401, auth_error or {"status": "unauthorized"})
    payload["tenant_id"] = ctx.tenant_id
    if ctx.user_id is not None:
        payload["user_id"] = ctx.user_id

    try:
        with begin_span("shadowproof.asgi.dispatch", {"tool": tool_name, "tenant_id": ctx.tenant_id}):
            response = call_tool(tool_name, payload)
        status = str(response.get("status", "unknown")) if isinstance(response, dict) else "unknown"
        duration_ms = int((time.monotonic() - started) * 1000)
        record_request_metric(tool_name, status, duration_ms)
        structured_log(method="POST", path=path, status=200, duration_ms=duration_ms, tenant_id=ctx.tenant_id, user_id=ctx.user_id, tool=tool_name, response_status=status)
        return await _send_json(send, 200, response)
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        record_request_metric(tool_name, "tool_exception", duration_ms)
        structured_log(method="POST", path=path, status=500, duration_ms=duration_ms, tenant_id=ctx.tenant_id, tool=tool_name, error="tool_exception")
        return await _send_json(send, 500, {"status": "error", "error": "tool_exception", "message": str(e)})
