# ShadowProof Architecture

## Layers

1. Input/API layer: HTTP/ASGI/MCP/CLI surfaces with schema validation and auth.
2. Draft layer: DraftProposal parsing, declared trust, theorem fingerprinting, theorem-lock checks.
3. Security layer: preflight rejection for sorry/axiom/unsafe/drift patterns and deployment-owned Lean command selection.
4. Lean layer: local or worker-based Lean execution when a Lean environment is configured.
5. ShadowHoTT/bilattice layer: truth/refutation coordinates, BOTH/human-review routing, proof-path labels, and repair selection.
6. Diligence layer: release gate, product readiness, threat model, acquisition docs.

## Deployment boundary

The code package is a pilot implementation. Production operation requires a hardened Lean worker, external security review, buyer CI, and customer-specific auth/storage/observability configuration.
