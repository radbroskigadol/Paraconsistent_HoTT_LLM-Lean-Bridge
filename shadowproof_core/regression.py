from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from .eval_harness import run_eval_suite
from .path_guard import resolve_under_allowed_root
from .learning import estimate_tokens
from .shadowhott_eval import run_shadowhott_eval_suite


@dataclass
class RetrievalEvalCaseResult:
    case_id: str
    passed: bool
    query: str
    expected_candidates: list[str]
    actual_candidates: list[str]
    expected_domains: list[str]
    actual_domains: list[str]
    expected_drift_traps: list[str]
    actual_drift_traps: list[str]
    failures: list[str]
    elapsed_ms: int


@dataclass
class PromptEfficiencyCaseResult:
    case_id: str
    passed: bool
    estimated_prompt_tokens: int | None
    max_expected_tokens: int | None
    retrieval_augmented: bool | None
    expect_retrieval_augmented: bool | None
    required_substrings: list[str]
    missing_substrings: list[str]
    failures: list[str]
    elapsed_ms: int


def run_bridge_regression_suite(payload: dict[str, Any], tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    suite = payload.get("suite", payload)
    base_dir = resolve_under_allowed_root(payload.get("_suite_base_dir"), default=".", must_exist=True, kind="regression suite base_dir")
    start = time.monotonic()

    sections: dict[str, Any] = {}
    overall_failures: list[str] = []

    if suite.get("shadowhott_eval"):
        sh_payload = load_section_payload(suite["shadowhott_eval"], base_dir)
        sh_payload.setdefault("_suite_base_dir", str(resolve_base_for_section(suite["shadowhott_eval"], base_dir)))
        sections["shadowhott_eval"] = run_shadowhott_eval_suite(sh_payload)

    if suite.get("retrieval_eval"):
        sections["retrieval_eval"] = run_retrieval_eval_suite(suite["retrieval_eval"], base_dir, tool_caller)

    if suite.get("prompt_efficiency_eval"):
        sections["prompt_efficiency_eval"] = run_prompt_efficiency_eval_suite(suite["prompt_efficiency_eval"], base_dir, tool_caller)

    if suite.get("bridge_eval"):
        bridge_payload = load_section_payload(suite["bridge_eval"], base_dir)
        bridge_payload.setdefault("_suite_base_dir", str(resolve_base_for_section(suite["bridge_eval"], base_dir)))
        sections["bridge_eval"] = run_eval_suite(bridge_payload, tool_caller)

    # Lean validation cases can be the same shape as bridge eval; separated because
    # these may be skipped/unverified in environments without Lean.
    if suite.get("lean_validation_eval"):
        lean_payload = load_section_payload(suite["lean_validation_eval"], base_dir)
        lean_payload.setdefault("_suite_base_dir", str(resolve_base_for_section(suite["lean_validation_eval"], base_dir)))
        sections["lean_validation_eval"] = run_eval_suite(lean_payload, tool_caller)

    metrics = aggregate_regression_metrics(sections)

    for section_name, section in sections.items():
        m = section.get("metrics", {})
        if m.get("failed_count", 0):
            overall_failures.append(f"{section_name}: {m.get('failed_count')} failures")
        if section_name == "bridge_eval" and m.get("false_theorem_drift_escape_count", 0):
            overall_failures.append("bridge_eval: false theorem-drift escape detected")
        if section_name == "lean_validation_eval" and m.get("false_theorem_drift_escape_count", 0):
            overall_failures.append("lean_validation_eval: false theorem-drift escape detected")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "status": "ok" if not overall_failures else "failed",
        "suite_id": suite.get("suite_id", "bridge_regression"),
        "elapsed_ms": elapsed_ms,
        "metrics": metrics,
        "overall_failures": overall_failures,
        "sections": sections,
    }


def load_section_payload(section_spec: Any, base_dir: Path) -> dict[str, Any]:
    if isinstance(section_spec, str):
        path = resolve_under_allowed_root(base_dir / section_spec, must_exist=True, kind="regression section file")
        return json.loads(path.read_text(encoding="utf-8"))
    if isinstance(section_spec, dict) and "file" in section_spec:
        path = Path(section_spec["file"])
        if not path.is_absolute():
            path = base_dir / path
        path = resolve_under_allowed_root(path, must_exist=True, kind="regression section file")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(section_spec.get("overrides"), dict):
            payload.update(section_spec["overrides"])
        return payload
    if isinstance(section_spec, dict):
        return dict(section_spec)
    return {}


def resolve_base_for_section(section_spec: Any, base_dir: Path) -> Path:
    if isinstance(section_spec, str):
        return resolve_under_allowed_root(base_dir / section_spec, must_exist=True, kind="regression section file").parent
    if isinstance(section_spec, dict) and "file" in section_spec:
        p = Path(section_spec["file"])
        if not p.is_absolute():
            p = base_dir / p
        return resolve_under_allowed_root(p, must_exist=True, kind="regression section file").parent
    return base_dir


def run_retrieval_eval_suite(spec: dict[str, Any], base_dir: Path, tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    start = time.monotonic()
    cases = spec.get("cases", [])
    results = []
    for case in cases:
        results.append(run_retrieval_eval_case(case, base_dir, tool_caller))
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "status": "ok",
        "suite_id": spec.get("suite_id", "retrieval_eval"),
        "elapsed_ms": elapsed_ms,
        "metrics": {
            "case_count": len(results),
            "passed_count": sum(1 for r in results if r.passed),
            "failed_count": sum(1 for r in results if not r.passed),
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else None,
        },
        "case_results": [asdict(r) for r in results],
    }


