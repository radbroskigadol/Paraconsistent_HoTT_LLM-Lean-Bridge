# Diligence reading index

Start here, then drill down.  This package is a pre-commercial pilot
acquisition packet; the README's "Outstanding for GA" section is the
authoritative list of work that still needs to happen before any
production rollout.

## Start

1. [`../../README.md`](../../README.md) — what this package contains and
   what it does not contain.
2. [`../THREAT_MODEL.md`](../THREAT_MODEL.md) — threat-model summary.
3. [`../../SECURITY.md`](../../SECURITY.md) — security posture, recent
   hardening, and disclosure contact.
4. [`../../CHANGELOG.md`](../../CHANGELOG.md) — what changed in this
   release, including the security fixes applied to v0.25.x before the
   diligence cut.

## Architecture

5. [`../PROTOCOL.md`](../PROTOCOL.md) — JSON wire protocol.
6. [`../LEAN_ENV.md`](../LEAN_ENV.md) — Lean toolchain expectations and
   the optional HTTP worker.
7. [`../DRAFT_PROPOSAL.md`](../DRAFT_PROPOSAL.md) — the
   `DraftProposal` shape that the LLM is expected to produce, including
   theorem fingerprint, declared trust, and proof graph.
8. [`../OPENAI_NATIVE_TOOL.md`](../OPENAI_NATIVE_TOOL.md) — descriptor
   subset exposed to frontier model tool surfaces.
9. [`../VERSIONED_CERTIFICATES.md`](../VERSIONED_CERTIFICATES.md) — the
   certificate payload that an accepted theorem carries.
10. [`../LOCAL_SIMULATION.md`](../LOCAL_SIMULATION.md) — deterministic local provider/Lean behavior simulation for integration-contract demos.

## Algebraic core

11. [`../../shadowproof_core/bilattice.py`](../../shadowproof_core/bilattice.py)
    — the bilattice `L = Bool × Bool` itself.
12. [`../../shadowproof_core/shadowhott.py`](../../shadowproof_core/shadowhott.py)
    `bilattice_axiom_report()` and `audit_shadowhott_state()` — the
    self-checks that every server response carries.
13. [`../../lean_project_template/ShadowProof/DemorganSymmetry.lean`](../../lean_project_template/ShadowProof/DemorganSymmetry.lean)
    — the kernel-checked counterpart to those self-checks.

## Operations

14. [`../DEPLOYMENT.md`](../DEPLOYMENT.md) — deployment notes.
15. [`../../deploy/docker-compose.yml`](../../deploy/docker-compose.yml)
    — pilot stack.
16. [`../EVAL_PLAN.md`](../EVAL_PLAN.md), [`../REPAIR_PROMPTS.md`](../REPAIR_PROMPTS.md),
    [`../LEARNING_LAYER.md`](../LEARNING_LAYER.md),
    [`../ACTIVE_LEARNING_LOOP.md`](../ACTIVE_LEARNING_LOOP.md),
    [`../FRONTIER_MODEL_BRIDGE.md`](../FRONTIER_MODEL_BRIDGE.md) —
    pilot-mode operational notes.

## What is *not* here yet (and why that is in the price)

- A signed certificate-publishing pipeline.
- A real Lean CI transcript at production scale.
- Customer-specific model and retrieval adapters.
- Full external security review by a third-party firm.
- Production-grade kernel sandboxing (the package documents that this is
  delegated to Docker / gVisor / Firecracker / Kubernetes; it is not
  attempted inside Python).
- A trained policy file populated from real customer evals.
