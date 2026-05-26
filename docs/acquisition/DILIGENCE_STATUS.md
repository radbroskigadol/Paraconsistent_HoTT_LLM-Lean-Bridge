# Diligence Status — v0.25.8 Audit-Enhanced ShadowHoTT Governance Packet

## Status

v0.25.8 is a local, pre-commercial, release-artifact-clean inspection package with an expanded Lean-side reference model for the finite ShadowHoTT governance layer. It is suitable for technical diligence, buyer demos, and pilot integration planning. It is not yet a hosted enterprise production service.

## Issues closed from the v0.25.5 buyer audit

- Runtime JSON schemas are bundled inside `shadowproof_core/schemas/`, so source-tree, Docker source-copy, and wheel-install layouts preserve schema validation.
- `MANIFEST.in` and package-data settings now include runtime schemas and release/diligence artifacts in source distributions.
- Model-provider HTTP egress is server-configured, rejects caller-supplied URLs/headers/tokens, validates DNS resolutions against private/internal IP ranges, and caps provider response reads.
- The CLI now validates JSON payloads against the same schema boundary used by HTTP/ASGI before dispatch; MCP calls route through this validating CLI boundary.
- Local Lean stdout/stderr retained by the developer runner is capped and truncated. Production deployments should still use the isolated Lean worker.
- Allowed filesystem roots fail closed in production/staging unless `SHADOWPROOF_ALLOWED_FILE_ROOTS` is explicitly set.
- MCP version metadata is aligned with the Python package and the TypeScript build passes.
- The SBOM now enumerates Python required/optional dependencies and npm transitive dependencies from the lockfile, using public npm registry URLs.

## v0.25.8 audit-idea implementation additions

v0.25.8 incorporates practical audit recommendations that can be shipped locally: richer eval metrics, proof-lifecycle trace helpers, human-review/bilattice-both observability counters, and lexical dependency/LSH metadata for retrieval indexing.  These additions improve pilot measurement and diligence visibility without claiming enterprise GA or a full HoTT/cubical/univalence implementation.

## v0.25.7 governance-core additions

v0.25.7 adds Lean-side reference files for the finite ShadowHoTT governance layer:

- `lean_project_template/ShadowProof/BilatticeCore.lean`
- `lean_project_template/ShadowProof/Routing.lean`
- `lean_project_template/ShadowProof/PatchMorphism.lean`
- `lean_project_template/ShadowProof/NoGluttyJ.lean`

These files formalize bilattice laws, disposition routing, theorem-fingerprint preservation, and the No-Glutty-J safety invariant.  The package still does not claim a full HoTT implementation or add cubical/univalence/HIT assumptions to the production boundary.

## Mathematical non-drift status

The paraconsistent/ShadowHoTT core remains the finite bilattice

```text
L = Bool × Bool
coordinates = (truth, refutation)
designated ⇔ truth_coordinate = true
```

The runtime path-composition operation remains the truth-order meet:

```text
(t, f) ∧L (t′, f′) = (t ∧ t′, f ∨ f′)
```

v0.25.6 added the dual join and regression tests for:

- exact four-element carrier,
- order-two De Morgan involution,
- fixed points `both` and `neither`,
- top/bottom swap,
- meet/join associativity, commutativity, idempotence,
- absorption laws,
- meet identity/zero and join identity/zero,
- De Morgan duality,
- binary designation,
- reflexivity paths forced to `⊤_L`,
- rejection of string-boolean coordinate coercion.

The Lean template now mirrors these meet/join/De Morgan laws in `lean_project_template/ShadowProof/DemorganSymmetry.lean` and extends the governance reference model through `BilatticeCore.lean`, `Routing.lean`, `PatchMorphism.lean`, and `NoGluttyJ.lean`. A Lean-equipped buyer can run `scripts/capture_lean_transcript.sh` to generate a preserved `lake build` transcript.

## Verified locally in this packet

- `python -m compileall -q shadowproof_core tests`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest tests/ -q -o faulthandler_timeout=30`
- `RUN_WHEEL_TEST=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest tests/test_v25_6_release_artifact_clean.py::test_wheel_install_preserves_runtime_schemas -q`
- `bash scripts/run_buyer_demo.sh`
- `python -m shadowproof_core.cli local-sim examples/local_simulation/request.json`
- `cd mcp && npm ci --registry=https://registry.npmjs.org && npm run build`
- `python scripts/ci_secret_scan.py`

## Still intentionally deferred

- Live Lean/Mathlib kernel execution in a pinned production worker in this sandbox.
- Live frontier-model provider integration and provider-specific adapters.
- Independent penetration test / external security review.
- SOC 2, ISO, HIPAA, export-control, procurement, and legal compliance review.
- Buyer-specific Mathlib retrieval indexes, domain packs, performance baselines, and acceptance thresholds.

## Buyer-safe summary

ShadowProof Bridge v0.25.7 demonstrates a governed route from natural-language math workflows toward Lean/Mathlib formalization using bilattice proof-state tracking, schema-validated tool calls, theorem-lock checks, diagnostic repair routing, local simulation, and certificate artifact scaffolding. It is ready for inspection and pilot hardening, not for unsupported production claims.


## Retail-hardening addendum

A post-audit hardening pass replaced the remaining regex-only Lean comment stripper and proof-body replacement paths with delimiter-aware scanners/splitters. The regression suite now includes checks for nested block comments, string-delimiter hiding of real `axiom`/`sorry` declarations, theorem-lock leakage, and fake `:= by` / `#print axioms` anchors inside string literals/comments. Local validation result: `119 passed, 1 skipped`; secret scan, compileall, buyer demo, and MCP TypeScript build pass.
