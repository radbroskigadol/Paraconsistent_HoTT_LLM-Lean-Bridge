from __future__ import annotations

import json
import copy
from functools import lru_cache
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


PROJECT_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
PACKAGED_SCHEMA_DIR = Path(__file__).resolve().parent / "artifacts" / "schemas"


def _active_schema_dir() -> Path:
    """Return the schema directory for source-tree or wheel installs.

    Source checkouts keep schemas at the repository root.  Wheels ship a
    package-internal copy under ``shadowproof_core/artifacts/schemas`` so CLI,
    HTTP, and ASGI validation still work after installation outside the source
    tree.
    """
    if PROJECT_SCHEMA_DIR.exists():
        return PROJECT_SCHEMA_DIR
    return PACKAGED_SCHEMA_DIR


SCHEMA_DIR = _active_schema_dir()
DESCRIPTOR_FILE = SCHEMA_DIR / "openai_mcp_tool_descriptors.json"

# The runtime dispatch key is the concrete tool name.  Most schemas are named
# exactly that way.  A small number are intentionally shared family schemas;
# this map lets the HTTP/ASGI boundary enforce those contracts instead of
# silently treating the tool as unvalidated.
_SCHEMA_ALIASES: dict[str, str] = {
    "shadowproof_shadowhott_audit": "shadowproof_shadowhott_state",
    "shadowproof_suggest_repair": "shadowproof_compile_repair_prompt",
    "shadowproof_compile_repair_context": "shadowproof_diagnostic_retrieval",
    "shadowproof_retrieve_for_diagnostics": "shadowproof_diagnostic_retrieval",
    "shadowproof_integration_checklist": "shadowproof_pilot_plan",
    "shadowproof_acceptance_criteria": "shadowproof_pilot_plan",
    "shadowproof_onboarding_packet": "shadowproof_pilot_plan",
    "shadowproof_adapter_conformance_plan": "shadowproof_pilot_plan",
}

_PREFIX_ALIASES: tuple[tuple[str, str], ...] = (
    ("shadowproof_optimize_", "shadowproof_optimization"),
    ("shadowproof_domain_pack_", "shadowproof_domain_pack_promotion"),
    ("shadowproof_proof_artifact_", "shadowproof_proof_artifact_promotion"),
)

_ENTERPRISE_SCHEMA_TOOLS = frozenset({
    "shadowproof_model_provider_call",
    "shadowproof_cost_estimate",
    "shadowproof_license_scan",
    "shadowproof_release_gate",
    "shadowproof_security_threat_model",
})

_COMMERCIAL_SCHEMA_TOOLS = frozenset({
    "shadowproof_adapter_catalog",
    "shadowproof_admin_delete_tenant_data",
    "shadowproof_admin_tenant_report",
    "shadowproof_config_check",
    "shadowproof_create_review_packet",
    "shadowproof_draft_schema",
    "shadowproof_get_domain_pack",
    "shadowproof_list_domains",
    "shadowproof_liveness",
    "shadowproof_memory_stats",
    "shadowproof_metrics_report",
    "shadowproof_openapi_spec",
    "shadowproof_product_readiness",
    "shadowproof_prometheus_metrics",
    "shadowproof_readiness",
    "shadowproof_release_checklist",
    "shadowproof_retention_sweep",
    "shadowproof_service_status",
    "shadowproof_trace_envelope",
    "shadowproof_error_taxonomy",
    "shadowproof_repair",
    "shadowproof_translate",
    "shadowproof_lean_worker_check",
    "shadowproof_local_behavior_simulation",
    "shadowproof_release_report",
    "shadowproof_create_domain_pack",
    "shadowproof_validate_domain_pack",
    "shadowproof_domain_pack_eval_stub",
    "shadowproof_domain_pack_authoring_guide",
    "shadowproof_acquisition_packet",
    "shadowproof_claims_boundary",
    "shadowproof_due_diligence_checklist",
    "shadowproof_investor_deck",
})


def _schema_path(schema_name: str) -> Path:
    return _active_schema_dir() / f"{schema_name}.input.schema.json"


def _descriptor_file() -> Path:
    return _active_schema_dir() / "openai_mcp_tool_descriptors.json"


