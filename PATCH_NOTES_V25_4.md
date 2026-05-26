# Patch Notes v0.25.4 — Local behavior simulation

## Purpose

v0.25.4 answers a buyer/diligence question left open by v0.25.3: can the package model the Lean-worker and frontier-model integration behavior locally, without requiring a live Lean installation or real provider key?

Answer: yes, as a deterministic contract/integration simulation. It does not claim Lean-kernel truth or frontier-model quality.

## Added

- `shadowproof_core/local_simulation.py`
  - Generates stable identity-proof DraftProposal fixtures.
  - Provides a local mock Lean environment context.
  - Runs `shadowproof_local_behavior_simulation` over provider, LeanRunner, DraftProposal, certificate, ShadowHoTT, repair-context, and theorem-lock paths.
- `scripts/mock_lean.py`
  - Lean-like subprocess stand-in.
  - Emits parseable Lean-shaped diagnostics for unknown identifiers, type mismatches, unsolved goals, missing imports, and timeouts.
- `provider=local_deterministic`
  - Added to `shadowproof_model_provider_call`.
  - Supports deterministic scenarios: `valid_identity_draft`, `unknown_identifier_draft`, and `theorem_drift_draft`.
- `shadowproof_local_behavior_simulation`
  - Added to Python registry, stdlib HTTP routes, ASGI routes, CLI, schema validation, and OpenAPI generation.
- `docs/LOCAL_SIMULATION.md`
  - Documents CLI/HTTP usage, supported scenarios, mock Lean markers, and limitations.
- `examples/local_simulation/request.json`
  - Minimal local simulation request.
- `tests/test_v25_4_local_simulation.py`
  - Verifies local provider fixtures, mock Lean acceptance/rejection, theorem-lock rejection, schema enforcement, and the full local behavior simulation.

## Verification

- `python -m compileall -q shadowproof_core scripts/mock_lean.py`
- `python -m pytest -q` → 94 passed
- Registry/route/schema audit: 84 tools, 84 routes, 0 route/tool mismatches, 0 tools without input-schema coverage
- CLI smoke: `python -m shadowproof_core.cli local-sim examples/local_simulation/request.json`

## Limitations

The local simulator is not a Lean kernel, not Mathlib compatibility proof, not a model-quality benchmark, and not a replacement for buyer-side provider authentication, latency, streaming, quota, or deployment tests.
