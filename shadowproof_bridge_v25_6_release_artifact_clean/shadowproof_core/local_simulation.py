from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def mock_lean_command() -> str:
    """Return a deployment-owned Lean command that exercises LeanRunner locally.

    This is intentionally a subprocess command, not an in-process shortcut, so
    tests hit the same shlex/subprocess/timeout/diagnostic-parser path that a
    real ``lake env lean`` command would use.
    """
    return f"{sys.executable} {package_root() / 'scripts' / 'mock_lean.py'}"


@contextmanager
def local_mock_lean_env(command: str | None = None):
    old = os.environ.get("SHADOWPROOF_LEAN_CMD")
    os.environ["SHADOWPROOF_LEAN_CMD"] = command or mock_lean_command()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("SHADOWPROOF_LEAN_CMD", None)
        else:
            os.environ["SHADOWPROOF_LEAN_CMD"] = old


def make_identity_code(theorem_name: str = "local_id", marker: str | None = None) -> str:
    marker_line = f"-- {marker}\n" if marker else ""
    return (
        "import Mathlib\n\n"
        f"{marker_line}"
        f"theorem {theorem_name} (n : Nat) : n = n := by\n"
        "  rfl\n"
    )


def make_identity_draft(theorem_name: str = "local_id", marker: str | None = None, *, drift: bool = False) -> dict[str, Any]:
    header_var = "m" if drift else "n"
    code = (
        "import Mathlib\n\n"
        + (f"-- {marker}\n" if marker else "")
        + f"theorem {theorem_name} ({header_var} : Nat) : {header_var} = {header_var} := by\n"
        + "  rfl\n"
    )
    return {
        "proposal_id": f"local-sim-{theorem_name}",
        "source_language": "controlled_math_english",
        "target_system": "lean4",
        "theorem_name": theorem_name,
        "imports": ["Mathlib"],
        "natural_language_theorem": "For every natural number n, n equals n.",
        "natural_language_proof": "By reflexivity.",
        "lean_code": code,
        "theorem_fingerprint": {
            "theorem_family": "reflexivity_identity",
            "objects": ["n : Nat"],
            "assumptions": [],
            "conclusion": "n = n",
            "forbidden_drift": ["sorry", "axiom", "unsafe", "#eval", "run_cmd"],
            "source_theorem": "For every natural number n, n equals n.",
        },
        "proof_graph": [
            {
                "id": "p1",
                "source_text": "By reflexivity.",
                "truth": {"claim": "n = n follows by reflexivity", "dependencies": [], "lean_goal": "n = n"},
                "falsity": {"counterconditions": [], "counterexample_hint": None},
                "boundary": {"ambiguities": [], "missing_data": [], "lean_error_excerpt": None},
                "paths": [
                    {"id": "refl_p1", "source": "p1", "target": "p1", "label": "top", "witness": "J/reflexivity", "kind": "refl"}
                ],
            }
        ],
        "nl_to_lean_map": [
            {
                "source_step_id": "p1",
                "source_text": "By reflexivity.",
                "lean_fragment": "rfl",
                "intended_claim": "n = n",
                "confidence": "high",
            }
        ],
        "declared_trust": {"uses_sorry": False, "uses_axioms": False, "mutates_theorem": False, "notes": ["local simulation fixture"]},
        "metadata": {"local_simulation": True, "drift_fixture": drift},
    }


def _pass(name: str, observed: dict[str, Any], predicate: Callable[[dict[str, Any]], bool], expectation: str) -> dict[str, Any]:
    try:
        ok = bool(predicate(observed))
    except Exception as e:
        ok = False
        observed = {"exception": str(e), "observed": observed}
    return {
        "name": name,
        "passed": ok,
        "expectation": expectation,
        "observed_status": observed.get("status"),
        "observed_lean_status": observed.get("lean_status"),
        "diagnostic_kinds": [d.get("kind") for d in observed.get("diagnostics", []) if isinstance(d, dict)],
        "observed": observed if not ok else _compact_observed(observed),
    }


