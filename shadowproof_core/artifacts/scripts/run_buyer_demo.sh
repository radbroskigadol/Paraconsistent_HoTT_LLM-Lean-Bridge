#!/usr/bin/env bash
# Buyer demo: exercises the read-only diligence surface without requiring
# Lean / Lake to be installed.  Each step prints a section header and the
# JSON response.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
  shift
  python -m shadowproof_core.cli "$@"
}

run "1. Bilattice axiom + De Morgan order-two report (executable witness)" \
    demorgan-symmetry examples/tool_requests/demorgan_symmetry.json

run "2. Offline training-parameter capacity plan (no GPU required)" \
    training-capacity-plan examples/optimization/training_capacity_plan.json

run "3. ShadowHoTT evaluation suite (verdict assignment from inputs)" \
    shadowhott-eval examples/evals/shadowhott_eval.json

run "4. Cross-suite regression run (composes the eval cases above)" \
    regression examples/evals/regression_suite.json

run "5. Acquisition packet" \
    acquisition-packet examples/commercial/acquisition_packet.json

run "6. Claims boundary (what we do not yet do)" \
    claims-boundary examples/commercial/acquisition_packet.json

run "7. Due-diligence checklist" \
    due-diligence-checklist examples/commercial/acquisition_packet.json

run "8. Investor deck (sections only)" \
    investor-deck examples/commercial/investor_deck.json

echo
echo "Buyer demo complete."
