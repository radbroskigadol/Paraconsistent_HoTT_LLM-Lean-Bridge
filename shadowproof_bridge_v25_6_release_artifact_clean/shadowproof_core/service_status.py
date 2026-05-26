from __future__ import annotations

import json
import platform
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.request import urlopen, Request
from typing import Any

from .config import load_config
from .storage import storage_health_check
from .auth import quota_health_check


ERROR_TAXONOMY = {
    "SP_OK": {"severity": "info", "retryable": False, "description": "Operation completed successfully."},
    "SP_UNAUTHORIZED": {"severity": "error", "retryable": False, "description": "Authentication failed."},
    "SP_RATE_LIMITED": {"severity": "warning", "retryable": True, "description": "Quota or rate limit exceeded."},
    "SP_BAD_REQUEST": {"severity": "error", "retryable": False, "description": "Request schema or input is invalid."},
    "SP_SECURITY_REJECTED": {"severity": "error", "retryable": False, "description": "Proof or Lean code failed security preflight."},
    "SP_THEOREM_DRIFT": {"severity": "critical", "retryable": False, "description": "Candidate proof changed theorem meaning or assumptions."},
    "SP_LEAN_UNAVAILABLE": {"severity": "warning", "retryable": True, "description": "Lean worker is unavailable or disabled."},
    "SP_LEAN_REJECTED": {"severity": "error", "retryable": True, "description": "Lean rejected the submitted proof."},
    "SP_LEAN_TIMEOUT": {"severity": "warning", "retryable": True, "description": "Lean worker timed out."},
    "SP_SHADOWHOTT_BOUNDARY": {"severity": "warning", "retryable": True, "description": "Boundary obstruction requires repair."},
    "SP_RETRIEVAL_MISS": {"severity": "warning", "retryable": True, "description": "Retrieval did not find expected formalization candidates."},
    "SP_RELEASE_BLOCKED": {"severity": "critical", "retryable": False, "description": "Release gate blocked promotion."},
    "SP_EXTERNAL_REQUIRED": {"severity": "info", "retryable": False, "description": "A company-provided external integration is required."},
    "SP_INTERNAL_ERROR": {"severity": "critical", "retryable": True, "description": "Unexpected internal error."},
}


@dataclass
class TraceEnvelope:
    request_id: str
    trace_id: str
    span_id: str
    tenant_id: str
    user_id: str | None
    created_at: float


def make_trace(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    trace = TraceEnvelope(
        request_id=str(payload.get("request_id") or f"req_{uuid.uuid4().hex[:12]}"),
        trace_id=str(payload.get("trace_id") or uuid.uuid4().hex),
        span_id=str(payload.get("span_id") or uuid.uuid4().hex[:16]),
        tenant_id=str(payload.get("tenant_id") or payload.get("config", {}).get("default_tenant_id", "default")),
        user_id=str(payload.get("user_id")) if payload.get("user_id") is not None else None,
        created_at=time.time(),
    )
    return asdict(trace)


def liveness(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "status": "ok",
        "service": "shadowproof",
        "version": "0.25.6",
        "time": time.time(),
        "trace": make_trace(payload),
    }


def readiness(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    checks = []

    def check(name: str, status: str, detail: str):
        checks.append({"name": name, "status": status, "detail": detail})

    check("python", "ok", platform.python_version())
    check("config", "ok", f"environment={cfg.environment}, tenant_mode={cfg.tenant_mode}, auth_mode={cfg.auth_mode}")

    storage_check = storage_health_check(cfg)
    check(storage_check["name"], storage_check["status"], f"{storage_check.get('backend')}: {storage_check.get('detail')}")

    quota_check = quota_health_check(cfg)
    check(quota_check["name"], quota_check["status"], f"{quota_check.get('backend')}: {quota_check.get('detail')}")

    if cfg.lean_worker_mode == "disabled":
        check("lean_worker", "warn", "Lean worker disabled; suitable only for non-kernel scaffold checks.")
    elif cfg.lean_worker_mode == "http":
        if not cfg.lean_worker_url:
            check("lean_worker", "fail", "HTTP worker mode selected without SHADOWPROOF_LEAN_WORKER_URL")
        else:
            try:
                req = Request(str(cfg.lean_worker_url).rstrip("/") + "/health", headers={"User-Agent": "shadowproof-readiness"})
                with urlopen(req, timeout=2) as resp:  # nosec - deployment-controlled internal URL
                    ok = 200 <= resp.status < 300
                check("lean_worker", "ok" if ok else "fail", f"active HTTP probe status={resp.status}")
            except Exception as e:
                check("lean_worker", "fail", f"active HTTP probe failed: {e}")
    else:
        check("lean_worker", "warn", f"Local worker command configured: {cfg.lean_command}; production should use hardened HTTP worker.")

    if cfg.auth_mode == "disabled" and cfg.environment == "production":
        check("auth", "fail", "Production environment must not run with auth disabled.")
    elif cfg.auth_mode == "disabled":
        check("auth", "warn", "Auth disabled; acceptable only for local/pilot demos.")
    else:
        check("auth", "ok", cfg.auth_mode)

    failed = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warn"]
    status = "not_ready" if failed else ("degraded" if warnings else "ready")

    return {
        "status": status,
        "service": "shadowproof",
        "version": "0.25.6",
        "checks": checks,
        "summary": {"fail": len(failed), "warn": len(warnings), "ok": sum(1 for c in checks if c["status"] == "ok")},
        "trace": make_trace(payload),
    }


def service_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    live = liveness(payload)
    ready = readiness(payload)
    return {
        "status": "ok" if ready["status"] in {"ready", "degraded"} else "not_ready",
        "service": "shadowproof",
        "version": "0.25.6",
        "liveness": live,
        "readiness": ready,
        "error_taxonomy_count": len(ERROR_TAXONOMY),
        "trace": make_trace(payload),
    }


def error_taxonomy(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "status": "ok",
        "taxonomy": ERROR_TAXONOMY,
        "trace": make_trace(payload),
    }


def wrap_error(code: str, message: str, payload: dict[str, Any] | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    meta = ERROR_TAXONOMY.get(code, ERROR_TAXONOMY["SP_INTERNAL_ERROR"])
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "severity": meta["severity"],
            "retryable": meta["retryable"],
            "description": meta["description"],
            "details": details or {},
        },
        "trace": make_trace(payload),
    }
