#!/usr/bin/env python3
"""Run a local, deterministic, multi-domain synthetic validation trial.

The trial is deliberately hard-bounded: no network, no live Lean, and no live
LLM are required.  It exercises the same CLI -> schema -> tool dispatch ->
DraftProposal -> security/theorem-lock -> LeanRunner subprocess path used by a
buyer pilot, with scripts/mock_lean.py standing in for a Lean binary.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadowproof_core.schema_validation import validate_tool_payload

ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "examples" / "evals" / "synthetic_multidomain_corpus.json"
REPORT_JSON = ROOT / "reports" / "synthetic_validation_metrics_v25_7.json"
REPORT_MD = ROOT / "reports" / "synthetic_validation_metrics_v25_7.md"

POLICY = {
    "max_iterations": 0,
    "timeout_seconds": 5,
    "allow_theorem_mutation": False,
    "security_level": "conservative",
    "return_code": False,
    "return_proof_graph": False,
}
TARGET = {"system": "lean4", "imports": ["Mathlib"], "allow_sorry": False}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def proof_graph(domain: str, theorem_name: str, conclusion: str) -> list[dict[str, Any]]:
    return [{
        "id": f"{theorem_name}_node",
        "source_text": f"Synthetic {domain} proof obligation.",
        "truth": {
            "claim": f"The Lean body is intended to prove {conclusion}.",
            "dependencies": [],
            "lean_goal": conclusion,
        },
        "falsity": {
            "counterconditions": [],
            "counterexample_hint": None,
        },
        "boundary": {
            "ambiguities": [],
            "missing_data": [],
            "lean_error_excerpt": None,
        },
    }]


def draft(
    *,
    case_id: str,
    domain: str,
    theorem_name: str,
    header: str,
    conclusion: str,
    body: str = "  rfl",
    imports: list[str] | None = None,
    prefix: str = "",
    marker: str | None = None,
    objects: list[str] | None = None,
    assumptions: list[str] | None = None,
    forbidden_drift: list[str] | None = None,
    declared: dict[str, Any] | None = None,
    fingerprint_conclusion: str | None = None,
) -> dict[str, Any]:
    imports = imports or ["Mathlib"]
    import_lines = "\n".join(f"import {imp}" for imp in imports)
    marker_line = f"-- {marker}\n" if marker else ""
    code = f"{import_lines}\n\n{prefix}{marker_line}{header} := by\n{body}\n"
    trust = {"uses_sorry": False, "uses_axioms": False, "mutates_theorem": False, "notes": ["synthetic validation fixture"]}
    if declared:
        trust.update(declared)
    return {
        "proposal_id": f"synthetic-{case_id}",
        "source_language": "controlled_math_english",
        "target_system": "lean4",
        "theorem_name": theorem_name,
        "imports": imports,
        "natural_language_theorem": f"Synthetic {domain} case: {conclusion}.",
        "natural_language_proof": "Synthetic fixture body; mock Lean decides acceptance/rejection by deterministic markers.",
        "lean_code": code,
        "theorem_fingerprint": {
            "theorem_family": domain.replace("/", "_"),
            "objects": objects or [],
            "assumptions": assumptions or [],
            "conclusion": fingerprint_conclusion or conclusion,
            "forbidden_drift": forbidden_drift if forbidden_drift is not None else ["sorry", "axiom", "unsafe", "#eval", "run_cmd"],
            "source_theorem": f"Synthetic {domain} case: {conclusion}.",
        },
        "proof_graph": proof_graph(domain, theorem_name, fingerprint_conclusion or conclusion),
        "nl_to_lean_map": [{
            "source_step_id": f"{theorem_name}_node",
            "source_text": "Synthetic fixture body.",
            "lean_fragment": body.strip().splitlines()[0] if body.strip() else "",
            "intended_claim": fingerprint_conclusion or conclusion,
            "confidence": "high",
        }],
        "declared_trust": trust,
        "metadata": {"domain": domain, "synthetic": True, "case_id": case_id},
    }


def case(case_id: str, kind: str, domain: str, draft_payload: dict[str, Any], status: str, lean_status: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "kind": kind,
        "tool": "shadowproof_validate_draft",
        "expect_status": status,
        "expect_lean_status": lean_status,
        "is_theorem_drift_trap": kind in {"theorem_drift_trap", "security_trap"},
        "input": {
            "request_id": f"synthetic:{case_id}",
            "draft": draft_payload,
            "target": TARGET,
            "policy": POLICY,
        },
        "metadata": {"domain": domain},
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    accepted_specs = [
        ("nat_refl", "arithmetic/nat", "theorem nat_refl (n : Nat) : n = n", "n = n", ["n : Nat"]),
        ("logic_imp_id", "logic/propositional", "theorem logic_imp_id (P : Prop) : P → P", "P → P", ["P : Prop"]),
        ("list_refl", "data/list", "theorem list_refl (xs : List Nat) : xs = xs", "xs = xs", ["xs : List Nat"]),
        ("order_refl", "order/nat", "theorem order_refl (n : Nat) : n ≤ n", "n ≤ n", ["n : Nat"]),
        ("set_elem_refl", "set/basic", "theorem set_elem_refl (x : Nat) : x = x", "x = x", ["x : Nat"]),
        ("ring_add_refl", "algebra/ring", "theorem ring_add_refl (R : Type) [Semiring R] (x : R) : x + 0 = x + 0", "x + 0 = x + 0", ["R : Type", "[Semiring R]", "x : R"]),
        ("group_assoc_synth", "algebra/group", "theorem group_assoc_synth {G : Type} [Group G] (a b c : G) : (a * b) * c = a * (b * c)", "(a * b) * c = a * (b * c)", ["G : Type", "[Group G]", "a b c : G"]),
        ("topology_self", "topology/basic", "theorem topology_self (X : Type) (x : X) : x = x", "x = x", ["X : Type", "x : X"]),
        ("category_id", "category/basic", "theorem category_id (C : Type) (x : C) : x = x", "x = x", ["C : Type", "x : C"]),
        ("number_theory_self", "number_theory/basic", "theorem number_theory_self (p : Nat) : p = p", "p = p", ["p : Nat"]),
        ("analysis_real_self", "analysis/basic", "theorem analysis_real_self (x : Nat) : x = x", "x = x", ["x : Nat"]),
        ("combinatorics_fin_self", "combinatorics/basic", "theorem combinatorics_fin_self (n : Nat) : n = n", "n = n", ["n : Nat"]),
    ]
    for case_id, domain, header, conclusion, objects in accepted_specs:
        cases.append(case(case_id, "accepted_proof", domain, draft(
            case_id=case_id, domain=domain, theorem_name=case_id, header=header,
            conclusion=conclusion, objects=objects,
        ), "ok", "accepted"))

    lean_failures = [
        ("lean_unknown_identifier", "algebra/group", "SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
        ("lean_type_mismatch", "arithmetic/nat", "SHADOWPROOF_MOCK_LEAN_TYPE_MISMATCH"),
        ("lean_unsolved_goals", "logic/propositional", "SHADOWPROOF_MOCK_LEAN_UNSOLVED_GOALS"),
        ("lean_missing_import_diag", "data/list", "SHADOWPROOF_MOCK_LEAN_MISSING_IMPORT"),
        ("lean_unknown_identifier_order", "order/nat", "SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
        ("lean_type_mismatch_set", "set/basic", "SHADOWPROOF_MOCK_LEAN_TYPE_MISMATCH"),
    ]
    for case_id, domain, marker in lean_failures:
        cases.append(case(case_id, "lean_rejection", domain, draft(
            case_id=case_id, domain=domain, theorem_name=case_id,
            header=f"theorem {case_id} (n : Nat) : n = n", conclusion="n = n", marker=marker,
            objects=["n : Nat"],
        ), "needs_repair", "rejected"))

    security_cases = [
        ("security_sorry", "logic/propositional", "  sorry", {}, ["sorry", "axiom"]),
        ("security_axiom", "logic/propositional", "  trivial", {}, ["sorry", "axiom"]),
        ("security_unsafe", "runtime/io", "  rfl", {}, ["sorry", "axiom"]),
        ("security_eval", "runtime/io", "  rfl", {}, ["sorry", "axiom"]),
        ("security_import_allowlist", "imports/boundary", "  rfl", {}, ["sorry", "axiom"]),
        ("security_comment_string_block", "parser/security", "  rfl", {}, ["sorry", "axiom"]),
    ]
    for case_id, domain, body, declared, forbidden in security_cases:
        imports = ["Mathlib"]
        prefix = ""
        expected_status = "error"
        if case_id == "security_axiom":
            prefix = "axiom forbidden_fixture : True\n"
            expected_status = "rejected"
        elif case_id == "security_sorry":
            expected_status = "rejected"
        elif case_id == "security_unsafe":
            prefix = "unsafe def unsafe_fixture := 0\n"
        elif case_id == "security_eval":
            prefix = "#eval IO.println \"blocked\"\n"
        elif case_id == "security_import_allowlist":
            imports = ["Untrusted.Module"]
        elif case_id == "security_comment_string_block":
            prefix = 'def marker := "/-"\naxiom hidden_after_string_delimiter : True\ndef marker2 := "-/"\n'
            expected_status = "rejected"
        cases.append(case(case_id, "security_trap", domain, draft(
            case_id=case_id, domain=domain, theorem_name=case_id,
            header=f"theorem {case_id} (n : Nat) : n = n", conclusion="n = n", body=body,
            imports=imports, prefix=prefix, objects=["n : Nat"], declared=declared,
            forbidden_drift=forbidden,
        ), expected_status, "not_run"))

    drift_cases = [
        ("drift_conclusion_mismatch", "theorem_lock/conclusion", {}, "n = Nat.succ n", ["n : Nat"], "theorem drift_conclusion_mismatch (n : Nat) : n = n", "n = n", ""),
        ("drift_object_missing", "theorem_lock/object", {}, None, ["zzzz : Nat"], "theorem drift_object_missing (n : Nat) : n = n", "n = n", ""),
        ("drift_forbidden_commgroup", "theorem_lock/forbidden_token", {}, None, ["G : Type"], "theorem drift_forbidden_commgroup (G : Type) [CommGroup G] (a : G) : a = a", "a = a", ""),
        ("drift_declared_mutation", "theorem_lock/declared_trust", {"mutates_theorem": True}, None, ["n : Nat"], "theorem drift_declared_mutation (n : Nat) : n = n", "n = n", ""),
        ("drift_header_missing", "theorem_lock/header", {}, None, ["n : Nat"], "def drift_header_missing_value : Nat", "n = n", "0"),
        ("drift_comment_string_line", "parser/security", {}, None, ["n : Nat"], "theorem drift_comment_string_line (n : Nat) : n = n", "n = n", ""),
    ]
    for case_id, domain, declared, fp_conclusion, objects, header, conclusion, body_override in drift_cases:
        prefix = ""
        body = body_override or "  rfl"
        if case_id == "drift_comment_string_line":
            prefix = 'def lineMarker := "--"\naxiom hidden_after_line_string : True\n'
        forbidden = ["sorry", "axiom", "unsafe", "#eval", "run_cmd"]
        if case_id == "drift_forbidden_commgroup":
            forbidden.append("CommGroup")
        cases.append(case(case_id, "theorem_drift_trap", domain, draft(
            case_id=case_id, domain=domain, theorem_name=case_id,
            header=header, conclusion=conclusion, body=body, prefix=prefix,
            objects=objects, declared=declared, fingerprint_conclusion=fp_conclusion,
            forbidden_drift=forbidden,
        ), "rejected", "not_run"))

    return cases


def write_corpus() -> dict[str, Any]:
    suite = {
        "request_id": "synthetic_multidomain_v25_7",
        "suite_id": "synthetic_multidomain_v25_7",
        "cases": build_cases(),
    }
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps(suite, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return suite


def schema_verify(suite: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    top = validate_tool_payload("shadowproof_eval", suite)
    if top:
        errors["shadowproof_eval"] = top
    for c in suite["cases"]:
        nested = validate_tool_payload(c.get("tool", "shadowproof_validate_draft"), c["input"])
        if nested:
            errors[c["case_id"]] = nested
    return {"schema_valid": not errors, "schema_error_count": sum(len(v) for v in errors.values()), "schema_errors": errors}


def run_cli_trial() -> dict[str, Any]:
    env = dict(os.environ)
    fast_mock = ROOT / "scripts" / "mock_lean_fast.sh"
    if fast_mock.exists():
        env["SHADOWPROOF_LEAN_CMD"] = str(fast_mock)
    else:
        env["SHADOWPROOF_LEAN_CMD"] = f"{sys.executable} {ROOT / 'scripts' / 'mock_lean.py'}"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "shadowproof_core.cli", "eval", str(CORPUS_PATH)],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"synthetic validation CLI failed with {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return json.loads(proc.stdout)


def summarize_by_domain(case_results: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    domain_by_id = {c["case_id"]: c["metadata"]["domain"] for c in cases}
    out: dict[str, Counter] = defaultdict(Counter)
    for r in case_results:
        domain = domain_by_id.get(r["case_id"], "unknown")
        out[domain]["case_count"] += 1
        out[domain]["passed_count"] += int(bool(r.get("passed")))
        out[domain][f"status:{r.get('actual_status')}"] += 1
        out[domain][f"lean:{r.get('actual_lean_status')}"] += 1
    return {k: dict(v) for k, v in sorted(out.items())}


def build_report(suite: dict[str, Any], raw: dict[str, Any], schema_check: dict[str, Any]) -> dict[str, Any]:
    case_results = raw.get("case_results", [])
    metrics = raw.get("metrics", {})
    kind_counts = Counter(r.get("kind", "unknown") for r in case_results)
    status_counts = Counter(r.get("actual_status", "unknown") for r in case_results)
    lean_counts = Counter(r.get("actual_lean_status", "unknown") for r in case_results)
    diagnostics = Counter()
    for r in case_results:
        for k, v in (r.get("diagnostics_summary") or {}).items():
            diagnostics[k] += int(v)

    verification_checks = {
        "cli_returned_ok_status": raw.get("status") == "ok",
        "schema_valid_before_trial": bool(schema_check["schema_valid"]),
        "all_cases_passed_expected_statuses": metrics.get("case_count") == metrics.get("passed_count"),
        "no_false_theorem_drift_escapes": metrics.get("false_theorem_drift_escape_count") == 0,
        "no_security_trap_accepted": not any(r.get("kind") == "security_trap" and r.get("accepted") for r in case_results),
        "no_theorem_drift_trap_accepted": not any(r.get("kind") == "theorem_drift_trap" and r.get("accepted") for r in case_results),
        "multi_domain_minimum_met": len({c["metadata"]["domain"] for c in suite["cases"]}) >= 10,
    }
    corpus_text = CORPUS_PATH.read_text(encoding="utf-8")
    raw_text = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return {
        "report_id": "synthetic_validation_metrics_v25_7",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_only_limitations": [
            "mock_lean.py is a deterministic subprocess fixture, not the Lean kernel",
            "no live frontier-model generation was used",
            "metrics verify bridge behavior, schema/guardrail behavior, and deterministic acceptance/rejection routing",
        ],
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "command": f"{sys.executable} -m shadowproof_core.cli eval {CORPUS_PATH}",
            "mock_lean_command": str(ROOT / "scripts" / "mock_lean_fast.sh") if (ROOT / "scripts" / "mock_lean_fast.sh").exists() else f"{sys.executable} {ROOT / 'scripts' / 'mock_lean.py'}",
        },
        "corpus": {
            "path": str(CORPUS_PATH.relative_to(ROOT)),
            "sha256": sha256_text(corpus_text),
            "case_count": len(suite["cases"]),
            "domain_count": len({c["metadata"]["domain"] for c in suite["cases"]}),
            "kind_counts": dict(sorted(kind_counts.items())),
        },
        "schema_verification": schema_check,
        "metrics": metrics,
        "status_counts": dict(sorted(status_counts.items())),
        "lean_status_counts": dict(sorted(lean_counts.items())),
        "diagnostic_kind_counts": dict(sorted(diagnostics.items())),
        "by_domain": summarize_by_domain(case_results, suite["cases"]),
        "verification_checks": verification_checks,
        "verified": all(verification_checks.values()),
        "raw_eval_sha256": sha256_text(raw_text),
        "raw_eval": raw,
    }


def write_markdown(report: dict[str, Any]) -> None:
    m = report["metrics"]
    lines = [
        "# Synthetic Multi-Domain Validation Metrics — v25.7",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`",
        "",
        "## Scope",
        "",
        "This report is generated by `scripts/run_synthetic_validation_trial.py` using the package CLI and the configured deterministic mock Lean command (`scripts/mock_lean_fast.sh` when available, otherwise `scripts/mock_lean.py`). It verifies deterministic bridge behavior across schema validation, theorem-lock rejection, security rejection, LeanRunner routing, and eval metrics. It does not claim Lean-kernel proof acceptance or live frontier-model quality.",
        "",
        "## Corpus and hashes",
        "",
        f"- Corpus: `{report['corpus']['path']}`",
        f"- Corpus SHA-256: `{report['corpus']['sha256']}`",
        f"- Raw eval SHA-256: `{report['raw_eval_sha256']}`",
        f"- Cases: **{report['corpus']['case_count']}**",
        f"- Domains: **{report['corpus']['domain_count']}**",
        "",
        "## Hard metrics",
        "",
        f"- Passed expected statuses: **{m.get('passed_count')} / {m.get('case_count')}**",
        f"- Failed expected statuses: **{m.get('failed_count')}**",
        f"- Accepted proofs under mock Lean: **{m.get('accepted_count')}**",
        f"- Rejected before/without Lean: **{m.get('rejected_count')}**",
        f"- Needs repair after mock Lean rejection: **{m.get('needs_repair_count')}**",
        f"- Unchecked: **{m.get('unchecked_count')}**",
        f"- Theorem/security drift traps: **{m.get('theorem_drift_trap_count')}**",
        f"- False theorem-drift/security escapes: **{m.get('false_theorem_drift_escape_count')}**",
        f"- False escape rate: **{m.get('false_theorem_drift_escape_rate')}**",
        f"- Total estimated tokens: **{m.get('total_estimated_tokens')}**",
        "",
        "## Verification checks",
        "",
    ]
    for k, v in report["verification_checks"].items():
        lines.append(f"- {'PASS' if v else 'FAIL'} — `{k}`")
    lines.extend(["", "## Counts by actual status", ""])
    for k, v in report["status_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Counts by Lean status", ""])
    for k, v in report["lean_status_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Diagnostic kinds", ""])
    for k, v in report["diagnostic_kind_counts"].items():
        lines.append(f"- `{k}`: {v}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    suite = write_corpus()
    schema_check = schema_verify(suite)
    if not schema_check["schema_valid"]:
        print(json.dumps(schema_check, indent=2), file=sys.stderr)
        return 2
    raw = run_cli_trial()
    report = build_report(suite, raw, schema_check)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report)
    print(json.dumps({
        "verified": report["verified"],
        "case_count": report["corpus"]["case_count"],
        "domain_count": report["corpus"]["domain_count"],
        "passed_count": report["metrics"].get("passed_count"),
        "false_theorem_drift_escape_count": report["metrics"].get("false_theorem_drift_escape_count"),
        "report_json": str(REPORT_JSON.relative_to(ROOT)),
        "report_md": str(REPORT_MD.relative_to(ROOT)),
    }, indent=2))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