def _compact_observed(response: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("request_id", "tool", "status", "lean_status", "model_id", "estimated_input_tokens", "estimated_output_tokens"):
        if key in response:
            compact[key] = response[key]
    if response.get("certificate"):
        cert = response["certificate"] or {}
        compact["certificate"] = {
            "accepted_by_lean": cert.get("accepted_by_lean"),
            "bilattice_label": cert.get("bilattice_label"),
            "theorem_name": cert.get("theorem_name"),
        }
    if response.get("diagnostics"):
        compact["diagnostics"] = [
            {"severity": d.get("severity"), "kind": d.get("kind"), "source": d.get("source")}
            for d in response.get("diagnostics", []) if isinstance(d, dict)
        ]
    return compact


def run_local_behavior_simulation(payload: dict[str, Any], tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Exercise the live integration contract with local deterministic stand-ins.

    This does not claim Lean-kernel truth or frontier-model quality.  It checks
    that the package can run the same dispatch, provider, LeanRunner, theorem-
    lock, certificate, and repair-context paths that a buyer would connect to
    real services.
    """
    request_id = str(payload.get("request_id", "local_behavior_simulation"))
    include_observed = bool(payload.get("include_observed", False))
    checks: list[dict[str, Any]] = []

    provider_response = tool_caller("shadowproof_model_provider_call", {
        "request_id": f"{request_id}:provider",
        "provider": "local_deterministic",
        "model_id": "local-sim-draft-v1",
        "prompt": "Prove that every natural number n satisfies n = n.",
        "scenario": "valid_identity_draft",
        "return_raw": True,
    })
    checks.append(_pass(
        "model_provider_contract",
        provider_response,
        lambda r: r.get("status") == "ok" and r.get("model_id") == "local-sim-draft-v1" and "local simulation" in str(r.get("text", "")).lower(),
        "local deterministic provider returns a parseable, non-empty DraftProposal-like response",
    ))

    with local_mock_lean_env(str(payload.get("mock_lean_command")) if payload.get("mock_lean_command") else None):
        accept_response = tool_caller("lean_check", {
            "request_id": f"{request_id}:lean_accept",
            "lean_code": make_identity_code(),
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
            "policy": {"timeout_seconds": 5, "return_code": False},
        })
        checks.append(_pass(
            "mock_lean_acceptance_contract",
            accept_response,
            lambda r: r.get("status") == "ok" and r.get("lean_status") == "accepted",
            "LeanRunner subprocess path accepts the valid local fixture",
        ))

        reject_response = tool_caller("lean_check", {
            "request_id": f"{request_id}:lean_reject",
            "lean_code": make_identity_code(marker="SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
            "policy": {"timeout_seconds": 5, "return_code": False},
        })
        checks.append(_pass(
            "mock_lean_rejection_contract",
            reject_response,
            lambda r: r.get("status") == "rejected" and r.get("lean_status") == "rejected" and any(d.get("kind") == "unknown_identifier" for d in r.get("diagnostics", []) if isinstance(d, dict)),
            "LeanRunner subprocess path converts Lean-like stderr into structured diagnostics",
        ))

        draft_accept = tool_caller("shadowproof_validate_draft", {
            "request_id": f"{request_id}:draft_accept",
            "draft": make_identity_draft(),
            "policy": {"timeout_seconds": 5, "max_iterations": 0, "return_code": False, "return_shadowhott_state": True},
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
        })
        checks.append(_pass(
            "draft_validation_certificate_contract",
            draft_accept,
            lambda r: r.get("status") == "ok" and r.get("lean_status") == "accepted" and (r.get("certificate") or {}).get("accepted_by_lean") is True and r.get("shadowhott_state") is not None,
            "validate_draft produces accepted status, certificate, and ShadowHoTT state against the local Lean model",
        ))

        draft_reject = tool_caller("shadowproof_validate_draft", {
            "request_id": f"{request_id}:draft_reject",
            "draft": make_identity_draft(marker="SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
            "policy": {"timeout_seconds": 5, "max_iterations": 0, "return_code": False, "return_shadowhott_state": True, "auto_repair_context": True},
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
        })
        checks.append(_pass(
            "draft_repair_context_contract",
            draft_reject,
            lambda r: r.get("status") == "needs_repair" and r.get("lean_status") == "rejected" and r.get("compiled_repair_prompt") is not None,
            "failed draft validation attaches repair context/prompt without calling an external LLM",
        ))

        drift_response = tool_caller("shadowproof_validate_draft", {
            "request_id": f"{request_id}:drift",
            "draft": make_identity_draft(drift=True),
            "policy": {"timeout_seconds": 5, "max_iterations": 0, "return_code": False},
            "target": {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False},
        })
        checks.append(_pass(
            "theorem_lock_rejection_contract",
            drift_response,
            lambda r: r.get("status") in {"error", "rejected"} and r.get("lean_status") == "not_run" and any(d.get("kind") == "theorem_drift" for d in r.get("diagnostics", []) if isinstance(d, dict)),
            "theorem-lock rejects a mutated theorem before Lean execution",
        ))

    if not include_observed:
        for check in checks:
            check.pop("observed", None)

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    status = "ok" if passed == total else "failed"
    return {
        "status": status,
        "simulation_mode": "local_deterministic_contract_model",
        "local_only_not_claimed": [
            "not a Lean kernel acceptance proof",
            "not a frontier-model quality measurement",
            "not a substitute for provider auth/latency/rate-limit tests",
        ],
        "coverage": [
            "model-provider adapter contract",
            "LeanRunner subprocess acceptance path",
            "LeanRunner subprocess rejection/diagnostic path",
            "DraftProposal static theorem-lock path",
            "validate_draft certificate + ShadowHoTT augmentation path",
            "retrieval-free repair prompt attachment path",
        ],
        "passed": passed,
        "total": total,
        "checks": checks,
    }
