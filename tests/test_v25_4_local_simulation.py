from __future__ import annotations

import json

from shadowproof_core.local_simulation import local_mock_lean_env, make_identity_code, make_identity_draft
from shadowproof_core.model_providers import call_model_provider
from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.tool_api import call_tool
from shadowproof_core.schema_validation import validate_tool_payload


def test_local_deterministic_provider_returns_draft_fixture():
    out = call_model_provider(
        {
            "provider": "local_deterministic",
            "model_id": "local-sim",
            "prompt": "prove n = n",
            "scenario": "valid_identity_draft",
        },
        ShadowProofConfig(),
    )
    assert out["status"] == "ok"
    body = json.loads(out["text"])
    assert body["local_simulation"] is True
    assert body["draft"]["theorem_name"] == "local_id"


def test_mock_lean_accepts_and_rejects_through_tool_api():
    with local_mock_lean_env():
        ok = call_tool("lean_check", {
            "request_id": "ok",
            "lean_code": make_identity_code(),
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
            "policy": {"timeout_seconds": 5, "return_code": False},
        })
        assert ok["status"] == "ok"
        assert ok["lean_status"] == "accepted"

        bad = call_tool("lean_check", {
            "request_id": "bad",
            "lean_code": make_identity_code(marker="SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
            "policy": {"timeout_seconds": 5, "return_code": False},
        })
        assert bad["status"] == "rejected"
        assert bad["lean_status"] == "rejected"
        assert any(d["kind"] == "unknown_identifier" for d in bad["diagnostics"])


def test_local_behavior_simulation_passes_contracts():
    out = call_tool("shadowproof_local_behavior_simulation", {"request_id": "sim"})
    assert out["status"] == "ok"
    assert out["passed"] == out["total"]
    assert out["total"] >= 6


def test_local_simulation_schema_rejects_string_bool():
    errors = validate_tool_payload("shadowproof_local_behavior_simulation", {"include_observed": "false"})
    assert errors
    assert any("include_observed" in e for e in errors)


def test_theorem_lock_fixture_is_rejected_before_lean():
    with local_mock_lean_env():
        out = call_tool("shadowproof_validate_draft", {
            "request_id": "drift",
            "draft": make_identity_draft(drift=True),
            "policy": {"timeout_seconds": 5, "max_iterations": 0, "return_code": False},
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
        })
    assert out["status"] in {"error", "rejected"}
    assert out["lean_status"] == "not_run"
    assert any(d["kind"] == "theorem_drift" for d in out["diagnostics"])
