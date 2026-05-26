# ShadowProof Bridge v25.8 Acquisition-Clean Package

ShadowProof Bridge is a self-hostable Lean-acceptance gateway with
ShadowHoTT bilattice-routed disposition.  It accepts proof attempts
(either direct Lean 4 code or a structured `DraftProposal` produced by
an LLM), runs them through a security preflight + Lean kernel check +
theorem-fingerprint lock, and routes the outcome through a 2×2 bilattice
state machine that distinguishes `accept`, `repair`, `reject`,
`human_review`, and `unchecked`.

## What the math actually is

- Semantic values: `L = Bool × Bool`, with coordinates `(truth, refutation)`.
- Designation: the binary predicate `truth == True`.  Not a probability,
  not a score.
- De Morgan involution: the coordinate swap `(t, r) ↦ (r, t)`.  It has
  order two, fixes `both` and `neither`, swaps `top` and `bottom`, and
  is explicitly NOT designation-preserving.
- Path composition: bilattice meet `∧_L`, defined as
  `(t₁ ∧ t₂, r₁ ∨ r₂)` — truth is fragile (AND), refutation accumulates
  (OR).
- Reflexivity paths carry `⊤_L`.
- Patch morphisms preserve theorem fingerprints and are checked by the
  No-Glutty-J runtime monitor.
- Glutty `⊥⊤_L` states (Lean-accepted plus a refutation signal) are
  designated but routed to `human_review` — never auto-accepted.

Lean-side reference formalizations of these claims are in:

- `lean_project_template/ShadowProof/DemorganSymmetry.lean`
- `lean_project_template/ShadowProof/BilatticeCore.lean`
- `lean_project_template/ShadowProof/Routing.lean`
- `lean_project_template/ShadowProof/PatchMorphism.lean`
- `lean_project_template/ShadowProof/NoGluttyJ.lean`

The runtime `shadowproof demorgan-symmetry` and `bilattice_axiom_report()` are the
in-process counterparts of the same finite governance semantics.

## What ships in the package

- Dependency-light ASGI app: `shadowproof_core.asgi:app`.
- Stdlib HTTP server with per-connection timeout: `shadowproof serve`.
- Optional Postgres storage backend and Redis quota backend.
- OIDC / JWT auth scaffold and a bearer-token mode for local pilots.
- Active readiness checks, Prometheus metrics, structured JSON access
  logs, OpenTelemetry span hooks.
- Docker Compose pilot stack (`deploy/`) with API, Lean-worker stub,
  Postgres, Redis, Prometheus.
- OpenAPI 3.1 schema generation plus a deliberately minimal TypeScript MCP bridge. Full Python/TypeScript SDKs are not bundled.
- 84 tools registered in the in-process tool registry; 35 of them are
  declared in `schemas/openai_mcp_tool_descriptors.json` for OpenAI
  native tool surfaces (the omitted 49 are admin, domain-pack, and
  promotion tools that are not part of the buyer-facing API).
- Runtime De Morgan symmetry report (`shadowproof demorgan-symmetry`).
- Lean-formalized ShadowHoTT governance core covering bilattice laws, routing invariants, fingerprint-preserving patch morphisms, and No-Glutty-J safety.
- Offline training-parameter capacity planner
  (`shadowproof training-capacity-plan`).
- Diligence reading index: `docs/acquisition/DILIGENCE_INDEX.md`; the v0.25.8 patch status is in `docs/acquisition/DILIGENCE_STATUS.md`.

## Lean-formalized ShadowHoTT governance core

v25.7 extends the HoTT-inspired layer without changing the production safety boundary.  The new Lean template files formalize the finite governance semantics already used by the runtime:

- `BilatticeCore.lean` defines the four-valued `Shadow` carrier, truth/refutation coordinates, designation, meet, join, and De Morgan duality.
- `Routing.lean` defines the reference disposition routing table and proves that `accepted + ok + both` routes to `human_review`, not `accept`.
- `PatchMorphism.lean` formalizes theorem-fingerprint preservation for repair morphisms.
- `NoGluttyJ.lean` names the central safety theorem: contradiction-bearing accepted states are designated but review-bound.

This is not a full HoTT implementation, not a cubical extension, and not an added axiom package.  It is a finite Lean-side semantic mirror for ShadowProof's bilattice governance layer.

See `docs/SHADOWHOTT_LEAN_GOVERNANCE.md` and `PATCH_NOTES_V25_7.md`.

## What does NOT ship

To set buyer expectations correctly:

- **The translator is a deterministic scaffold.** The shipped
  `LLMBridgeTranslator` recognises three hardcoded English theorem
  families (group associativity, group left-cancellation, group
  commutativity — the last is a deliberate drift trap).  Anything else
  routes to `unsupported`.  The frontier-model path is exposed via
  `shadowproof_model_provider_call`, which posts a generic JSON
  envelope only to server-configured provider URLs; caller-supplied
  provider URLs, headers, and bearer tokens are rejected. Adapters for
  specific frontier providers are NOT bundled.
