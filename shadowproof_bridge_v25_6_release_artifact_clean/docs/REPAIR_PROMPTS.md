# Repair prompts

A repair prompt is a compact, model-facing instruction object.

Instead of sending raw Lean output, ShadowProof sends:

```text
THEOREM FINGERPRINT
DIAGNOSTIC SUMMARY
REPAIR STRATEGIES, RANKED
INVARIANTS
OUTPUT CONTRACT
```

## Example

```text
Repair class: unknown_identifier
Likely cause: wrong theorem name.
Try: simpa using mul_assoc a b c
Invariant: preserve theorem_fingerprint exactly.
Output: DraftProposal JSON only.
```

## Why compact prompts work better

Large Lean error dumps waste context and make the model overfit to noise.

A compact prompt preserves:

- exact theorem lock
- error kind
- actionable strategy
- output schema requirement

while stripping:

- repeated paths
- irrelevant elaborator traces
- huge raw context
```

## Token budget

The compiler accepts:

```json
{"max_prompt_tokens": 900}
```

It estimates token cost and trims diagnostic detail before trimming invariants.
