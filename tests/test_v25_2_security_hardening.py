import json
from pathlib import Path

import pytest

from shadowproof_core.auth import build_request_context
from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.path_guard import PathPolicyError, resolve_under_allowed_root
from shadowproof_core.schema_validation import validate_tool_payload
from shadowproof_core.tool_api import call_tool, shadowproof_validate_draft


def test_target_lean_command_is_rejected_before_runner():
    out = call_tool("lean_check", {
        "request_id": "rce-target",
        "lean_code": "theorem t : True := trivial",
        "target": {"system": "lean4", "lean_command": "python /tmp/evil.py"},
        "policy": {"timeout_seconds": 1},
    })
    assert out["status"] == "error"
    assert any("lean_command" in d["message"] for d in out["diagnostics"])


def test_schema_rejects_string_boolean_policy_values():
    errors = validate_tool_payload("lean_check", {
        "request_id": "strict-bool",
        "lean_code": "theorem t : True := trivial",
        "target": {"system": "lean4", "allow_sorry": False},
        "policy": {"return_code": "false"},
    })
    assert errors
    assert any("return_code" in e for e in errors)


def test_theorem_lock_mismatch_rejects_before_lean_even_if_code_is_trivial():
    draft = {
        "proposal_id": "drift",
        "source_language": "english",
        "target_system": "lean4",
        "theorem_name": "t",
        "imports": [],
        "natural_language_theorem": "multiplication is commutative",
        "natural_language_proof": "not supplied",
        "lean_code": "theorem t : True := trivial",
        "theorem_fingerprint": {
            "theorem_family": "commutativity",
            "objects": ["a", "b"],
            "assumptions": [],
            "conclusion": "a * b = b * a",
            "forbidden_drift": [],
            "source_theorem": "multiplication is commutative",
        },
        "proof_graph": [],
        "nl_to_lean_map": [],
        "declared_trust": {"uses_sorry": False, "uses_axioms": False, "mutates_theorem": False, "notes": []},
    }
    out = shadowproof_validate_draft({
        "request_id": "drift",
        "draft": draft,
        "target": {"system": "lean4", "allow_sorry": False},
        "policy": {"max_iterations": 0, "timeout_seconds": 1, "allow_theorem_mutation": False, "security_level": "conservative", "return_code": True, "return_proof_graph": True},
    })
    assert out["status"] == "rejected"
    assert out["lean_status"] == "not_run"
    assert any(d["kind"] == "theorem_drift" and d["severity"] == "error" for d in out["diagnostics"])
    assert "certificate" not in out or out["certificate"] is None


def test_auth_disabled_fails_closed_outside_development():
    cfg = ShadowProofConfig(environment="production", auth_mode="disabled")
    ctx = build_request_context({}, cfg)
    assert ctx.authenticated is False
    assert "disabled" in ctx.reason


def test_path_guard_rejects_absolute_escape(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(allowed))
    inside = allowed / "x.json"
    assert resolve_under_allowed_root(str(inside)) == inside.resolve()
    with pytest.raises(PathPolicyError):
        resolve_under_allowed_root("/etc/passwd", kind="escape")


def test_theorem_lock_string_delimiter_cannot_hide_sorry_or_axiom():
    from shadowproof_core.models import TheoremFingerprint

    fp = TheoremFingerprint(
        theorem_family="security_probe",
        forbidden_drift=["axiom", "sorry"],
    )
    code = 'def openMarker : String := "/-"\naxiom hiddenAxiom : True\ntheorem t : True := by sorry\ndef closeMarker : String := "-/"\n'
    kinds = {d.kind.value if hasattr(d.kind, "value") else str(d.kind) for d in fp.diff_summary(code)}
    assert "axiom_leak" in kinds
    assert "sorry_leak" in kinds
