# Claims Boundary

## Safe claims

- The package implements a 2x2 bilattice/ShadowHoTT-style control layer.
- Draft validation rejects theorem-lock drift by default before issuing a certificate.
- Glutty/refutation-carrying proof states route to human review.
- The repository is suitable for pilot diligence and self-hosted technical evaluation.

## Claims not supported by this package alone

- Production-hosted enterprise service.
- Externally penetration-tested platform.
- SOC 2, ISO, HIPAA, or formal legal compliance.
- Full Mathlib-scale performance validation.
- Live Lean kernel checking in this audit environment.

## v0.25.5 acquisition-clean status

Safe additional claims after the v0.25.5 patch:

- The API Dockerfile includes runtime schemas, docs, examples, scripts, and the Lean template needed by the local inspection package.
- Domain-pack operations are guarded by `SHADOWPROOF_ALLOWED_FILE_ROOTS`.
- Authored domain packs can be validated and then retrieved by the Mathlib/domain retrieval path.
- Frontier HTTP egress is deployment-configured; caller-supplied provider URLs, headers, and bearer tokens are not accepted.
- The package includes local CI, SBOM, license/notice, and a diligence-status document.

Still not safe to claim without buyer-side integration:

- Production Lean/Mathlib execution under a pinned worker image.
- Live frontier-model quality or throughput.
- Independent penetration test, SOC 2/ISO compliance, or legal/security signoff.



## v0.25.6 release-artifact clean status

Safe additional claims after the v0.25.6 patch:

- Runtime schemas are preserved in source-tree, Docker source-copy, and wheel-install layouts.
- The CLI, HTTP/ASGI, and MCP-through-CLI paths share schema validation at the Python boundary.
- Model-provider egress no longer accepts caller-supplied URLs and now rejects private/internal DNS resolutions.
- The bilattice core was re-audited against finite algebra laws: meet/join semilattices, absorption, De Morgan duality, order-two involution, and binary designation.

Still do not claim production Lean/Mathlib validation until a Lean-equipped runner produces preserved transcripts.
