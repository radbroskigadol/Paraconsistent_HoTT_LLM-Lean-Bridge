# Patch Notes v0.25.6 — release-artifact hardening

This patch closes the remaining offline buyer-diligence items identified after v0.25.5. It does not require a live Lean, Mathlib, Redis, OIDC, or frontier-model environment.

## Security and boundary hardening

- CLI commands now run the same JSON Schema validation used by the HTTP/ASGI boundary before dispatching to `call_tool`.
- The schema loader makes top-level payload strictness the default, including shared family schemas, while preserving nested object extensibility where individual schemas allow it.
- Frontier HTTP egress now checks both literal configured IPs and DNS-resolved addresses. DNS failure, NXDOMAIN, empty results, or any private/loopback/link-local/reserved/multicast/unspecified address fail closed.
- Model-provider HTTP responses are read through a configured byte cap before JSON parsing.
- Local Lean subprocess stdout/stderr and Lean-worker HTTP responses are bounded by configured byte caps.
- Compose no longer ships copy-pasteable default bearer/Postgres secrets. Local pilot users must provide values through `.env`, Docker secrets, or a secret manager.

## Packaging and diligence hardening

- Runtime schemas and diligence artifacts are copied into `shadowproof_core/artifacts/` and included as package data, so wheel installs can validate schemas outside the source tree.
- Added `MANIFEST.in` for source distributions and acquisition-review completeness.
- Added `scripts/wheel_smoke.py` to build/install the wheel in a clean target and verify schema loading plus CLI validation.
- Added `scripts/check_no_default_secrets.py` to fail CI on known dev-secret patterns outside allowlisted tests/docs.
- Expanded GitHub Actions to run Python compile/tests, buyer demo, local simulation, secret scan, MCP build, wheel smoke, Docker artifact inclusion check, and Docker build smoke where Docker is available.

## Mathematical non-drift hardening

- `BilatticeValue.from_label()` now rejects string truthiness and requires real JSON booleans for coordinate dictionaries.
- The executable bilattice layer now includes truth-order join in addition to meet.
- Runtime/self-test coverage now includes join associativity/commutativity/idempotence, absorption, and De Morgan meet/join duality in addition to order-two involution and meet composition.

## Claim boundary

This package provides executable semantic guardrails and local release verification. It still does not claim full machine-checked ShadowHoTT repair soundness, production Lean isolation, or live frontier-model quality without buyer-side integration and independent review.
