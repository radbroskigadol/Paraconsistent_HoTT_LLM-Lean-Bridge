# Security posture and disclosure

This document is part of the diligence packet for ShadowProof Bridge.  It
describes what the package does and does not protect against, the
hardening applied in v0.25.1, v0.25.2, v0.25.3, v0.25.4, and v0.25.5, and how to report
further issues.

## Threat model summary

The package is designed to be deployed as a backend service that accepts
authenticated requests from a model orchestrator (or directly from a
buyer's frontier model).  The trust boundary is the HTTP / ASGI layer:

- **Authenticated callers** may submit Lean code and DraftProposal
  payloads.  The system runs Lean against those payloads, records
  derived metrics, and may persist hash-only outcome records.
- **Anonymous callers** can only reach the `/health`, `/livez`,
  `/readyz`, and `/metrics` endpoints; no functional tool is exposed
  without authentication.
- **Operators** are assumed to control the deployment environment and
  the bearer-token allowlist or OIDC configuration.

The package explicitly does NOT attempt to provide kernel-level sandbox
isolation for the Lean subprocess.  Deployments that accept untrusted
Lean code must run the Lean worker inside Docker / gVisor / Firecracker
/ Kubernetes with appropriate CPU, memory, network, and filesystem
controls.  See `shadowproof_core/sandbox.py::sandbox_check()` and
`docs/THREAT_MODEL.md`.

## Hardening applied in v0.25.1

The audit of v0.25.0 surfaced four authenticated-caller defects, all
remediated in v0.25.1.  See `CHANGELOG.md` for full IDs and tests.

| ID      | Old behaviour                                                    | New behaviour                                                                                  |
| ------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| CRIT-1  | `payload.config` overrode any `ShadowProofConfig` field          | `payload.config` is ignored.  Opt-in env flag honours a strict safe allowlist only.            |
| CRIT-2  | `retention_sweep` would delete `.jsonl`s at a payload-supplied `data_dir` | Same root cause as CRIT-1; sweep now uses env-only config.                                     |
| CRIT-3a | `multi_tenant` mode let any token claim any tenant               | Tenant is bound to the credential in both modes; mismatched `tenant_id` in payload fails auth. |
| CRIT-3b | `tenant_dir` accepted `..` / `....` as path segments             | Path-unsafe tenant ids are rejected before any filesystem operation; verified by `relative_to`. |

Regression tests for these defects are in `tests/test_security_regressions.py`; v0.25.2 additions are in `tests/test_v25_2_security_hardening.py`; v0.25.3 boundary hardening tests are in `tests/test_v25_3_boundary_hardening.py`; v0.25.4 local-simulation tests are in `tests/test_v25_4_local_simulation.py`; v0.25.5 acquisition-clean regressions are in `tests/test_v25_5_acquisition_clean.py`.


## Additional hardening applied in v0.25.2

The follow-up audit identified several server/API risks that did not require a live Lean or LLM environment to remediate. v0.25.2 adds:

- Request payloads can no longer specify `target.lean_command`; all Lean command selection is deployment-owned via `SHADOWPROOF_LEAN_CMD`.
- Theorem-lock mismatches are errors by default, preventing certificate issuance for Lean-accepted but theorem-mutated DraftProposals.
- Admin/file-writing HTTP routes are disabled by default and require a separate admin bearer token when explicitly enabled.
- Tool schemas are validated at the HTTP/ASGI boundary for routes with concrete schema files; string booleans such as `"false"` no longer coerce to true on those routes.
- Caller-controlled file paths are constrained to `SHADOWPROOF_ALLOWED_FILE_ROOTS` by default.
- `auth_mode=disabled` fails closed outside development/local/test.
- ASGI request-size enforcement now stops while streaming instead of buffering the entire oversized request first.
- Redis quota limiter wrappers are cached by URL.

## Additional hardening applied in v0.25.3

The next audit pass fixed issues that were cheap locally but buyer-visible:

- Quota mode comparison is normalized before enforcement, so `SHADOWPROOF_QUOTA_MODE=Memory` or `Redis` cannot fail open.
- The primary buyer-facing schemas were renamed to the concrete runtime tool names: `shadowproof_shadowhott_state`, `shadowproof_pilot_plan`, and `shadowproof_compile_repair_prompt`.
- HTTP/ASGI schema resolution now falls back to OpenAI/MCP inline descriptors and shared family schemas, raising boundary coverage from partial to all 83 then-current routes; v0.25.4 keeps coverage at all 84 routes after adding the local-simulation route.
- Caller-controlled memory, optimization, eval, regression, retrieval, release-report, license-scan, domain-authoring, and onboarding paths now pass through `SHADOWPROOF_ALLOWED_FILE_ROOTS`.
- Additional file-writing HTTP routes (`create_domain_pack`, `domain_pack_eval_stub`, `onboarding_packet`, and `release_report`) are admin-token scoped.
- README/product-readiness wording now avoids claiming bundled SDK/MkDocs/CI assets that are not in the package.

## Local simulation added in v0.25.4

v0.25.4 adds a deterministic local integration-behavior model:

- `provider=local_deterministic` returns stable DraftProposal fixtures for provider-contract tests without API keys.
- `scripts/mock_lean.py` emits Lean-like acceptance/rejection diagnostics through the same subprocess path used by `LeanRunner`.
- `shadowproof_local_behavior_simulation` exercises provider, LeanRunner, DraftProposal, certificate, ShadowHoTT, repair-context, and theorem-lock paths locally.
- The simulator is explicitly not a Lean kernel proof check, not a frontier-model quality benchmark, and not a replacement for buyer environment integration testing.

## Additional hardening applied in v0.25.5

v0.25.5 closes the acquisition-diligence issues found in the v25.4 packet:

- Docker/API packaging now copies `schemas/`, `docs/`, `examples/`, `scripts/`, and `lean_project_template/`, so runtime schema loading and buyer evidence survive containerization.
- Domain-pack listing, direct lookup, and retrieval now share the same `SHADOWPROOF_ALLOWED_FILE_ROOTS` path guard.
- Domain-pack authoring and retrieval now agree on theorem fields: canonical `theorems[*].statement` is accepted, with backward-compatible support for `common_theorems[*].statement_pattern`.
- Model-provider HTTP egress is locked to server-configured provider URLs. Caller-supplied `provider_url`, arbitrary headers, and caller-supplied bearer tokens are rejected. Private, loopback, link-local, reserved, multicast, and unspecified IP targets are blocked.
- High-risk tool schemas are now concrete and strict for model-provider calls, domain listing/getting/authoring, Mathlib retrieval, Mathlib indexing, and release-report generation.
- MCP package/version metadata has been aligned with the Python package.
- License, notice, SBOM, CI, and diligence-status artifacts have been added for buyer inspection.

## What v0.25.4 still defers to the deployment

- **Process isolation.** Python cannot enforce cgroups, seccomp,
  namespaces, or per-process filesystem views by itself.  Operators
  must wrap the Lean worker in a container runtime that provides those
  controls.  The package documents this and the `sandbox_check` tool
  surfaces it as a warning.
- **TLS.** The packaged HTTP / ASGI servers speak plain HTTP.  Front
  with a TLS-terminating reverse proxy.
- **Secret storage.** Bearer tokens live in the
  `SHADOWPROOF_BEARER_TOKENS` env variable.  Operators are expected to
  inject these via the deployment platform's secret manager and rotate
  on schedule.
- **External security review.** This package has not yet been audited
  by an independent third-party firm; that work is on the "outstanding
  for GA" list.
- **Customer-specific model/retrieval adapters.** The shipped
  `model_providers.frontier_http` is a generic HTTP shim and the
  shipped translator covers three deterministic English patterns.
  Production deployments require buyer-specific adapters and a real
  retrieval index.

## Disclosure

Security issues should be reported privately before public disclosure.
Contact: repository owner David Betzer `<akivareb@yahoo.com>` until a dedicated security address is assigned.  Please include a minimal
reproduction, the affected version, and an estimated severity.  We aim
to acknowledge within 5 business days.

## Recommended deployment hardening

In addition to the in-process fixes:

1. Run with `SHADOWPROOF_AUTH_MODE=oidc` and a real JWKS endpoint, not
   `bearer` mode.
2. Set `SHADOWPROOF_QUOTA_MODE=redis` and configure
   `SHADOWPROOF_REDIS_URL`; the in-memory limiter is per-process.
3. Set `SHADOWPROOF_STORAGE_BACKEND=postgres` and configure
   `SHADOWPROOF_POSTGRES_DSN`; the JSONL backend is for local dev.
4. Do NOT set `SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE` in production.
5. Run the Lean worker as a separate process / container with
   `SHADOWPROOF_LEAN_WORKER_MODE=http` and `network: none` plus
   read-only filesystem on its container.
6. Set `SHADOWPROOF_PRIVACY_MODE=hash_only` unless legal review
   approves a higher mode.
7. Front the bridge with a TLS-terminating proxy that enforces request
   size limits matching `SHADOWPROOF_MAX_REQUEST_BYTES`.
