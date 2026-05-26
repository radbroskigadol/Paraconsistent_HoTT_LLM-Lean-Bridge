from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from .shadowhott import build_shadowhott_state, bilattice_axiom_report
from .path_guard import resolve_under_allowed_root


@dataclass
class ShadowHoTTEvalCaseResult:
    case_id: str
    passed: bool
    expected_lane: str | None
    actual_lanes: list[str]
    expected_verdict: str | None
    actual_verdict: str
    expected_repairability: str | None
    actual_repairabilities: list[str]
    expected_patch_kind: str | None
    actual_patch_kinds: list[str]
    expected_theorem_safe: bool | None
    actual_theorem_safe_values: list[bool]
    expected_bilattice_label: str | None
    actual_bilattice_label: str
    axiom_failures: list[str]
    failures: list[str]
    elapsed_ms: int


def run_shadowhott_eval_suite(payload: dict[str, Any]) -> dict[str, Any]:
    suite = payload.get("suite", payload)
    base_dir = resolve_under_allowed_root(payload.get("_suite_base_dir"), default=".", must_exist=True, kind="shadowhott eval base_dir")
    start = time.monotonic()

    results = []
    for case in suite.get("cases", []):
        results.append(run_shadowhott_eval_case(case, base_dir))

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "status": "ok",
        "suite_id": suite.get("suite_id", "shadowhott_eval"),
        "elapsed_ms": elapsed_ms,
        "metrics": compute_shadowhott_metrics(results),
        "bilattice_axioms": bilattice_axiom_report(),
        "case_results": [asdict(r) for r in results],
    }


def run_shadowhott_eval_case(case: dict[str, Any], base_dir: Path) -> ShadowHoTTEvalCaseResult:
    start = time.monotonic()
    case_id = str(case.get("case_id", "case"))

    payload = case.get("input")
    if payload is None and case.get("input_file"):
        path = Path(case["input_file"])
        if not path.is_absolute():
            path = base_dir / path
        path = resolve_under_allowed_root(path, must_exist=True, kind="shadowhott eval input_file")
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}

    # Accept direct state payload or full tool response-style payload.
    if "shadowhott_state" in payload:
        state = payload["shadowhott_state"]
    else:
        state = build_shadowhott_state(payload).to_dict()

    obstructions = state.get("obstructions", []) or []
    patches = state.get("patch_morphisms", []) or []

    actual_lanes = sorted(set(str(o.get("lane", "unknown")) for o in obstructions))
    actual_repairabilities = sorted(set(str(o.get("repairability", "unknown")) for o in obstructions))
    actual_patch_kinds = sorted(set(str(o.get("suggested_patch_kind", "unknown")) for o in obstructions))
    actual_theorem_safe_values = sorted(set(bool(p.get("theorem_safe", False)) for p in patches))
    actual_verdict = str(state.get("verdict", "unknown"))
    actual_bilattice_label = str((state.get("global_label") or {}).get("label", "unknown"))
    axiom_report = bilattice_axiom_report()
    axiom_failures = [] if axiom_report.get("all_passed") else ["bilattice axioms failed"]

    expected_lane = case.get("expect_lane")
    expected_verdict = case.get("expect_verdict")
    expected_repairability = case.get("expect_repairability")
    expected_patch_kind = case.get("expect_patch_kind")
    expected_theorem_safe = case.get("expect_theorem_safe")
    expected_bilattice_label = case.get("expect_bilattice_label") or case.get("expected_bilattice_label")

    failures = list(axiom_failures)
    if expected_lane is not None and expected_lane not in actual_lanes:
        failures.append(f"expected lane {expected_lane}, got {actual_lanes}")
    if expected_verdict is not None and expected_verdict != actual_verdict:
        failures.append(f"expected verdict {expected_verdict}, got {actual_verdict}")
    if expected_repairability is not None and expected_repairability not in actual_repairabilities:
        failures.append(f"expected repairability {expected_repairability}, got {actual_repairabilities}")
    if expected_patch_kind is not None and expected_patch_kind not in actual_patch_kinds:
        failures.append(f"expected patch kind {expected_patch_kind}, got {actual_patch_kinds}")
    if expected_theorem_safe is not None and expected_theorem_safe not in actual_theorem_safe_values:
        failures.append(f"expected theorem_safe {expected_theorem_safe}, got {actual_theorem_safe_values}")
    if expected_bilattice_label is not None and str(expected_bilattice_label) != actual_bilattice_label:
        failures.append(f"expected bilattice label {expected_bilattice_label}, got {actual_bilattice_label}")

    return ShadowHoTTEvalCaseResult(
        case_id=case_id,
        passed=not failures,
        expected_lane=expected_lane,
        actual_lanes=actual_lanes,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        expected_repairability=expected_repairability,
        actual_repairabilities=actual_repairabilities,
        expected_patch_kind=expected_patch_kind,
        actual_patch_kinds=actual_patch_kinds,
        expected_theorem_safe=expected_theorem_safe,
        actual_theorem_safe_values=actual_theorem_safe_values,
        expected_bilattice_label=expected_bilattice_label,
        actual_bilattice_label=actual_bilattice_label,
        axiom_failures=axiom_failures,
        failures=failures,
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


def compute_shadowhott_metrics(results: list[ShadowHoTTEvalCaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    lane_failures = sum(1 for r in results if any("expected lane" in f for f in r.failures))
    verdict_failures = sum(1 for r in results if any("expected verdict" in f for f in r.failures))
    repairability_failures = sum(1 for r in results if any("expected repairability" in f for f in r.failures))
    patch_failures = sum(1 for r in results if any("expected patch kind" in f for f in r.failures))
    theorem_safety_failures = sum(1 for r in results if any("expected theorem_safe" in f for f in r.failures))
    bilattice_label_failures = sum(1 for r in results if any("expected bilattice label" in f for f in r.failures))
    axiom_failures = sum(1 for r in results if r.axiom_failures)

    return {
        "case_count": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "pass_rate": passed / total if total else None,
        "lane_routing_failures": lane_failures,
        "verdict_failures": verdict_failures,
        "repairability_failures": repairability_failures,
        "patch_kind_failures": patch_failures,
        "theorem_safety_failures": theorem_safety_failures,
        "bilattice_label_failures": bilattice_label_failures,
        "axiom_failures": axiom_failures,
    }
