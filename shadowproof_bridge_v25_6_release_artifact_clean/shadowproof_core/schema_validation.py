from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


PACKAGE_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
ROOT_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _schema_dirs() -> tuple[Path, ...]:
    """Runtime schema search path.

    Package schemas are authoritative in installed wheels.  The repository-level
    ``schemas/`` directory is kept as a source-tree fallback so editable/dev
    checkouts and older Docker layouts remain compatible.
    """
    dirs: list[Path] = []
    for candidate in (PACKAGE_SCHEMA_DIR, ROOT_SCHEMA_DIR):
        if candidate.exists() and candidate not in dirs:
            dirs.append(candidate)
    return tuple(dirs)


def _first_existing_schema_file(filename: str) -> Path | None:
    for schema_dir in _schema_dirs():
        path = schema_dir / filename
        if path.exists():
            return path
    return None


def _read_schema_file(filename: str) -> dict[str, Any] | None:
    path = _first_existing_schema_file(filename)
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))

# The runtime dispatch key is the concrete tool name.  Most schemas are named
# exactly that way.  A small number are intentionally shared family schemas;
# this map lets the HTTP/ASGI/CLI boundaries enforce those contracts instead of
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


def _schema_filename(schema_name: str) -> str:
    return f"{schema_name}.input.schema.json"


@lru_cache(maxsize=1)
def descriptor_input_schemas() -> dict[str, dict[str, Any]]:
    """Return OpenAI/MCP inline input schemas keyed by concrete tool name."""
    raw = _read_schema_file("openai_mcp_tool_descriptors.json")
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
      1. Exact packaged/source file: schemas/{tool_name}.input.schema.json.
      2. Inline OpenAI/MCP descriptor schema for buyer-facing tools.
      3. Explicit/family aliases for grouped tools.
      4. Generic commercial/enterprise envelope schemas.
    """
    exact = _read_schema_file(_schema_filename(tool_name))
    if exact is not None:
        return exact

    descriptor_schema = descriptor_input_schemas().get(tool_name)
    if descriptor_schema is not None:
        return descriptor_schema

    alias = _SCHEMA_ALIASES.get(tool_name)
    if alias:
        schema = schema_for_tool(alias)
        if schema is not None:
            return schema

    for prefix, schema_name in _PREFIX_ALIASES:
        if tool_name.startswith(prefix):
            schema = _read_schema_file(_schema_filename(schema_name))
            if schema is not None:
                return schema

    if tool_name in _ENTERPRISE_SCHEMA_TOOLS:
        schema = _read_schema_file(_schema_filename("shadowproof_enterprise"))
        if schema is not None:
            return schema

    if tool_name in _COMMERCIAL_SCHEMA_TOOLS:
        schema = _read_schema_file(_schema_filename("shadowproof_commercial"))
        if schema is not None:
            return schema

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
