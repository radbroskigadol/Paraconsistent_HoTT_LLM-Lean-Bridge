from __future__ import annotations

from typing import Any

API_VERSION = "0.25.6"


def build_openapi_spec() -> dict[str, Any]:
    # Imported lazily to avoid circular import at module load time.
    from .tool_api import TOOL_REGISTRY

    paths: dict[str, Any] = {}
    for name in sorted(TOOL_REGISTRY.keys()):
        paths[f"/{name}"] = {
            "post": {
                "summary": name,
                "operationId": name,
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": request_schema_for(name),
                            "examples": {"minimal": {"value": {"request_id": name}}},
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Tool response", "content": {"application/json": {"schema": tool_response_schema()}}},
                    "401": {"description": "Unauthorized"},
                    "413": {"description": "Request too large"},
                    "429": {"description": "Rate limited"},
                    "500": {"description": "Tool exception"},
                },
            }
        }
    paths["/health"] = {
        "get": {
            "summary": "Health check",
            "responses": {"200": {"description": "OK"}},
        }
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "ShadowProof Bridge API",
            "version": API_VERSION,
            "description": "ShadowProof Bridge API with J-conserved ShadowHoTT bilattice state semantics.",
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            },
            "schemas": {
                "ToolResponse": tool_response_schema(),
                "BilatticeLabel": bilattice_label_schema(),
                "ProofPath": proof_path_schema(),
            },
        },
        "paths": paths,
    }


def request_schema_for(name: str) -> dict[str, Any]:
    from .schema_validation import schema_for_tool

    schema = schema_for_tool(name)
    if schema is not None:
        return schema

    base: dict[str, Any] = {
        "type": "object",
        "properties": {
            "request_id": {"type": "string"},
            "tenant_id": {"type": "string"},
            "user_id": {"type": "string"},
        },
        "additionalProperties": True,
    }
    if name in {"shadowproof_validate", "shadowproof_validate_draft", "lean_check"}:
        base["properties"].update({
            "lean_code": {"type": "string"},
            "policy": {"type": "object", "additionalProperties": True},
            "target": {"type": "object", "additionalProperties": True},
        })
    if name.startswith("shadowproof_shadowhott"):
        base["properties"].update({
            "proof_graph": {"type": "array", "items": {"type": "object"}},
            "diagnostics": {"type": "array", "items": {"type": "object"}},
            "lean_status": {"type": "string"},
            "status": {"type": "string"},
        })
    return base


def bilattice_label_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["label", "truth_coordinate", "refutation_coordinate", "designated"],
        "properties": {
            "label": {"type": "string", "enum": ["top", "bottom", "both", "neither"]},
            "pretty": {"type": "string"},
            "truth_coordinate": {"type": "boolean"},
            "refutation_coordinate": {"type": "boolean"},
            "designated": {"type": "boolean"},
            "classical": {"type": "boolean"},
            "nonreal": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def proof_path_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["id", "source", "target", "label"],
        "properties": {
            "id": {"type": "string"},
            "source": {"type": "string"},
            "target": {"type": "string"},
            "label": bilattice_label_schema(),
            "witness": {"type": "string"},
            "kind": {"type": "string"},
        },
        "additionalProperties": True,
    }


def tool_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["request_id", "tool", "status"],
        "properties": {
            "request_id": {"type": "string"},
            "tool": {"type": "string"},
            "status": {"type": "string"},
            "lean_status": {"type": "string"},
            "diagnostics": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "theorem_fingerprint": {"type": "object", "additionalProperties": True},
            "proof_graph": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "certificate": {"type": "object", "additionalProperties": True},
            "shadowhott_state": {
                "type": "object",
                "properties": {
                    "semantics_version": {"type": "string"},
                    "global_label": bilattice_label_schema(),
                    "verdict": {"type": "string", "enum": ["accept", "repair", "reject", "human_review", "unchecked"]},
                    "bilattice_axioms": {"type": "object", "additionalProperties": True},
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": True,
    }