def _strict_top_level_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with strict top-level properties unless explicitly opted out.

    Legacy/family schemas used to leave ``additionalProperties`` open.  v25.6
    makes strict top-level payloads the default for all routed tools while
    preserving each schema's documented fields.  Nested objects remain governed
    by their own schema declarations so extensible records such as diagnostics
    can stay forward-compatible where the schema says so.
    """
    if schema.get("type") != "object":
        return schema
    out = copy.deepcopy(schema)
    out["additionalProperties"] = False
    return out


@lru_cache(maxsize=1)
def descriptor_input_schemas() -> dict[str, dict[str, Any]]:
    """Return OpenAI/MCP inline input schemas keyed by concrete tool name."""
    descriptor_file = _descriptor_file()
    if not descriptor_file.exists():
        return {}
    raw = json.loads(descriptor_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        schema = item.get("inputSchema")
        if isinstance(name, str) and isinstance(schema, dict):
            out[name] = schema
    return out


@lru_cache(maxsize=128)
def schema_for_tool(tool_name: str) -> dict[str, Any] | None:
    """Find the strongest local input schema available for a tool.

    Resolution order:
      1. Exact file: schemas/{tool_name}.input.schema.json.
      2. Inline OpenAI/MCP descriptor schema for buyer-facing tools.
      3. Explicit/family aliases for grouped tools.
      4. Generic commercial/enterprise envelope schemas.
    """
    exact = _schema_path(tool_name)
    if exact.exists():
        return _strict_top_level_schema(json.loads(exact.read_text(encoding="utf-8")))

    descriptor_schema = descriptor_input_schemas().get(tool_name)
    if descriptor_schema is not None:
        return _strict_top_level_schema(descriptor_schema)

    alias = _SCHEMA_ALIASES.get(tool_name)
    if alias:
        schema = schema_for_tool(alias)
        if schema is not None:
            return schema

    for prefix, schema_name in _PREFIX_ALIASES:
        if tool_name.startswith(prefix):
            path = _schema_path(schema_name)
            if path.exists():
                return _strict_top_level_schema(json.loads(path.read_text(encoding="utf-8")))

    if tool_name in _ENTERPRISE_SCHEMA_TOOLS:
        path = _schema_path("shadowproof_enterprise")
        if path.exists():
            return _strict_top_level_schema(json.loads(path.read_text(encoding="utf-8")))

    if tool_name in _COMMERCIAL_SCHEMA_TOOLS:
        path = _schema_path("shadowproof_commercial")
        if path.exists():
            return _strict_top_level_schema(json.loads(path.read_text(encoding="utf-8")))

    return None


def validate_tool_payload(tool_name: str, payload: dict[str, Any]) -> list[str]:
    """Validate payload against a shipped JSON Schema when one exists.

    This boundary check intentionally runs before tool dispatch.  It catches
    type-confusion such as string booleans (e.g. "false") that Python's
    bool(...) would otherwise coerce to True, and it rejects deprecated unsafe
    fields such as target.lean_command when the schema forbids them.
    """
    schema = schema_for_tool(tool_name)
    if schema is None:
        return []
    # Authentication/routing metadata is handled by the server before/after
    # validation and is intentionally not part of every tool-specific schema.
    # Validate a copy without those top-level fields so bearer-token and tenant
    # workflows are not broken by strict per-tool schemas.
    validation_payload = dict(payload)
    for meta_key in ("tenant_id", "user_id", "authorization", "bearer_token", "admin_bearer_token", "admin_authorization"):
        validation_payload.pop(meta_key, None)
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except Exception as e:  # pragma: no cover - dependency should be installed
        return [f"jsonschema dependency unavailable: {e}"]
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(validation_payload), key=lambda e: list(e.absolute_path))
    out: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.absolute_path) or "$"
        out.append(f"{loc}: {err.message}")
    return out


def strict_bool(value: Any, default: bool = False, *, field: str = "boolean") -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean")


def strict_int(value: Any, default: int, *, field: str, min_value: int | None = None, max_value: int | None = None) -> int:
    if value is None:
        out = default
    elif isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a JSON integer")
    else:
        out = value
    if min_value is not None and out < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    if max_value is not None and out > max_value:
        raise ValueError(f"{field} must be <= {max_value}")
    return out
