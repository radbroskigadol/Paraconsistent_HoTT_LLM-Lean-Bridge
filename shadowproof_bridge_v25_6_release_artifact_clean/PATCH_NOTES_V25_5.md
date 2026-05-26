# Patch Notes v0.25.5 — Acquisition-Clean Hardening

This patch closes the buyer-diligence blockers identified in the v0.25.4 local
simulation packet without requiring a live Lean or LLM environment.

## Security and governance fixes

- All public domain-pack operations now use the same allowed-root path guard.
- Domain-pack authoring and retrieval now agree on theorem fields.
- Frontier HTTP provider calls no longer accept caller-supplied URLs, headers, or
  bearer tokens. Egress must be configured by the operator.
- Configured provider URLs are rejected if they target localhost, private IP,
  loopback, link-local, reserved, multicast, or unspecified addresses.
- High-risk tool schemas are exact and strict.

## Packaging and diligence fixes

- API Docker image now copies runtime schemas, docs, examples, scripts, and Lean
  templates.
- MCP version metadata is aligned with the Python package.
- Added proprietary LICENSE, NOTICE, SBOM, CI workflow, and diligence-status docs.
- Added production Lean-worker hardening guidance.

## Tests

Added `tests/test_v25_5_acquisition_clean.py`. The local suite is now 102 tests.
