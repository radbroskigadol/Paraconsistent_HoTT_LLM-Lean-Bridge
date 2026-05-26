# Changelog

## v0.25.8 — Audit-idea implementation pass

- Added richer eval metrics for human-review escalation accuracy, token load, p95 latency, acceptance rate, repair request rate, and theorem-drift escape rate.
- Added dependency-light proof-lifecycle trace helpers and lifecycle-derived metric events for draft/security/theorem-lock/Lean/bilattice/routing/escalation stages.
- Extended metrics and Prometheus output with human-review and bilattice-both counters.
- Added lexical dependency metadata, declaration structure hashes, and LSH-style buckets to `shadowproof_index_mathlib`; optional sidecar dependency graph output is available via `build_dependency_graph`.
- Added v0.25.8 regression tests and documentation in `docs/EVAL_OBSERVABILITY_RETRIEVAL_V25_8.md`.
- Preserved the existing finite ShadowHoTT safety boundary; no full HoTT/cubical/univalence/GNN claims are added to the production core.

## v0.25.7 — Lean-formalized ShadowHoTT governance core

- Added Lean reference files for the finite ShadowHoTT governance layer: `BilatticeCore.lean`, `Routing.lean`, `PatchMorphism.lean`, and `NoGluttyJ.lean`.
- Formalized the four-valued bilattice carrier, truth/refutation coordinates, designation, meet/path-composition, join, De Morgan duality, absorption laws, and identity/zero laws in Lean.
- Added a Lean-side reference routing table proving that `accepted + ok + both` routes to `human_review`, not `accept`.
- Added theorem-fingerprint-preserving patch-morphism lemmas for identity and composition of safe repairs.
- Added the named No-Glutty-J safety theorem: contradiction-bearing accepted states are designated but review-bound.
- Updated `shadowproof demorgan-symmetry` output to advertise the expanded Lean governance formalization surface.
- Added v25.7 regression guards for Lean-file presence, theorem names, root imports, runtime No-Glutty-J behavior, and the expanded formalization report.
- This release deliberately does not add full HoTT, cubical type theory, univalence, HITs, or new production axioms.

## v25.6-retail-hardening addendum

- Hardened Lean lexical handling for security/theorem-lock/ShadowHoTT fingerprint scans using a delimiter-aware nested-comment scanner.
- Replaced fragile proof-body regex substitution with delimiter-aware anchor splitting in the repair engine.
- Added regression tests; local suite now reports `124 passed, 1 skipped`.


## v0.25.6

- Bundled runtime schemas inside the Python package so wheel installs preserve schema validation.
- Added package-data/MANIFEST coverage for release artifacts.
- Hardened model-provider DNS/IP egress and response-size handling.
- Added CLI schema validation before dispatch.
- Added local Lean stdout/stderr output truncation.
- Made production/staging path roots fail closed unless explicitly configured.
- Re-audited the paraconsistent bilattice core with meet, join, absorption, De Morgan duality, and strict coordinate parsing tests.
- Expanded Lean template with meet/join/De Morgan laws and added `scripts/capture_lean_transcript.sh`.
- Expanded CI release gates for wheel smoke, MCP build, Docker build, and lightweight secret scan.

## 0.25.6 — acquisition-clean hardening

This patch closes the v0.25.4 buyer-diligence blockers that could be fixed without a live Lean or LLM environment.

### Security and correctness fixes

- Docker/API packaging now includes runtime schemas, docs, examples, scripts, and Lean templates.
- Domain-pack listing, lookup, and retrieval now share the same allowed-root path guard.
- Domain-pack authoring and retrieval now agree on theorem fields: canonical `theorems[*].statement` is accepted, with backward-compatible support for `common_theorems[*].statement_pattern`.
- Frontier HTTP model-provider egress is server-configured only. Caller-supplied URLs, arbitrary headers, and caller-supplied bearer tokens are rejected.
- Configured model-provider URLs reject localhost/private/loopback/link-local/reserved/multicast/unspecified IP targets.
- High-risk schemas are now strict for provider calls, domain operations, Mathlib retrieval/indexing, and release reports.

### Packaging and diligence fixes

- MCP package metadata is aligned with the Python package.
- Added proprietary `LICENSE`, `NOTICE`, `sbom.spdx.json`, GitHub Actions CI, production Lean-worker guidance, and `docs/acquisition/DILIGENCE_STATUS.md`.
- Added `tests/test_v25_5_acquisition_clean.py`; the suite is now 102 tests.

### Verification

```bash
python -m compileall -q shadowproof_core tests
PYTHONPATH=. python -m pytest tests/ -q     # 102 passed
bash scripts/run_buyer_demo.sh
python -m shadowproof_core.cli local-sim examples/local_simulation/request.json
```

## 0.25.4 — local integration-behavior simulation

