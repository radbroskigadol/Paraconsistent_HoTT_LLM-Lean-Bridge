from __future__ import annotations

import pytest

from shadowproof_core.auth import build_request_context
from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.path_guard import PathPolicyError
from shadowproof_core.schema_validation import schema_for_tool, validate_tool_payload
from shadowproof_core.learning import resolve_memory_path


def test_quota_mode_case_is_normalized_before_rate_limit_check():
    cfg = ShadowProofConfig(
        environment="development",
        auth_mode="disabled",
        quota_mode="Memory",
        requests_per_minute=2,
    )
    payload = {"tenant_id": "casequota", "user_id": "u_v25_3"}
    assert build_request_context(payload, cfg).quota_allowed is True
    assert build_request_context(payload, cfg).quota_allowed is True
    third = build_request_context(payload, cfg)
    assert third.quota_allowed is False
    assert "rate limit" in third.reason.lower()


@pytest.mark.parametrize(
    ("tool_name", "payload", "expected_fragment"),
    [
        (
            "shadowproof_shadowhott_state",
            {"request_id": "bad", "proof_graph": "not an array", "lean_status": 99},
            "proof_graph",
        ),
        (
            "shadowproof_pilot_plan",
            {"request_id": "bad", "target_domains": "algebra"},
            "target_domains",
        ),
        (
            "shadowproof_compile_repair_prompt",
            {"request_id": "bad", "diagnostics": []},
            "theorem_fingerprint",
        ),
    ],
)
def test_renamed_primary_schemas_are_enforced(tool_name, payload, expected_fragment):
    errors = validate_tool_payload(tool_name, payload)
    assert errors
    assert any(expected_fragment in e for e in errors)


def test_descriptor_inline_schema_fallback_validates_buyer_facing_tools():
    # shadowproof_check_draft has no standalone schema file; its OpenAI/MCP
    # descriptor has additionalProperties=false and should now be enforced at
    # the raw HTTP/ASGI boundary too.
    errors = validate_tool_payload(
        "shadowproof_check_draft",
        {"request_id": "bad", "draft": {}, "unexpected": True},
    )
    assert errors
    assert any("Additional properties" in e or "unexpected" in e for e in errors)


def test_family_schema_fallback_validates_grouped_tools():
    assert schema_for_tool("shadowproof_optimize_record") is not None
    errors = validate_tool_payload(
        "shadowproof_optimize_record",
        {"request_id": "bad", "learning_enabled": "false"},
    )
    assert errors
    assert any("learning_enabled" in e for e in errors)


def test_explicit_memory_path_is_root_guarded(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", "/safe-root-that-does-not-contain-tmp")
    with pytest.raises(PathPolicyError):
        resolve_memory_path("/tmp/shadowproof-memory.jsonl", "tenant")
