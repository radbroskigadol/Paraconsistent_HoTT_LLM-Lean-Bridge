#!/usr/bin/env bash
# Buyer demo: exercises the read-only diligence surface without requiring
# Lean / Lake to be installed.  Runs in one Python process so repeated CLI
# startup/import cost cannot mask the actual demo behavior.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

from shadowproof_core.tool_api import call_tool

ROOT = Path.cwd()

STEPS = [
    (
        "1. Bilattice axiom + De Morgan order-two report (executable witness)",
        "shadowproof_demorgan_symmetry",
        "examples/tool_requests/demorgan_symmetry.json",
    ),
    (
        "2. Offline training-parameter capacity plan (no GPU required)",
        "shadowproof_training_capacity_plan",
        "examples/optimization/training_capacity_plan.json",
    ),
    (
        "3. ShadowHoTT evaluation suite (verdict assignment from inputs)",
        "shadowproof_shadowhott_eval",
        "examples/evals/shadowhott_eval.json",
    ),
    (
        "4. Cross-suite regression run (composes the eval cases above)",
        "shadowproof_regression_suite",
        "examples/evals/regression_suite.json",
    ),
    (
        "5. Acquisition packet",
        "shadowproof_acquisition_packet",
        "examples/commercial/acquisition_packet.json",
    ),
    (
        "6. Claims boundary (what we do not yet do)",
        "shadowproof_claims_boundary",
        "examples/commercial/acquisition_packet.json",
    ),
    (
        "7. Due-diligence checklist",
        "shadowproof_due_diligence_checklist",
        "examples/commercial/acquisition_packet.json",
    ),
    (
        "8. Investor deck (sections only)",
        "shadowproof_investor_deck",
        "examples/commercial/investor_deck.json",
    ),
]

for title, tool_name, payload_path in STEPS:
    print()
    print("=" * 66)
    print(title)
    print("=" * 66)
    payload_file = ROOT / payload_path
    payload = json.loads(payload_file.read_text(encoding="utf-8"))
    if tool_name in {"shadowproof_eval", "shadowproof_shadowhott_eval", "shadowproof_regression_suite"}:
        payload.setdefault("_suite_base_dir", str(payload_file.parent))
    result = call_tool(tool_name, payload)
    print(json.dumps(result, indent=2, sort_keys=False))
    status = result.get("status")
    if status in {"error", "failed"}:
        raise SystemExit(f"buyer demo step failed: {title}: {status}")

print()
print("Buyer demo complete.")
PY