- Added a deterministic `local_deterministic` model-provider adapter for local provider-contract tests.
- Added `scripts/mock_lean.py`, a Lean-like subprocess stand-in that exercises LeanRunner acceptance/rejection/diagnostic parsing without requiring Lean.
- Added `shadowproof_local_behavior_simulation` as an in-process, CLI, HTTP/ASGI-accessible tool for modeling provider, Lean, DraftProposal, certificate, ShadowHoTT, repair-context, and theorem-lock behavior locally.
- Added `tests/test_v25_4_local_simulation.py`; the suite is now 94 tests.
- This release does not claim local simulation is a Lean kernel check or frontier-model quality measure; it is a deterministic contract/integration model.

## 0.25.3 — boundary/schema hardening patch

This patch applies the additional local fixes identified after the v0.25.2 hardened package. It does not require a live Lean, Mathlib, Redis, OIDC, or LLM-connected environment.

### Security and correctness fixes

- Normalized `quota_mode` before rate-limit enforcement, closing the `Memory`/`Redis` case-sensitivity fail-open.
- Renamed the three misnamed runtime input schemas so `shadowproof_shadowhott_state`, `shadowproof_pilot_plan`, and `shadowproof_compile_repair_prompt` are validated at the HTTP/ASGI boundary.
- Added OpenAI/MCP descriptor, shared family-schema, and generic schema fallbacks so all 83 concrete HTTP/ASGI routes resolve to an input schema.
- Added root-guarding for memory, optimization, eval/regression, retrieval, release-report, license-scan, domain-authoring, and onboarding file paths.
- Added admin HTTP scoping for additional server-side file-writing routes: `shadowproof_create_domain_pack`, `shadowproof_domain_pack_eval_stub`, `shadowproof_onboarding_packet`, and `shadowproof_release_report`.

### Packaging and diligence fixes

- Corrected README/product-readiness wording that claimed bundled SDK/MkDocs/hosted-CI assets not present in the package.
- Replaced the empty `docs/EVAL_HARNESS.md` placeholder with a usable evaluation-harness note.
- Added `tests/test_v25_3_boundary_hardening.py`; the suite is now 89 tests.

### Verification

```bash
python -m pytest -q                 # 89 passed
python -m compileall -q shadowproof_core
```

## 0.25.2 — audit hardening patch

This patch applies the follow-up audit fixes that do not require a live Lean, Mathlib, or LLM-connected environment.

### Security and correctness fixes

- Removed request-controlled `target.lean_command` from schemas and parser behavior; Lean command selection is now deployment-owned through `SHADOWPROOF_LEAN_CMD`.
- Changed DraftProposal theorem-lock mismatches from warnings to errors, so a Lean-accepted but theorem-mutated draft is rejected before any certificate can be issued unless theorem mutation is explicitly allowed.
- Added HTTP/ASGI admin-route scoping. File-writing/admin tools are disabled by default and require `SHADOWPROOF_ENABLE_ADMIN_HTTP=true` plus a separate admin bearer token.
- Added JSON Schema validation before HTTP/ASGI tool dispatch and strict boolean/integer parsing for core target/policy fields.
- Added caller-path root guards via `SHADOWPROOF_ALLOWED_FILE_ROOTS` for registry, promotion, retrieval-index, artifact, review-packet, and environment-inspection paths.
- Made `auth_mode=disabled` fail closed outside development/local/test environments.
- Hardened ASGI request body reading so oversized streaming bodies are rejected before full buffering.
- Hardened stdlib HTTP `Content-Length` handling.
- Cached Redis rate limiters by URL rather than constructing a new limiter/client wrapper per request.

### Packaging and diligence fixes

- Added `jsonschema` as a runtime dependency.
- Added `tests/test_v25_2_security_hardening.py`; the suite is now 82 tests.
- Added pinned Lean project-template inputs: `lean-toolchain`, pinned `lakefile.lean`, and `lake-manifest.json`. These are reproducibility inputs; live Lean/lake verification still belongs in Lean-equipped CI.
- Added MCP `package-lock.json`, synchronized MCP versioning, added subprocess timeout/buffer limits, and confirmed `npm run build` passes after `npm ci`.
- Added missing acquisition/architecture markdown documents and corrected acquisition reporting so absent PPTX/PDF files are optional collateral rather than falsely required code-package assets.
- Hardened Docker/compose examples with non-root users, no-new-privileges, cap-drop/read-only/tmpfs where compatible, and health checks.
- Aligned HTTP/ASGI routes with the Python registry and added `docs/TOOL_SURFACE.md` to document the deliberately smaller MCP/OpenAI descriptor surfaces.

### Verification

```bash
python -m pytest -q                 # 82 passed
python -m compileall -q shadowproof_core
cd mcp && npm ci --ignore-scripts && npm run build
```

## 0.25.1 — diligence-polished

