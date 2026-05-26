from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .tool_api import call_tool
from .auth import require_request_allowed
from .config import load_config
from .observability import prometheus_text, structured_log, record_request_metric, begin_span
from .schema_validation import validate_tool_payload


class ShadowProofHandler(BaseHTTPRequestHandler):
    # Per-connection socket timeout.  Without this, BaseHTTPRequestHandler
    # blocks indefinitely on `rfile.read(length)` if a client sends a
    # Content-Length header and then stalls (slowloris-class DoS).  The
    # ASGI app gets its timeout from uvicorn; this is only the stdlib path.
    timeout = 30
    routes = {
        "/lean_check": "lean_check",
        "/shadowproof_translate": "shadowproof_translate",
        "/shadowproof_repair": "shadowproof_repair",
        "/shadowproof_validate": "shadowproof_validate",
        "/shadowproof_check_draft": "shadowproof_check_draft",
        "/shadowproof_validate_draft": "shadowproof_validate_draft",
        "/shadowproof_record_outcome": "shadowproof_record_outcome",
        "/shadowproof_suggest_repair": "shadowproof_suggest_repair",
        "/shadowproof_compile_repair_prompt": "shadowproof_compile_repair_prompt",
        "/shadowproof_memory_stats": "shadowproof_memory_stats",
        "/shadowproof_env_info": "shadowproof_env_info",
        "/shadowproof_eval": "shadowproof_eval",
        "/shadowproof_optimize_suggest": "shadowproof_optimize_suggest",
        "/shadowproof_optimize_record": "shadowproof_optimize_record",
        "/shadowproof_optimize_train": "shadowproof_optimize_train",
        "/shadowproof_optimize_stats": "shadowproof_optimize_stats",
        "/shadowproof_optimize_export_policy": "shadowproof_optimize_export_policy",
        "/shadowproof_training_capacity_plan": "shadowproof_training_capacity_plan",
        "/shadowproof_demorgan_symmetry": "shadowproof_demorgan_symmetry",
        "/shadowproof_list_domains": "shadowproof_list_domains",
        "/shadowproof_get_domain_pack": "shadowproof_get_domain_pack",
        "/shadowproof_retrieve_mathlib": "shadowproof_retrieve_mathlib",
        "/shadowproof_compile_formalization_context": "shadowproof_compile_formalization_context",
        "/shadowproof_index_mathlib": "shadowproof_index_mathlib",
        "/shadowproof_retrieve_for_diagnostics": "shadowproof_retrieve_for_diagnostics",
        "/shadowproof_compile_repair_context": "shadowproof_compile_repair_context",
        "/shadowproof_shadowhott_state": "shadowproof_shadowhott_state",
        "/shadowproof_shadowhott_audit": "shadowproof_shadowhott_audit",
        "/shadowproof_shadowhott_eval": "shadowproof_shadowhott_eval",
        "/shadowproof_regression_suite": "shadowproof_regression_suite",
        "/shadowproof_local_behavior_simulation": "shadowproof_local_behavior_simulation",
        "/shadowproof_config_check": "shadowproof_config_check",
        "/shadowproof_product_readiness": "shadowproof_product_readiness",
        "/shadowproof_metrics_report": "shadowproof_metrics_report",
        "/shadowproof_prometheus_metrics": "shadowproof_prometheus_metrics",
        "/shadowproof_retention_sweep": "shadowproof_retention_sweep",
        "/shadowproof_create_review_packet": "shadowproof_create_review_packet",
        "/shadowproof_lean_worker_check": "shadowproof_lean_worker_check",
        "/shadowproof_adapter_catalog": "shadowproof_adapter_catalog",
        "/shadowproof_model_provider_call": "shadowproof_model_provider_call",
        "/shadowproof_cost_estimate": "shadowproof_cost_estimate",
        "/shadowproof_admin_tenant_report": "shadowproof_admin_tenant_report",
        "/shadowproof_admin_delete_tenant_data": "shadowproof_admin_delete_tenant_data",
        "/shadowproof_openapi_spec": "shadowproof_openapi_spec",
        "/shadowproof_security_threat_model": "shadowproof_security_threat_model",
        "/shadowproof_license_scan": "shadowproof_license_scan",
        "/shadowproof_release_gate": "shadowproof_release_gate",
        "/shadowproof_pilot_plan": "shadowproof_pilot_plan",
        "/shadowproof_integration_checklist": "shadowproof_integration_checklist",
        "/shadowproof_acceptance_criteria": "shadowproof_acceptance_criteria",
        "/shadowproof_onboarding_packet": "shadowproof_onboarding_packet",
        "/shadowproof_adapter_conformance_plan": "shadowproof_adapter_conformance_plan",
        "/shadowproof_domain_pack_schema": "shadowproof_domain_pack_schema",
        "/shadowproof_create_domain_pack": "shadowproof_create_domain_pack",
        "/shadowproof_validate_domain_pack": "shadowproof_validate_domain_pack",
        "/shadowproof_domain_pack_eval_stub": "shadowproof_domain_pack_eval_stub",
        "/shadowproof_domain_pack_authoring_guide": "shadowproof_domain_pack_authoring_guide",
        "/shadowproof_domain_pack_submit": "shadowproof_domain_pack_submit",
        "/shadowproof_domain_pack_status": "shadowproof_domain_pack_status",
        "/shadowproof_domain_pack_registry": "shadowproof_domain_pack_registry",
        "/shadowproof_domain_pack_promote": "shadowproof_domain_pack_promote",
        "/shadowproof_domain_pack_review": "shadowproof_domain_pack_review",
        "/shadowproof_domain_pack_attach_eval": "shadowproof_domain_pack_attach_eval",
        "/shadowproof_domain_pack_rollback": "shadowproof_domain_pack_rollback",
        "/shadowproof_proof_artifact_submit": "shadowproof_proof_artifact_submit",
        "/shadowproof_proof_artifact_status": "shadowproof_proof_artifact_status",
        "/shadowproof_proof_artifact_registry": "shadowproof_proof_artifact_registry",
        "/shadowproof_proof_artifact_attach_validation": "shadowproof_proof_artifact_attach_validation",
        "/shadowproof_proof_artifact_promote": "shadowproof_proof_artifact_promote",
        "/shadowproof_proof_artifact_review": "shadowproof_proof_artifact_review",
        "/shadowproof_proof_artifact_review_packet": "shadowproof_proof_artifact_review_packet",
        "/shadowproof_proof_artifact_export": "shadowproof_proof_artifact_export",
        "/shadowproof_release_report": "shadowproof_release_report",
        "/shadowproof_release_checklist": "shadowproof_release_checklist",
        "/shadowproof_liveness": "shadowproof_liveness",
        "/shadowproof_readiness": "shadowproof_readiness",
        "/shadowproof_service_status": "shadowproof_service_status",
        "/shadowproof_error_taxonomy": "shadowproof_error_taxonomy",
        "/shadowproof_trace_envelope": "shadowproof_trace_envelope",
        "/shadowproof_draft_schema": "shadowproof_draft_schema",
        "/shadowproof_investor_deck": "shadowproof_investor_deck",
        "/shadowproof_acquisition_packet": "shadowproof_acquisition_packet",
        "/shadowproof_claims_boundary": "shadowproof_claims_boundary",
        "/shadowproof_due_diligence_checklist": "shadowproof_due_diligence_checklist",
    }

    admin_routes = {
        "/shadowproof_admin_tenant_report",
        "/shadowproof_admin_delete_tenant_data",
        "/shadowproof_retention_sweep",
        "/shadowproof_create_review_packet",
        "/shadowproof_onboarding_packet",
        "/shadowproof_create_domain_pack",
        "/shadowproof_domain_pack_eval_stub",
        "/shadowproof_release_report",
        "/shadowproof_index_mathlib",
        "/shadowproof_optimize_export_policy",
        "/shadowproof_domain_pack_submit",
        "/shadowproof_domain_pack_status",
        "/shadowproof_domain_pack_registry",
        "/shadowproof_domain_pack_promote",
        "/shadowproof_domain_pack_review",
        "/shadowproof_domain_pack_attach_eval",
        "/shadowproof_domain_pack_rollback",
        "/shadowproof_proof_artifact_submit",
        "/shadowproof_proof_artifact_status",
        "/shadowproof_proof_artifact_registry",
        "/shadowproof_proof_artifact_attach_validation",
        "/shadowproof_proof_artifact_promote",
        "/shadowproof_proof_artifact_review",
        "/shadowproof_proof_artifact_review_packet",
        "/shadowproof_proof_artifact_export",
    }

    def _is_admin_request(self, cfg, payload: dict) -> bool:
        if not getattr(cfg, "enable_admin_http", False):
            return False
        supplied = payload.get("admin_bearer_token") or payload.get("admin_authorization")
        if not supplied:
            supplied = self.headers.get("X-ShadowProof-Admin-Token") or self.headers.get("Authorization")
        if isinstance(supplied, str) and supplied.lower().startswith("bearer "):
            supplied = supplied[7:].strip()
        supplied = str(supplied or "")
        if not supplied:
            return False
        raw = os.environ.get(getattr(cfg, "admin_bearer_tokens_env", "SHADOWPROOF_ADMIN_BEARER_TOKENS"), "")
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        return any(hmac.compare_digest(supplied, token) for token in tokens)

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args):
        # Use explicit structured access logs instead of BaseHTTPRequestHandler text logs.
        return

    def _access_log(self, **fields):
        try:
            structured_log(**fields)
        except Exception:
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        start = time.monotonic()
        cfg = load_config({})
        code = 200
        if path in {"/health", "/livez"}:
            self._send(200, {"ok": True, "service": "shadowproof_bridge", "version": "0.25.6"})
        elif path == "/readyz":
            self._send(200, call_tool("shadowproof_readiness", {}))
        elif path == "/metrics":
            self._send_text(200, prometheus_text(cfg), "text/plain; version=0.0.4; charset=utf-8")
        elif path == "/draft_schema":
            self._send(200, call_tool("shadowproof_draft_schema", {}))
        else:
            code = 404
            self._send(404, {"error": "not_found"})
        self._access_log(method="GET", path=path, status=code, duration_ms=int((time.monotonic()-start)*1000), tenant_id=None, tool=None)

    def do_POST(self):
        started = time.monotonic()
        path = urlparse(self.path).path
        if path not in self.routes:
            self._send(404, {"error": "not_found"})
            return

        cfg = load_config({})
        try:
            if "Content-Length" not in self.headers:
                self._send(411, {"status": "error", "error": "content_length_required"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                self._send(400, {"status": "error", "error": "invalid_content_length"})
                return
            if length > int(getattr(cfg, "max_request_bytes", 1_000_000)):
                self._send(413, {"status": "error", "error": "request_too_large", "max_request_bytes": cfg.max_request_bytes})
                return
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body) if body.strip() else {}
            if not isinstance(payload, dict):
                self._send(400, {"error": "bad_json", "message": "request JSON must be an object"})
                return
        except Exception as e:
            self._send(400, {"error": "bad_json", "message": str(e)})
            return

        tool_name = self.routes[path]
        schema_errors = validate_tool_payload(tool_name, payload)
        if schema_errors:
            self._send(400, {"status": "error", "error": "schema_validation_failed", "diagnostics": schema_errors})
            return

        if path in self.admin_routes and not self._is_admin_request(cfg, payload):
            self._send(403, {"status": "forbidden", "error": "admin_scope_required", "message": "This route is disabled unless SHADOWPROOF_ENABLE_ADMIN_HTTP=true and a matching admin bearer token is supplied."})
            return

        authz = self.headers.get("Authorization")
        if authz and "authorization" not in payload and "bearer_token" not in payload:
            payload["authorization"] = authz
        allowed, ctx, auth_error = require_request_allowed(payload, cfg)
        if not allowed:
            self._send(429 if not ctx.quota_allowed else 401, auth_error or {"status": "unauthorized"})
            return
        payload["tenant_id"] = ctx.tenant_id
        if ctx.user_id is not None:
            payload["user_id"] = ctx.user_id

        try:
            with begin_span("shadowproof.tool.dispatch", {"tool": tool_name, "tenant_id": getattr(ctx, "tenant_id", None) or ""}):
                response = call_tool(tool_name, payload)
        except Exception as e:
            duration_ms = int((time.monotonic()-started)*1000)
            record_request_metric(tool_name, "tool_exception", duration_ms)
            self._send(500, {"status": "error", "error": "tool_exception", "message": str(e)})
            self._access_log(method="POST", path=path, status=500, duration_ms=duration_ms, tenant_id=getattr(ctx, "tenant_id", None), tool=tool_name, error="tool_exception")
            return
        duration_ms = int((time.monotonic()-started)*1000)
        response_status = response.get("status") if isinstance(response, dict) else "unknown"
        record_request_metric(tool_name, str(response_status), duration_ms)
        self._send(200, response)
        self._access_log(method="POST", path=path, status=200, duration_ms=duration_ms, tenant_id=getattr(ctx, "tenant_id", None), user_id=getattr(ctx, "user_id", None), tool=tool_name, response_status=response_status, lean_status=response.get("lean_status") if isinstance(response, dict) else None, bilattice_label=((response.get("certificate") or {}).get("bilattice_label") if isinstance(response, dict) else None))


def serve(host: str = "127.0.0.1", port: int = 8765):
    server = ThreadingHTTPServer((host, port), ShadowProofHandler)
    print(f"ShadowProof Bridge v25.6 Pre-Commercial Package listening on http://{host}:{port}", flush=True)
    server.serve_forever()