def run_retrieval_eval_case(case: dict[str, Any], base_dir: Path, tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> RetrievalEvalCaseResult:
    start = time.monotonic()
    case_id = str(case.get("case_id", "retrieval_case"))

    payload = case.get("input")
    if payload is None and case.get("input_file"):
        p = Path(case["input_file"])
        if not p.is_absolute():
            p = base_dir / p
        p = resolve_under_allowed_root(p, must_exist=True, kind="regression input_file")
        payload = json.loads(p.read_text(encoding="utf-8"))
    payload = payload or {}

    response = tool_caller(str(case.get("tool", "shadowproof_retrieve_mathlib")), payload)
    retrieval = response.get("retrieval") or response.get("result") or {}
    candidates = retrieval.get("candidates", [])
    actual_candidates = [str(c.get("name", "")) for c in candidates if isinstance(c, dict)]
    actual_domains = [str(x) for x in retrieval.get("detected_domains", [])]
    actual_drift_traps = [str(x) for x in retrieval.get("drift_traps", [])]

    expected_candidates = [str(x) for x in case.get("expect_candidates", [])]
    expected_domains = [str(x) for x in case.get("expect_domains", [])]
    expected_drift_traps = [str(x) for x in case.get("expect_drift_traps", [])]

    failures = []
    for x in expected_candidates:
        if x not in actual_candidates:
            failures.append(f"expected candidate {x}, got {actual_candidates}")
    for x in expected_domains:
        if x not in actual_domains:
            failures.append(f"expected domain {x}, got {actual_domains}")
    for x in expected_drift_traps:
        if not any(x in trap for trap in actual_drift_traps):
            failures.append(f"expected drift trap containing {x}, got {actual_drift_traps}")

    return RetrievalEvalCaseResult(
        case_id=case_id,
        passed=not failures,
        query=str(payload.get("query", "")),
        expected_candidates=expected_candidates,
        actual_candidates=actual_candidates,
        expected_domains=expected_domains,
        actual_domains=actual_domains,
        expected_drift_traps=expected_drift_traps,
        actual_drift_traps=actual_drift_traps,
        failures=failures,
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


def run_prompt_efficiency_eval_suite(spec: dict[str, Any], base_dir: Path, tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    start = time.monotonic()
    results = [run_prompt_efficiency_case(c, base_dir, tool_caller) for c in spec.get("cases", [])]
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "status": "ok",
        "suite_id": spec.get("suite_id", "prompt_efficiency_eval"),
        "elapsed_ms": elapsed_ms,
        "metrics": {
            "case_count": len(results),
            "passed_count": sum(1 for r in results if r.passed),
            "failed_count": sum(1 for r in results if not r.passed),
            "pass_rate": sum(1 for r in results if r.passed) / len(results) if results else None,
            "avg_estimated_prompt_tokens": (
                sum((r.estimated_prompt_tokens or 0) for r in results) / len(results) if results else None
            ),
        },
        "case_results": [asdict(r) for r in results],
    }


def run_prompt_efficiency_case(case: dict[str, Any], base_dir: Path, tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> PromptEfficiencyCaseResult:
    start = time.monotonic()
    case_id = str(case.get("case_id", "prompt_case"))
    payload = case.get("input")
    if payload is None and case.get("input_file"):
        p = Path(case["input_file"])
        if not p.is_absolute():
            p = base_dir / p
        p = resolve_under_allowed_root(p, must_exist=True, kind="regression input_file")
        payload = json.loads(p.read_text(encoding="utf-8"))
    payload = payload or {}

    response = tool_caller(str(case.get("tool", "shadowproof_compile_repair_prompt")), payload)
    prompt = str(response.get("prompt", ""))
    estimated = response.get("estimated_prompt_tokens")
    if estimated is None:
        estimated = estimate_tokens(prompt)

    max_expected = case.get("max_expected_tokens")
    expect_aug = case.get("expect_retrieval_augmented")
    actual_aug = response.get("retrieval_augmented")

    required = [str(x) for x in case.get("require_substrings", [])]
    missing = [s for s in required if s not in prompt]

    failures = []
    if max_expected is not None and estimated > int(max_expected):
        failures.append(f"estimated tokens {estimated} exceed max {max_expected}")
    if expect_aug is not None and bool(actual_aug) != bool(expect_aug):
        failures.append(f"expected retrieval_augmented={expect_aug}, got {actual_aug}")
    if missing:
        failures.append(f"missing required substrings {missing}")

    return PromptEfficiencyCaseResult(
        case_id=case_id,
        passed=not failures,
        estimated_prompt_tokens=int(estimated) if estimated is not None else None,
        max_expected_tokens=int(max_expected) if max_expected is not None else None,
        retrieval_augmented=bool(actual_aug) if actual_aug is not None else None,
        expect_retrieval_augmented=bool(expect_aug) if expect_aug is not None else None,
        required_substrings=required,
        missing_substrings=missing,
        failures=failures,
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


def aggregate_regression_metrics(sections: dict[str, Any]) -> dict[str, Any]:
    total_cases = 0
    total_failed = 0
    total_passed = 0
    false_drift_escapes = 0
    unchecked = 0

    for section in sections.values():
        m = section.get("metrics", {})
        total_cases += int(m.get("case_count", 0) or 0)
        total_failed += int(m.get("failed_count", 0) or 0)
        total_passed += int(m.get("passed_count", 0) or 0)
        false_drift_escapes += int(m.get("false_theorem_drift_escape_count", 0) or 0)
        unchecked += int(m.get("unchecked_count", 0) or 0)

    return {
        "section_count": len(sections),
        "case_count": total_cases,
        "passed_count": total_passed,
        "failed_count": total_failed,
        "pass_rate": total_passed / total_cases if total_cases else None,
        "false_theorem_drift_escape_count": false_drift_escapes,
        "unchecked_count": unchecked,
    }
