# DraftProposal protocol

The DraftProposal is the object an LLM should produce before Lean is invoked.

## Purpose

It prevents the model from saying:

> "Here is a proof."

and instead forces it to say:

> "Here is the exact Lean theorem, here is the intended theorem fingerprint, here is the proof graph, here is how the prose maps to Lean, and here are my trust claims."

## Required fields

```text
proposal_id
source_language
target_system
theorem_name
imports
natural_language_theorem
natural_language_proof
lean_code
theorem_fingerprint
proof_graph
nl_to_lean_map
declared_trust
```

## Theorem fingerprint

The theorem fingerprint is the theorem-lock.

```json
{
  "theorem_family": "group_assoc",
  "objects": ["G : Type u", "[Group G]", "a b c : G"],
  "assumptions": [],
  "conclusion": "(a * b) * c = a * (b * c)",
  "forbidden_drift": ["CommGroup", "axiom", "unsafe", "#eval", "run_cmd", "sorry"],
  "source_theorem": "Let G be a group..."
}
```

Patches may alter tactics, proof terms, local lemmas, and imports.

Patches may not silently alter objects, assumptions, or conclusion.

## Declared trust

```json
{
  "uses_sorry": false,
  "uses_axioms": false,
  "mutates_theorem": false,
  "notes": []
}
```

If the Lean code contains `sorry` but the proposal declares `uses_sorry=false`, the bridge rejects before Lean runs.

## ShadowHoTT proof graph

Each proof node carries:

```text
truth lane:    what the step claims
falsity lane:  what would break the step
boundary lane: ambiguous or missing formal bridge data
```

This lets the model receive useful diagnostics rather than a raw Lean error blob.
