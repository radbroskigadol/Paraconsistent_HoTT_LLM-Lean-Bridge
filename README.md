# ShadowProof Bridge v25.6

**ShadowProof Bridge** is a self-hostable paraconsistent HoTT LLM-to-Lean acceptance gateway.

It accepts Lean 4 proof attempts or structured proof proposals produced by an LLM, runs them through security preflight, theorem-fingerprint locking, and Lean validation, then routes the result through a 4-valued ShadowHoTT bilattice state machine.

The bridge is designed for proof-assistant workflows where ordinary pass/fail validation is too coarse. Failed proof attempts may still contain useful repair structure. Accepted Lean code may still conflict with external refutation signals. Repair loops need stable mathematical governance rather than untracked retry logic.

ShadowProof provides that governance layer.

---

## Core purpose

ShadowProof Bridge sits between:

1. **LLM-generated mathematical reasoning**
2. **Lean/Mathlib validation**
3. **Human or automated proof-repair workflows**

It is not a general chatbot and not a replacement for the Lean kernel.

Its role is to govern proof attempts before, during, and after Lean validation by tracking:

- proof acceptance,
- repairable failure,
- rejection,
- unchecked states,
- contradiction-bearing states requiring human review,
- theorem-target drift,
- security preflight failures,
- and proof fingerprint preservation.

---

## What the system does

At a high level, ShadowProof Bridge:

1. Accepts a direct Lean 4 proof attempt or structured `DraftProposal`.
2. Runs security preflight checks.
3. Locks the intended theorem fingerprint.
4. Checks or delegates Lean validation.
5. Computes a ShadowHoTT bilattice state.
6. Routes the attempt to one of the supported dispositions:

```text
accept
repair
reject
human_review
unchecked
```

This allows the system to preserve useful failed proof structure without pretending that all failed attempts are worthless, while also preventing contradiction-bearing states from being silently auto-accepted.

---

## Mathematical core

The runtime uses a finite four-valued bilattice:

\[
L = \mathrm{Bool} \times \mathrm{Bool}
\]

with coordinates:

\[
(t, r) = (\text{truth signal}, \text{refutation signal})
\]

The four canonical values are:

```text
top     = (true, false)
bottom  = (false, true)
both    = (true, true)
neither = (false, false)
```

Designation is the predicate:

\[
t = \mathrm{True}
\]

Designation is not a probability, not a confidence score, and not a neural heuristic.

Path composition is modeled by the bilattice meet:

\[
(t_1, r_1) \wedge_L (t_2, r_2)
=
(t_1 \wedge t_2,\; r_1 \vee r_2)
\]

Truth is fragile. Refutation accumulates.

The De Morgan involution is coordinate swap:

\[
(t, r) \mapsto (r, t)
\]

It has order two, fixes `both` and `neither`, swaps `top` and `bottom`, and is deliberately not designation-preserving.

Lean-accepted states with a simultaneous refutation signal are designated but not auto-accepted. They route to:

```text
human_review
```

This is the central ShadowHoTT safety rule: contradiction-bearing acceptance is visible, typed, and routed. It is not hidden inside an ordinary success state.

---

## ShadowHoTT routing intuition

Ordinary proof pipelines often collapse proof attempts into a binary outcome:

```text
pass / fail
```

ShadowProof instead separates truth and refutation signals.

This makes the following distinctions explicit:

| State | Meaning | Routing |
|---|---|---|
| Truth without refutation | accepted proof signal | `accept` |
| Refutation without truth | failed or rejected proof signal | `reject` or `repair` |
| Neither truth nor refutation | unchecked or unavailable validation | `unchecked` |
| Truth and refutation together | accepted but contradiction-bearing | `human_review` |

The purpose is not to weaken Lean. Lean remains the kernel authority.

The purpose is to prevent proof-repair systems from losing information when reasoning, tests, formal validation, and external contradiction signals conflict.

---

## What ships

ShadowProof Bridge v25.6 includes:

