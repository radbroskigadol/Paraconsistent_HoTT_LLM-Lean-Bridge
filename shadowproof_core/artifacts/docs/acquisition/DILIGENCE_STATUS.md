# Diligence Status — v0.25.5 Acquisition-Clean Packet

## Status

v0.25.6 is a local, pre-commercial, acquisition-clean inspection package. It is
suitable for technical diligence, buyer demos, and pilot integration planning. It is
not yet a hosted enterprise production service.

## Issues closed from the v0.25.4 audit

- Runtime Docker packaging now includes schemas, docs, examples, scripts, and the
  Lean project template.
- Domain-pack listing, retrieval, and direct lookup share the same allowed-root path
  policy.
- Domain-pack authoring and retrieval now use a compatible theorem format.
- Model-provider HTTP egress is server-configured and allowlisted; caller-supplied
  URLs, headers, and bearer tokens are rejected.
- High-risk schemas are strict and concrete.
- MCP version metadata is aligned with the Python package.
- License, notice, SBOM, CI workflow, production Lean-worker hardening guidance, and
  v0.25.5 regression tests are included.

## Verified locally in this packet

- `python -m compileall -q shadowproof_core tests`
- `PYTHONPATH=. python -m pytest tests/ -q`
- `bash scripts/run_buyer_demo.sh`
- `python -m shadowproof_core.cli local-sim examples/local_simulation/request.json`

## Still intentionally deferred

- Live Lean/Mathlib kernel execution in a pinned production worker.
- Live frontier-model provider integration and provider-specific adapters.
- Independent penetration test / external security review.
- SOC 2, ISO, HIPAA, export-control, procurement, and legal compliance review.
- Buyer-specific Mathlib retrieval indexes, domain packs, performance baselines, and
  acceptance thresholds.

## Buyer-safe summary

ShadowProof Bridge v0.25.6 demonstrates a governed route from natural-language math
workflows toward Lean/Mathlib formalization using bilattice proof-state tracking,
schema-validated tool calls, theorem-lock checks, diagnostic repair routing, local
simulation, and certificate artifact scaffolding. It is ready for inspection and
pilot hardening, not for unsupported production claims.