This release applies the security fixes identified during the pre-acquisition
code audit of v0.25.0.  All four critical defects, plus several smaller
correctness bugs, are remediated and pinned by regression tests under
`tests/`.

### Security fixes

| ID       | Severity | Summary                                                  |
| -------- | -------- | -------------------------------------------------------- |
| CRIT-1   | Critical | `payload["config"]` could override server-side config, leading to RCE via `lean_command` |
| CRIT-2   | Critical | Same vector via `shadowproof_retention_sweep` enabled arbitrary `.jsonl` deletion |
| CRIT-3a  | Critical | `multi_tenant` auth let any token claim any tenant via `payload["tenant_id"]` |
| CRIT-3b  | High     | `tenant_dir` accepted path-traversal tenant ids (`..`, `....`) |

Remediations:

- `config.load_config()` no longer reads `payload["config"]` by default.
  An explicit `SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE=1` env knob
  restores a *restricted* allowlist for dev use; the allowlist excludes
  every field that could lead to RCE, arbitrary file deletion, or auth
  bypass.
- `auth.build_request_context()` now binds the tenant to the
  authenticating credential in both `single_tenant` and `multi_tenant`
  modes.  A payload-supplied `tenant_id` that disagrees with the
  token-bound tenant fails authentication.
- `storage._safe_tenant_segment()` rejects `""`, `"."`, `".."`, and any
  dots-only value; `storage.tenant_dir()` performs a defence-in-depth
  `relative_to()` check after `Path.resolve()`.
- `server.py` and `asgi.py` now *overwrite* `payload["tenant_id"]` with
  the auth context's value rather than calling `setdefault`, so the
  storage layer and the auth layer can never disagree about who the
  caller is.

### Non-security correctness fixes

- **ROUTE-1** Removed duplicate route entries for
  `shadowproof_shadowhott_state` and `shadowproof_shadowhott_audit` in
  `server.routes`.
- **DIAG-1** `sandbox.parse_basic_lean_diagnostics` no longer
  misclassifies benign `"goals"`-containing lines (e.g. `"no goals"`,
  `"goals accomplished"`, `"subgoals"`) as `unsolved_goal`.
- **REPAIR-1** `repair.replace_body` returns `None` when no proof-body
  anchor is found instead of silently returning the original code as if
  a patch had been applied.  The repair engine now produces a
  `NO_PATCH` outcome with a diagnostic in that case.
- **MODEL-1** `model_providers._extract_text` understands the response
  shapes of Anthropic Messages, OpenAI Responses, OpenAI Chat
  Completions, and Google Gemini in addition to the legacy flat
  `text`/`output_text`/`content` keys.  Retry backoff is now exponential
  up to 8 seconds instead of capped near 1 second.
- **LEARN-1** Rejection memory is tenant-scoped by default
  (`.shadowproof_memory/<tenant>/rejections.jsonl`).  Each
  `RejectionRecord` carries an explicit `tenant_id` field, and the
  loader filters per-tenant.  Legacy records without `tenant_id` are
  surfaced to the caller for backward compatibility.  Unknown fields in
  records are tolerated for forward compatibility, and parse failures
  are accumulated on `memory._load_warnings` rather than silently
  swallowed.
- **SERVER-1** `ShadowProofHandler.timeout = 30` closes the
  slowloris-class DoS vector in the stdlib HTTP server path.
- `RedisRateLimiter` caches its client instead of re-creating one per
  request.

### Packaging fixes

The previous release's README referenced files that did not ship.  This
release adds:

- `examples/evals/` — `regression_suite.json`, `shadowhott_eval.json`.
- `examples/tool_requests/` — `demorgan_symmetry.json`.
- `examples/optimization/` — `training_capacity_plan.json`.
- `examples/commercial/` — `acquisition_packet.json`, `investor_deck.json`.
- `scripts/run_buyer_demo.sh` — single-script buyer walkthrough.
- `deploy/` — `docker-compose.yml`, `api.Dockerfile`,
  `lean-worker.Dockerfile` stub, `prometheus.yml`.
- `lean_project_template/` — Lean 4 / Mathlib project containing the
  kernel-checked `ShadowProof.DemorganSymmetry` formalisation that the
  runtime `demorgan-symmetry` report references.
- `docs/acquisition/DILIGENCE_INDEX.md` — diligence reading index.
- `tests/` — pytest suite with 77 tests covering the bilattice algebra,
  verdict assignment, all four security fixes, the diagnostic
  classifier, the repair-engine no-patch path, learning-memory tenant
  scoping, the model-provider response parser, and the security
  preflight.
- `CHANGELOG.md` and `SECURITY.md` (this file and `SECURITY.md`).

### Verification

```bash
pip install -e .
python -m pytest tests/ -q     # 77 passed
bash scripts/run_buyer_demo.sh # exits 0
```
