# OpenAI / native tool integration shape

## Goal

Expose Lean as a first-class mathematical verifier to a model without trusting the model's prose.

## Recommended tool split

### `lean_check`

Use when the model already has Lean code.

Input:

```json
{
  "request_id": "abc",
  "lean_code": "import Mathlib\n\nexample : True := by trivial",
  "target": {
    "system": "lean4",
    "imports": ["Mathlib"],
    "allow_sorry": false
  },
  "policy": {
    "timeout_seconds": 30,
    "security_level": "conservative"
  }
}
```

### `shadowproof_validate`

Use when the model has natural-language theorem/proof text or an imperfect proof.

Input:

```json
{
  "request_id": "abc",
  "nl_problem": {
    "theorem": "Let G be a group. For all a b c : G, (a*b)*c = a*(b*c).",
    "proof": "This follows by associativity."
  },
  "target": {
    "system": "lean4",
    "imports": ["Mathlib"],
    "allow_sorry": false
  },
  "policy": {
    "max_iterations": 4,
    "allow_theorem_mutation": false,
    "security_level": "conservative"
  }
}
```

## Output contract

Always return structured JSON with:

```json
{
  "status": "ok | rejected | error | needs_repair | unchecked",
  "lean_status": "accepted | rejected | not_run | not_available | timeout",
  "diagnostics": [],
  "theorem_fingerprint": {},
  "proof_graph": [],
  "patches": [],
  "certificate": null,
  "final_lean_code": null
}
```

## Model-side behavior

The assistant should treat:

- `status=ok` and `lean_status=accepted` as formal acceptance of the emitted Lean theorem only.
- `status=needs_repair` as a request to revise the proof/code while preserving the theorem fingerprint.
- `status=rejected` with `theorem_drift` as a hard warning that the proposed repair mutated the theorem.
- `status=unchecked` as no formal validation.

## Trust boundary

The natural-language theorem and the Lean theorem are not automatically identical.

The theorem fingerprint exists to reduce theorem drift, not eliminate it.
