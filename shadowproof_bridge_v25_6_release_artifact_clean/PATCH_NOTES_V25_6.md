# Patch Notes v0.25.6 — Release-Artifact and Math-Drift Clean

v0.25.6 closes the world-class-buyer diligence gaps found after v0.25.5 while preserving the ShadowHoTT/paraconsistent bilattice semantics.

## Fixed

- Packaged runtime JSON schemas inside `shadowproof_core/schemas/` so wheel installs preserve schema validation outside the source tree.
- Added `MANIFEST.in` and package-data entries so source distributions include runtime schemas and diligence artifacts.
- Hardened model-provider egress with DNS resolution checks, public-IP enforcement after DNS resolution, and bounded provider response reads.
- Added a bounded local Lean stdout/stderr reader with per-stream caps to prevent unbounded retained output in the developer runner.
- Made the CLI validate request payloads against the same JSON schemas used by HTTP/ASGI by default; `--no-schema-validation` is now explicit debug-only behavior.
- Made allowed filesystem roots fail closed in production/staging unless `SHADOWPROOF_ALLOWED_FILE_ROOTS` is explicitly set.
- Repaired MCP version drift and routed MCP requests through the now-schema-validating CLI boundary.

## Mathematical non-drift hardening

- Kept the core semantics as `L = Bool × Bool`, coordinates `(truth, refutation)`, designation iff `truth_coordinate = true`.
- Kept path composition as the truth-order meet `(t, f) ∧ (t′, f′) = (t ∧ t′, f ∨ f′)`.
- Added the dual truth-order join `(t, f) ∨ (t′, f′) = (t ∨ t′, f ∧ f′)`.
- Added executable axiom checks for associativity, commutativity, idempotence, absorption, meet/join identities and zeros, De Morgan duality, order-two involution, and reflexivity-path `⊤_L`.
- Hardened bilattice coordinate parsing so string values such as `"false"` cannot be truthiness-coerced into `True`.

## Still intentionally not claimed

- No live frontier-model adapter is bundled.
- No live Lean/Mathlib transcript is bundled in this sandbox build.
- The local Lean runner remains a developer fallback; production deployments should use the isolated Lean worker design in `docs/PRODUCTION_LEAN_WORKER.md`.