- **No kernel sandbox is implemented in Python.** The package documents
  that production deployments must run the Lean worker inside Docker /
  gVisor / Firecracker / Kubernetes with appropriate CPU, memory,
  network, and filesystem controls.  See `SECURITY.md` for the threat
  model and recommended deployment hardening.
- **No external security review.** The audits that produced the v0.25.2/v0.25.3/v0.25.4/v0.25.6/v0.25.7
  fixes (see `CHANGELOG.md`) were internal exercises.  Third-party
  review is on the "outstanding for GA" list.
- **No real customer eval corpora.** The shipped `examples/evals/` are
  smoke-test sized.

## Local validation

```bash
pip install -e .
python -m pytest tests/ -q                                              # 124 passed, 1 skipped
python -m shadowproof_core.cli demorgan-symmetry examples/tool_requests/demorgan_symmetry.json
python -m shadowproof_core.cli training-capacity-plan examples/optimization/training_capacity_plan.json
python -m shadowproof_core.cli shadowhott-eval examples/evals/shadowhott_eval.json
python -m shadowproof_core.cli regression examples/evals/regression_suite.json
```

## Local API demo

```bash
export SHADOWPROOF_AUTH_MODE=bearer
export SHADOWPROOF_BEARER_TOKENS=dev-token:default
python -m shadowproof_core.cli serve --host 127.0.0.1 --port 8765
```

In another shell:

```bash
curl -sS -X POST http://127.0.0.1:8765/shadowproof_shadowhott_state \
    -H 'Authorization: Bearer dev-token' \
    -H 'Content-Type: application/json' \
    -d '{"request_id":"smoke","proof_graph":[],"lean_status":"not_run","status":"unchecked"}'
```

## ASGI pilot server

```bash
pip install -e '.[prod]'
uvicorn shadowproof_core.asgi:app --host 0.0.0.0 --port 8765
```

## Full pilot stack

```bash
cd deploy
docker compose up --build
```

Note: the bundled Lean-worker container is a stub.  Replace
`deploy/lean-worker.Dockerfile` with a real Lean 4 / Mathlib image
before running the validation path; the bridge will report
`lean_status: not_available` against the stub.

## Acquisition demo

```bash
bash scripts/run_buyer_demo.sh
```

This walks through the bilattice axiom report, the offline capacity
plan, the ShadowHoTT eval, the regression suite, and the four
commercial-section endpoints.  It exits 0 and prints JSON for every
section.

Primary buyer documents live in `docs/acquisition/`.  Start with
`docs/acquisition/DILIGENCE_INDEX.md`; the v0.25.8 patch status is in `docs/acquisition/DILIGENCE_STATUS.md`.

## Security

See `SECURITY.md` for the threat model, the hardening applied in
v0.25.2, v0.25.3, v0.25.4, v0.25.6, and v0.25.7 (relative to v0.25.0), and the recommended deployment posture.
A short summary:

- Server configuration comes from environment variables only; request
  bodies cannot override it (CRIT-1, CRIT-2 fixed in v0.25.2).
- Tenant identity is bound to the authenticating credential in both
  single- and multi-tenant modes; payload-supplied `tenant_id` must
  match (CRIT-3a fixed).
- Tenant directory paths refuse `..`, `.`, and dots-only ids;
  `relative_to()` is enforced as defence in depth (CRIT-3b fixed).
- Rejection memory is tenant-scoped by default (LEARN-1 fixed).
- The stdlib HTTP server has a per-connection timeout to close the
  slowloris vector (SERVER-1 fixed).
- Quota mode comparisons are normalized before rate-limit checks, so `Memory`/`Redis` cannot bypass quota enforcement.
- All 84 HTTP/ASGI tool routes now resolve to an input schema; high-risk routes now use strict exact schemas where possible.
- Additional file-reading/writing paths are root-guarded; domain-pack list/get/retrieval share the same allowed-root policy; file-writing HTTP routes are admin-scoped.
- Retail hardening patch: Lean comment/literal masking is now delimiter-aware and nested-comment-safe across security preflight, theorem-lock, and ShadowHoTT fingerprint obstruction checks; proof-body repair replacement now uses a delimiter-aware anchor splitter rather than raw regex substitution.

## Outstanding for GA

This package is a pre-commercial acquisition packet.  Enterprise GA
still requires:

- External security review by a third-party firm.
- Legal / SLA work.
- Signed certificate / registry publishing pipeline.
- Large customer evaluation corpora (the shipped evals are smoke-test
  sized).
- A real Lean CI transcript at production scale.
- Customer-specific frontier-model adapters and retrieval integrations.
- A trained policy file populated from real customer evals.
