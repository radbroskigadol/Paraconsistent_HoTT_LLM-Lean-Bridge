# Local behavior simulation

ShadowProof Bridge can model the buyer-side Lean/LLM integration behavior locally without requiring a live Lean installation or a frontier-model API key.

This is a deterministic contract model, not a proof oracle and not a model-quality benchmark.

## What it exercises

`shadowproof_local_behavior_simulation` runs a compact integration path using local stand-ins:

1. `shadowproof_model_provider_call` with `provider=local_deterministic`.
2. `lean_check` using `scripts/mock_lean.py` through the same `LeanRunner` subprocess path used by `lake env lean`.
3. Accepted draft validation producing a certificate and ShadowHoTT state.
4. Rejected draft validation producing structured Lean-like diagnostics and repair-prompt context.
5. Theorem-lock rejection before Lean execution when the Lean theorem header drifts from the fingerprint.

## CLI

```bash
shadowproof local-sim examples/local_simulation/request.json
```

or directly:

```bash
python -m shadowproof_core.cli local-sim examples/local_simulation/request.json
```

## HTTP/ASGI

```bash
curl -sS -X POST http://127.0.0.1:8765/shadowproof_local_behavior_simulation \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"local-sim"}'
```

## Model-provider fixture

The local provider is selected with:

```json
{
  "provider": "local_deterministic",
  "model_id": "local-sim-draft-v1",
  "prompt": "Prove that every natural number n satisfies n = n.",
  "scenario": "valid_identity_draft"
}
```

Supported scenarios:

- `valid_identity_draft`
- `unknown_identifier_draft`
- `theorem_drift_draft`

## Mock Lean markers

`tests` and local demos can insert marker comments into Lean code:

- `SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER`
- `SHADOWPROOF_MOCK_LEAN_TYPE_MISMATCH`
- `SHADOWPROOF_MOCK_LEAN_UNSOLVED_GOALS`
- `SHADOWPROOF_MOCK_LEAN_MISSING_IMPORT`
- `SHADOWPROOF_MOCK_LEAN_TIMEOUT`

The mock emits Lean-shaped stderr so `diagnostics.parse_lean_output` is exercised.

## Limitations

The local simulator does not establish Lean kernel truth, Mathlib compatibility, frontier-model reasoning quality, provider auth behavior, provider latency, provider rate limits, or streaming behavior. Those remain deployment/integration checks.
