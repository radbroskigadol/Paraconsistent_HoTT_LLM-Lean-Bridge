# ShadowProof Bridge v25.7 Patch Notes — Lean-Formalized ShadowHoTT Governance Core

## Summary

v25.7 extends ShadowProof's HoTT-inspired layer in the safest high-leverage direction: more of the existing finite ShadowHoTT governance semantics is mirrored inside Lean, without claiming or introducing a full HoTT implementation.

The production Python gateway remains the operational system.  The Lean template now contains a kernel-checkable reference model for:

- the four-valued ShadowHoTT bilattice;
- truth/refutation coordinates;
- designation;
- meet/path-composition and join;
- De Morgan duality;
- disposition routing;
- theorem-fingerprint-preserving patch morphisms;
- and the No-Glutty-J safety invariant.

## New Lean files

Added under `lean_project_template/ShadowProof/`:

- `BilatticeCore.lean`
- `Routing.lean`
- `PatchMorphism.lean`
- `NoGluttyJ.lean`

`lean_project_template/ShadowProof.lean` now imports the full governance reference model.

## Scope boundary

This is deliberately not a full HoTT implementation and does not add cubical, univalence, HIT, or two-level-type-theory assumptions to the production safety boundary.

The formalized scope is finite and auditable:

```text
L = Bool × Bool
truth/refutation coordinates
designation = truth coordinate
meet = truth AND, refutation OR
join = truth OR, refutation AND
De Morgan = coordinate swap
both + accepted routes to human_review, never accept
patch morphisms are theorem-safe only when fingerprints are preserved
```

## Runtime integration

The existing `shadowproof demorgan-symmetry` tool now reports the expanded Lean governance files as the formalization surface.  No public HTTP/API tool count was changed.

## Validation

The v25.7 regression suite adds file-level and runtime guards that verify:

- all new Lean governance files are present;
- the expected theorem names are present;
- the root Lean module imports the new governance files;
- the Python runtime still routes Lean acceptance plus refutation to `human_review`;
- `shadowproof_demorgan_symmetry` advertises the expanded Lean formalization scope.

## Commercial impact

The central buyer-facing claim is now stronger and cleaner:

> ShadowProof does not merely call Lean.  It carries a formally specified acceptance-governance layer: bilattice states, repair routing, fingerprint preservation, and contradiction escalation are mirrored in Lean and regression-checked against the runtime.

## Still outstanding for GA

v25.7 does not remove the existing enterprise-GA blockers:

- third-party security review;
- production isolated Lean worker;
- fresh Lean/Mathlib transcript in the target environment;
- real customer eval corpora;
- customer-specific frontier-model adapters and retrieval integrations;
- trained policy file populated from real customer evals;
- legal/SLA/release-signing work.
