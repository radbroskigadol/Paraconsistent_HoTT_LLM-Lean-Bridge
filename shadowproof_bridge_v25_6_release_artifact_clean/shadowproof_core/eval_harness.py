from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from .learning import estimate_tokens
from .path_guard import resolve_under_allowed_root


@dataclass
class EvalCaseResult:
    case_id: str
    kind: str
    expected_status: str | None
    expected_lean_status: str | None
    actual_status: str | None
    actual_lean_status: str | None
    passed: bool
    accepted: bool
    rejected: bool
    unchecked: bool
    needs_repair: bool
    theorem_drift_trap: bool
    false_theorem_drift_escape: bool
    repair_turns: int
    estimated_tokens: int
    elapsed_ms: int
    diagnostics_summary: dict[str, int]


def run_eval_suite(payload: dict[str, Any], tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    suite = payload.get("suite", payload)
    if "cases" not in suite:
        raise ValueError("Eval payload must include `cases` or `suite.cases`.")

    base_dir = resolve_under_allowed_root(payload.get("_suite_base_dir"), default=".", must_exist=True, kind="eval suite base_dir")
    results: list[EvalCaseResult] = []
    start = time.monotonic()

    for case in suite.get("cases", []):
        results.append(run_eval_case(case, base_dir, tool_caller))

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "status": "ok",
        "suite_id": suite.get("suite_id", "unknown"),
        "elapsed_ms": elapsed_ms,
        "metrics": compute_metrics(results),
        "case_results": [asdict(r) for r in results],
    }


def run_eval_case(case: dict[str, Any], base_dir: Path, tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> EvalCaseResult:
    start = time.monotonic()
    case_id = str(case.get("case_id", "case"))
    kind = str(case.get("kind", "unknown"))

    input_payload = case.get("input")
    if input_payload is None and case.get("input_file"):
        input_file = resolve_case_path(base_dir, str(case["input_file"]))
        input_payload = json.loads(input_file.read_text(encoding="utf-8"))
    if input_payload is None:
        input_payload = {}

    tool = str(case.get("tool", "shadowproof_validate_draft"))
    response = tool_caller(tool, input_payload)

    actual_status = response.get("status")
    actual_lean_status = response.get("lean_status")
    expected_status = case.get("expect_status")
    expected_lean_status = case.get("expect_lean_status")

    status_ok = True if expected_status is None else actual_status == expected_status
    lean_ok = True if expected_lean_status is None else actual_lean_status == expected_lean_status
    passed = bool(status_ok and lean_ok)

    diagnostics = response.get("diagnostics", []) or []
    diag_counts: dict[str, int] = {}
    for d in diagnostics:
        k = str(d.get("kind", "unknown")) if isinstance(d, dict) else "unknown"
        diag_counts[k] = diag_counts.get(k, 0) + 1

    theorem_drift_trap = kind in {"theorem_drift_trap", "security_trap"} or bool(case.get("is_theorem_drift_trap", False))
    false_escape = theorem_drift_trap and actual_status == "ok" and actual_lean_status == "accepted"

    patches = response.get("patches", []) or []
    final_code = response.get("final_lean_code") or ""
    token_basis = json.dumps(input_payload, ensure_ascii=False) + "\n" + final_code + "\n" + json.dumps(diagnostics, ensure_ascii=False)

    return EvalCaseResult(
        case_id=case_id,
        kind=kind,
        expected_status=expected_status,
        expected_lean_status=expected_lean_status,
        actual_status=actual_status,
        actual_lean_status=actual_lean_status,
        passed=passed,
        accepted=(actual_status == "ok" and actual_lean_status == "accepted"),
        rejected=(actual_status == "rejected"),
        unchecked=(actual_status == "unchecked" or actual_lean_status in {"not_available", "not_run", "timeout"}),
        needs_repair=(actual_status == "needs_repair"),
        theorem_drift_trap=theorem_drift_trap,
        false_theorem_drift_escape=false_escape,
        repair_turns=len(patches),
        estimated_tokens=estimate_tokens(token_basis),
        elapsed_ms=int((time.monotonic() - start) * 1000),
        diagnostics_summary=diag_counts,
    )


def resolve_case_path(base_dir: Path, p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = base_dir / path
    return resolve_under_allowed_root(path, must_exist=True, kind="eval input_file")


def compute_metrics(results: list[EvalCaseResult]) -> dict[str, Any]:
    accepted = [r for r in results if r.accepted]
    drift_traps = [r for r in results if r.theorem_drift_trap]
    false_escapes = [r for r in results if r.false_theorem_drift_escape]

    accepted_tokens = sum(r.estimated_tokens for r in accepted)
    accepted_turns = sum(r.repair_turns for r in accepted)
    accepted_count = len(accepted)

    return {
        "case_count": len(results),
        "passed_count": sum(1 for r in results if r.passed),
        "failed_count": sum(1 for r in results if not r.passed),
        "accepted_count": accepted_count,
        "rejected_count": sum(1 for r in results if r.rejected),
        "unchecked_count": sum(1 for r in results if r.unchecked),
        "needs_repair_count": sum(1 for r in results if r.needs_repair),
        "total_estimated_tokens": sum(r.estimated_tokens for r in results),
        "tokens_per_accepted_proof": (accepted_tokens / accepted_count) if accepted_count else None,
        "repair_turns_per_accepted_proof": (accepted_turns / accepted_count) if accepted_count else None,
        "theorem_drift_trap_count": len(drift_traps),
        "false_theorem_drift_escape_count": len(false_escapes),
        "false_theorem_drift_escape_rate": (len(false_escapes) / len(drift_traps)) if drift_traps else 0.0,
    }