- dependency-light ASGI app: `shadowproof_core.asgi:app`
- stdlib HTTP server: `shadowproof serve`
- per-connection timeout on the stdlib HTTP server
- bearer-token local pilot mode
- OIDC/JWT authentication scaffold
- optional Postgres storage backend
- optional Redis quota backend
- active readiness checks
- Prometheus metrics
- structured JSON access logs
- OpenTelemetry span hooks
- OpenAPI 3.1 schema generation
- deliberately minimal TypeScript MCP bridge
- Docker Compose pilot stack under `deploy/`
- API service container
- Lean-worker stub container
- Postgres container
- Redis container
- Prometheus container
- in-process ShadowHoTT bilattice reports
- runtime De Morgan symmetry report
- offline training-capacity planner
- ShadowHoTT eval command
- regression-suite command
- buyer-demo script
- acquisition/diligence documentation under `docs/acquisition/`
- security documentation in `SECURITY.md`
- local smoke tests and regression tests

The package is structured for private diligence review, controlled pilots, and integration into a real Lean/Mathlib validation environment.

---

## What does not ship

This repository is an acquisition-clean pilot artifact, not a finished enterprise SaaS product.

The following are intentionally not bundled:

### No general natural-language theorem prover

The shipped `LLMBridgeTranslator` is a deterministic scaffold.

It recognizes a small number of hardcoded English theorem families:

- group associativity,
- group left-cancellation,
- group commutativity as a deliberate drift trap.

Unsupported requests route to `unsupported`.

The package does not pretend to translate arbitrary mathematics from English into Lean.

### No bundled frontier-model adapter

The frontier-model path is exposed through `shadowproof_model_provider_call`, which posts a generic JSON envelope only to server-configured provider URLs.

Caller-supplied provider URLs, caller-supplied headers, and caller-supplied bearer tokens are rejected.

Specific adapters for frontier providers are not bundled.

### No Python-level kernel sandbox

Production deployments must run the Lean worker inside an isolated environment such as:

- Docker,
- gVisor,
- Firecracker,
- Kubernetes with strict resource controls,
- or an equivalent hardened execution boundary.

The Python package itself does not provide a kernel sandbox.

### No external security review

The audits that produced the v0.25.2, v0.25.3, v0.25.4, and v0.25.6 hardening patches were internal exercises.

Third-party security review remains outstanding for enterprise general availability.

### No real customer eval corpora

The shipped examples and evals are smoke-test sized.

Real deployment requires larger customer-specific corpora.

### No trained production policy file

The framework includes training-capacity planning and policy scaffolding, but a trained production policy must be populated from real customer evals.

---

## Repository layout

Representative layout:

```text
shadowproof_core/
  asgi.py
  cli.py
  lean_lex.py
  repair.py
  security.py
  ...

deploy/
  docker-compose.yml
  lean-worker.Dockerfile
  ...

docs/
  acquisition/
    DILIGENCE_INDEX.md
    DILIGENCE_STATUS.md
  ...

examples/
  evals/
  optimization/
  tool_requests/

mcp/
  src/
  dist/
  package.json

schemas/
  openai_mcp_tool_descriptors.json

scripts/
  run_buyer_demo.sh
  ci_secret_scan.py

tests/
  ...
```

Primary diligence documents live in:

```text
docs/acquisition/
```

Start with:

```text
docs/acquisition/DILIGENCE_INDEX.md
docs/acquisition/DILIGENCE_STATUS.md
```

---

## Local installation

From the repository root:

```bash
pip install -e .
```

For production/pilot extras:

```bash
pip install -e '.[prod]'
```

---

## Local validation

Run the Python test suite:

```bash
python -m pytest tests/ -q
```

Expected v25.6 local result:

```text
119 passed, 1 skipped
```

Run the De Morgan symmetry report:

```bash
python -m shadowproof_core.cli demorgan-symmetry examples/tool_requests/demorgan_symmetry.json
```

Run the offline training-capacity planner:

