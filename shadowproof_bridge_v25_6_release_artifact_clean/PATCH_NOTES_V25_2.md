# ShadowProof Bridge v25.2 Hardening Patch Notes

This patch applies the non-live-environment fixes identified in the v25.1 audit. It does not require a live Lean kernel, live LLM connector, production OIDC provider, Redis service, or container registry.

## Implemented fixes

- Removed external payload control of `target.lean_command`; Lean execution command is now deployment configuration only.
- Rejected `target.lean_command` in Python tool parsing, JSON schemas/OpenAI descriptors, and MCP request validation.
- Promoted theorem-lock/fingerprint drift from warning-only behavior to blocking errors for draft certification.
- Added runtime JSON Schema validation at HTTP/ASGI boundaries.
- Added strict boolean/integer parsing for policy/config values where string coercion could change semantics.
- Added safe structured error responses for parser/schema failures.
- Added fail-closed auth behavior for non-development environments when auth is disabled.
- Added admin HTTP gating; admin/file-writing routes are disabled by default and require explicit admin enablement plus token authorization.
- Added root-jail file path enforcement for domain-pack promotion, proof-artifact promotion, retrieval indexing, and environment-info path inputs.
- Hardened HTTP Content-Length handling and ASGI streaming body-size rejection.
- Fixed Redis limiter reuse so Redis limiter instances are cached by URL instead of recreated per request.
- Brought Python registry and HTTP route table into alignment.
- Updated MCP packaging to v0.25.2, added lockfile, build output, spawn timeout/maxBuffer, and payload command override rejection.
- Added pinned Lean template inputs (`lean-toolchain`, `lake-manifest.json`, pinned Mathlib revision in `lakefile.lean`) while explicitly leaving live Lean verification to Lean-equipped CI.
- Added missing diligence/acquisition markdown assets and corrected buyer-deck packaging to treat PPTX/PDF as optional generated collateral.
- Added deployment hardening defaults for API and Lean-worker Dockerfiles/compose files.
- Added `docs/TOOL_SURFACE.md` documenting public/admin/CLI/MCP/OpenAI tool surfaces.
- Added regression tests for command override rejection, theorem drift blocking, schema strictness, auth fail-closed behavior, and file-root escape rejection.

## Verification run locally

- `python -m pytest -q` -> 82 passed.
- `python -m compileall -q shadowproof_core` -> passed.
- `cd mcp && npm run build` -> passed.
- `python -m shadowproof_core.cli acquisition-packet /tmp/sp_empty.json` -> ready.
- `python -m shadowproof_core.cli release-gate /tmp/sp_empty.json` -> still blocked, as expected, because remaining production readiness items require live Lean/production infrastructure/external review.

## Known remaining items not fixed here

These require a live or production-connected environment and therefore remain intentionally incomplete:

- Actual Lean/lake kernel check of the template project and formal files.
- Production OIDC/JWKS validation against a real identity provider.
- Live Redis/Postgres/container orchestration verification.
- Docker image build, SBOM generation, signing, and registry attestation.
- External security review and hosted penetration test.
- Live LLM/frontier-model tool-call integration tests.
- Generated PPTX/PDF buyer collateral.

The package should still be described as pilot-ready/pre-commercial, not production-ready, until those environment-dependent checks are completed.
