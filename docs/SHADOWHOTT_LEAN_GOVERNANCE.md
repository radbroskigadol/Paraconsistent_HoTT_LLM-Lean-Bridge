# Lean-Formalized ShadowHoTT Governance Core

ShadowProof Bridge v25.7 extends the HoTT-inspired layer by mirroring the finite ShadowHoTT governance semantics inside the Lean template project.

This is a production-safety move, not a foundations rewrite.  The bridge remains a governance-first LLM-to-Lean acceptance gateway.  Lean remains the object-level proof authority.  The new Lean files provide a kernel-checkable reference model for the small algebra and routing invariants used by the runtime.

## Files

```text
lean_project_template/ShadowProof/BilatticeCore.lean
lean_project_template/ShadowProof/Routing.lean
lean_project_template/ShadowProof/PatchMorphism.lean
lean_project_template/ShadowProof/NoGluttyJ.lean
```

The root module imports all of them:

```text
lean_project_template/ShadowProof.lean
```

## Bilattice core

The formalized carrier is the same finite governance bilattice used by the Python runtime:

```text
L = Bool × Bool
```

with named values:

```text
top     = (true, false)
bottom  = (false, true)
both    = (true, true)
neither = (false, false)
```

The Lean file `BilatticeCore.lean` defines:

- `Shadow`
- `truth`
- `refutation`
- `ofCoordinates`
- `designated`
- `meet`
- `join`
- `demorgan`

and proves the expected finite laws:

- meet associativity, commutativity, idempotence;
- join associativity, commutativity, idempotence;
- absorption laws;
- meet identity/zero laws;
- join identity/zero laws;
- De Morgan order two;
- De Morgan fixed points;
- De Morgan meet/join duality;
- non-preservation of designation by De Morgan swap;
- truth fragility/refutation accumulation under meet.

## Routing model

`Routing.lean` defines a pure reference routing function over:

- `LeanStatus`
- `ToolStatus`
- final `Shadow` label

and proves:

```text
accepted + ok + both -> human_review
accepted + ok + both != accept
accept requires accepted + ok + top
```

This is the Lean-side mirror of the runtime No-Glutty-J routing behavior.

## Patch morphisms

`PatchMorphism.lean` formalizes theorem-fingerprint preservation abstractly:

```text
PreservesFingerprint(p) := p.sourceFingerprint = p.targetFingerprint
```

It proves:

- identity patch preserves fingerprints;
- composition of preserving patches preserves fingerprints;
- changed fingerprints are not preserving.

This mirrors the runtime theorem-lock policy: repairs may transform proof bodies, but theorem targets must not drift.

## No-Glutty-J theorem

`NoGluttyJ.lean` names the central governance theorem:

```text
A contradiction-bearing accepted state is designated but review-bound.
It routes to human_review, not accept.
```

This is the core ShadowProof safety invariant.

## Explicit boundary

The v25.7 Lean governance layer does not claim to implement full HoTT, cubical type theory, univalence, higher inductive types, or two-level type theory inside Lean.

Those may be future research modules, but they should remain optional and explicitly separated from the production safety boundary.

The default production boundary is finite, axiom-free, and auditable.