```bash
python -m shadowproof_core.cli training-capacity-plan examples/optimization/training_capacity_plan.json
```

Run the ShadowHoTT eval:

```bash
python -m shadowproof_core.cli shadowhott-eval examples/evals/shadowhott_eval.json
```

Run the regression suite:

```bash
python -m shadowproof_core.cli regression examples/evals/regression_suite.json
```

Run the secret scan:

```bash
python scripts/ci_secret_scan.py
```

---

## Local API demo

Set local bearer-token auth:

```bash
export SHADOWPROOF_AUTH_MODE=bearer
export SHADOWPROOF_BEARER_TOKENS=dev-token:default
```

Start the stdlib server:

```bash
python -m shadowproof_core.cli serve --host 127.0.0.1 --port 8765
```

In another shell:

```bash
curl -sS -X POST http://127.0.0.1:8765/shadowproof_shadowhott_state \
  -H 'Authorization: Bearer dev-token' \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"smoke","proof_graph":[],"lean_status":"not_run","status":"unchecked"}'
```

---

## ASGI pilot server

Install production extras:

```bash
pip install -e '.[prod]'
```

Run with Uvicorn:

```bash
uvicorn shadowproof_core.asgi:app --host 0.0.0.0 --port 8765
```

---

## Full pilot stack

From the deployment directory:

```bash
cd deploy
docker compose up --build
```

Important note:

The bundled Lean-worker container is a stub. Replace:

```text
deploy/lean-worker.Dockerfile
```

with a real Lean 4 / Mathlib image before running the validation path in a serious pilot.

Against the stub, the bridge should report:

```text
lean_status: not_available
```

That is expected behavior.

---

## Buyer demo

Run:

```bash
bash scripts/run_buyer_demo.sh
```

The buyer demo walks through:

- bilattice axiom report,
- offline capacity plan,
- ShadowHoTT eval,
- regression suite,
- commercial-section endpoints.

It exits `0` and prints JSON for every section when the local environment is configured correctly.

---

## TypeScript MCP bridge

The repository includes a deliberately minimal TypeScript MCP bridge under:

```text
mcp/
```

Build it with:

```bash
cd mcp
npm ci --ignore-scripts
npm run build
```

The MCP bridge is intentionally narrow. It is present for integration demonstration and OpenAI-native tool-surface compatibility, not as a full SDK.

---

## Tool surface

The in-process tool registry contains 84 tools.

Of these, 35 are declared in:

```text
schemas/openai_mcp_tool_descriptors.json
```

The omitted tools are admin, domain-pack, and promotion tools that are not part of the buyer-facing API surface.

All HTTP/ASGI tool routes resolve to input schemas.

High-risk routes use strict exact schemas where possible.

---

## Security posture

See:

```text
SECURITY.md
```

for the full threat model and hardening notes.

Security hardening applied across v0.25.2, v0.25.3, v0.25.4, and v0.25.6 includes:

- server configuration comes from environment variables only;
- request bodies cannot override server configuration;
- tenant identity is bound to the authenticating credential;
- payload-supplied `tenant_id` must match the authenticated tenant;
- tenant directory paths reject `..`, `.`, and dots-only ids;
- `relative_to()` is enforced as defense in depth;
- rejection memory is tenant-scoped by default;
- stdlib HTTP server has a per-connection timeout;
- quota mode comparisons are normalized before rate-limit checks;
- Memory/Redis quota modes cannot bypass enforcement through casing drift;
- all HTTP/ASGI routes resolve to input schemas;
- high-risk routes use strict exact schemas where possible;
- additional file-reading and file-writing paths are root-guarded;
- domain-pack list/get/retrieval share the same allowed-root policy;
- file-writing HTTP routes are admin-scoped;
- Lean comment and literal masking is delimiter-aware;
- nested Lean block comments are handled;
- proof-body repair replacement uses a delimiter-aware anchor splitter rather than raw regex substitution.

The v25.6 retail-hardening patch specifically addresses Lean comment/literal masking and proof-body replacement fragility.

---

