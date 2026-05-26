from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from .learning import estimate_tokens
from .path_guard import resolve_under_allowed_root


HUMAN_REVIEW_KINDS = {"human_review_trap", "glutty_trap", "no_glutty_j_trap", "contradiction_trap"}


@dataclass
class EvalCaseResult:
    case_id: str
    kind: str
    expected_status: str | None
    expected_lean_status: str | None
    expected_human_review: bool | None
    actual_status: str | None
    actual_lean_status: str | None
    actual_disposition: str | None
    passed: bool
    accepted: bool
    rejected: bool
    unchecked: bool
    needs_repair: bool
    human_review: bool
    theorem_drift_trap: bool
    false_theorem_drift_escape: bool
    human_review_escalation_expected: bool
    missed_human_review_escalation: bool
    unexpected_human_review_escalation: bool
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
    actual_disposition = extract_disposition(response)
    expected_status = case.get("expect_status")
    expected_lean_status = case.get("expect_lean_status")
    expected_human_review = case.get("expect_human_review")
    if expected_human_review is not None:
        expected_human_review = bool(expected_human_review)

    status_ok = True if expected_status is None else actual_status == expected_status
    lean_ok = True if expected_lean_status is None else actual_lean_status == expected_lean_status
    human_review = is_human_review_response(response)
    hr_ok = True if expected_human_review is None else human_review == expected_human_review
    passed = bool(status_ok and lean_ok and hr_ok)

    diagnostics = response.get("diagnostics", []) or []
    diag_counts: dict[str, int] = {}
    for d in diagnostics:
        k = str(d.get("kind", "unknown")) if isinstance(d, dict) else "unknown"
        diag_counts[k] = diag_counts.get(k, 0) + 1

    theorem_drift_trap = kind in {"theorem_drift_trap", "security_trap"} or bool(case.get("is_theorem_drift_trap", False))
    false_escape = theorem_drift_trap and actual_status == "ok" and actual_lean_status == "accepted"

    human_review_expected = bool(expected_human_review) or kind in HUMAN_REVIEW_KINDS or bool(case.get("is_human_review_trap", False))
    missed_hr = human_review_expected and not human_review
    unexpected_hr = (not human_review_expected) and human_review

    patches = response.get("patches", []) or []
    final_code = response.get("final_lean_code") or ""
    token_basis = json.dumps(input_payload, ensure_ascii=False) + "\n" + final_code + "\n" + json.dumps(diagnostics, ensure_ascii=False)

    return EvalCaseResult(
        case_id=case_id,
        kind=kind,
        expected_status=expected_status,
        expected_lean_status=expected_lean_status,
        expected_human_review=expected_human_review,
        actual_status=actual_status,
        actual_lean_status=actual_lean_status,
        actual_disposition=actual_disposition,
        passed=passed,
        accepted=(actual_status == "ok" and actual_lean_status == "accepted"),
        rejected=(actual_status == "rejected"),
        unchecked=(actual_status == "unchecked" or actual_lean_status in {"not_available", "not_run", "timeout"}),
        needs_repair=(actual_status == "needs_repair"),
        human_review=human_review,
        theorem_drift_trap=theorem_drift_trap,
        false_theorem_drift_escape=false_escape,
        human_review_escalation_expected=human_review_expected,
        missed_human_review_escalation=missed_hr,
        unexpected_human_review_escalation=unexpected_hr,
        repair_turns=len(patches),
        estimated_tokens=estimate_tokens(token_basis),
        elapsed_ms=int((time.monotonic() - start) * 1000),
        diagnostics_summary=diag_counts,
    )


def extract_disposition(response: dict[str, Any]) -> str | None:
    state = response.get("shadowhott_state")
    if isinstance(state, dict):
        for key in ("disposition", "verdict", "status"):
            value = state.get(key)
            if isinstance(value, str):
                return value
    cert = response.get("certificate")
    if isinstance(cert, dict) and cert.get("human_review_required") is True:
        return "human_review"
    status = response.get("status")
    return str(status) if status is not None else None


def is_human_review_response(response: dict[str, Any]) -> bool:
    if response.get("status") == "human_review":
        return True
    if extract_disposition(response) == "human_review":
        return True
    cert = response.get("certificate")
    if isinstance(cert, dict) and cert.get("human_review_required") is True:
        return True
    state = response.get("shadowhott_state")
    if isinstance(state, dict):
        valuation = state.get("global_valuation") or state.get("valuation")
        if isinstance(valuation, dict) and valuation.get("truth") is True and valuation.get("refutation") is True:
            return True
    return False


def resolve_case_path(base_dir: Path, p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = base_dir / path
    return resolve_under_allowed_root(path, must_exist=True, kind="eval input_file")


def compute_metrics(results: list[EvalCaseResult]) -> dict[str, Any]:
    accepted = [r for r in results if r.accepted]
    drift_traps = [r for r in results if r.theorem_drift_trap]
    false_escapes = [r for r in results if r.false_theorem_drift_escape]
    human_expected = [r for r in results if r.human_review_escalation_expected]
    human_correct = [r for r in human_expected if r.human_review]
    human_reviewed = [r for r in results if r.human_review]
    missed_hr = [r for r in results if r.missed_human_review_escalation]
    unexpected_hr = [r for r in results if r.unexpected_human_review_escalation]
    needs_repair = [r for r in results if r.needs_repair]

    accepted_tokens = sum(r.estimated_tokens for r in accepted)
    accepted_turns = sum(r.repair_turns for r in accepted)
    accepted_count = len(accepted)
    elapsed = [r.elapsed_ms for r in results]
    tokens = [r.estimated_tokens for r in results]

    return {
        "case_count": len(results),
        "passed_count": sum(1 for r in results if r.passed),
        "failed_count": sum(1 for r in results if not r.passed),
        "accepted_count": accepted_count,
        "rejected_count": sum(1 for r in results if r.rejected),
        "unchecked_count": sum(1 for r in results if r.unchecked),
        "needs_repair_count": len(needs_repair),
        "human_review_count": len(human_reviewed),
        "expected_human_review_count": len(human_expected),
        "missed_human_review_escalation_count": len(missed_hr),
        "unexpected_human_review_escalation_count": len(unexpected_hr),
        "human_review_escalation_accuracy": (len(human_correct) / len(human_expected)) if human_expected else None,
        "acceptance_rate": (accepted_count / len(results)) if results else 0.0,
        "repair_request_rate": (len(needs_repair) / len(results)) if results else 0.0,
        "total_estimated_tokens": sum(tokens),
        "avg_estimated_tokens": (sum(tokens) / len(tokens)) if tokens else None,
        "median_estimated_tokens": statistics.median(tokens) if tokens else None,
        "avg_elapsed_ms": (sum(elapsed) / len(elapsed)) if elapsed else None,
        "p95_elapsed_ms": percentile(elapsed, 95) if elapsed else None,
        "tokens_per_accepted_proof": (accepted_tokens / accepted_count) if accepted_count else None,
        "repair_turns_per_accepted_proof": (accepted_turns / accepted_count) if accepted_count else None,
        "theorem_drift_trap_count": len(drift_traps),
        "false_theorem_drift_escape_count": len(false_escapes),
        "false_theorem_drift_escape_rate": (len(false_escapes) / len(drift_traps)) if drift_traps else 0.0,
    }


def percentile(values: list[int], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = (len(ordered) - 1) * (pct / 100)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return float(ordered[lo] * (1 - frac) + ordered[hi] * frac)