## Retail hardening in v25.6

v25.6 includes a hardening pass over Lean parsing-adjacent code.

The key changes are:

1. Lean comment and string masking is now delimiter-aware.
2. Nested Lean block comments are handled.
3. Lean comment markers inside string literals do not hide real declarations.
4. Security preflight, theorem-lock, and ShadowHoTT fingerprint obstruction checks share the safer masking behavior.
5. Proof-body repair replacement no longer depends on fragile raw regex substitution.
6. Replacement now uses a delimiter-aware anchor splitter.

This reduces the risk that `axiom`, `sorry`, theorem-target drift, or repair anchors are misread because of comments, nested comments, or string literals.

---

## Lean / Mathlib formalization

A standalone Lean 4 / Mathlib formalization of the De Morgan symmetry and bilattice claims is included under:

```text
lean_project_template/ShadowProof/DemorganSymmetry.lean
```

The runtime counterparts are:

```text
shadowproof demorgan-symmetry
bilattice_axiom_report()
```

The intended relationship is:

- Lean file: formal reference template.
- Runtime report: in-process operational counterpart.
- Tests: regression guard against semantic drift.

Production diligence should include a fresh Lean/Mathlib transcript generated in the buyer’s target Lean environment.

---

## ShadowHoTT correctness boundary

The ShadowHoTT finite bilattice layer is intentionally small and explicit.

The package claims:

- `L = Bool × Bool`;
- designation is `truth == True`;
- De Morgan duality is coordinate swap;
- the swap has order two;
- the swap fixes `both` and `neither`;
- the swap exchanges `top` and `bottom`;
- the swap is not designation-preserving;
- path composition is `(t₁ ∧ t₂, r₁ ∨ r₂)`;
- Lean-accepted plus refuted states route to `human_review`;
- patch morphisms must preserve theorem fingerprints;
- No-Glutty-J monitoring prevents contradiction-bearing states from being silently auto-accepted.

The package does not claim that the finite bilattice itself proves arbitrary mathematics.

It governs proof-attempt disposition around Lean validation.

---

## Commercial status

ShadowProof Bridge v25.6 is:

```text
pilot-ready
buyer-demo-ready
private-diligence-ready
acquisition-clean
```

It is not yet:

```text
enterprise-GA
externally security-certified
production-SLA-backed
fully provider-adapter-complete
trained on real customer corpora
```

This distinction is intentional.

The repository is suitable for technical diligence, controlled pilots, and acquisition evaluation.

---

## Outstanding for enterprise GA

Before enterprise general availability, the following remain outstanding:

1. External security review by a third-party firm.
2. Legal and SLA work.
3. Signed certificate / registry publishing pipeline.
4. Large customer evaluation corpora.
5. Real Lean CI transcript at production scale.
6. Customer-specific frontier-model adapters.
7. Customer-specific retrieval integrations.
8. Production isolated Lean worker.
9. Trained policy file populated from real customer evals.
10. Deployment-specific observability and incident-response procedures.

---

## Example positioning

ShadowProof Bridge is best understood as:

```text
A paraconsistent HoTT bridge between LLM proof generation and Lean validation,
with bilattice-governed repair, rejection, acceptance, and human-review routing.
```

A longer description:

```text
ShadowProof Bridge is a self-hostable paraconsistent HoTT LLM-to-Lean gateway
for contradiction-aware proof validation and repair. It routes Lean proof attempts
and LLM-generated proof proposals through security preflight, theorem-fingerprint
locking, Lean validation, and 4-valued ShadowHoTT bilattice semantics, preserving
useful repair structure while preventing contradiction-bearing states from being
silently auto-accepted.
```

---

## License and diligence

This is a private acquisition/diligence repository.

Do not treat this repository as a public production SaaS release unless and until the outstanding GA items have been completed.

For diligence review, begin with:

```text
docs/acquisition/DILIGENCE_INDEX.md
docs/acquisition/DILIGENCE_STATUS.md
SECURITY.md
CHANGELOG.md
```
