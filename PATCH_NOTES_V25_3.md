# ShadowProof Bridge v25.3 Boundary-Hardening Patch Notes

This patch applies the additional local fixes identified after the v25.2 hardened package. It still does not require a live Lean kernel, LLM connector, Redis service, OIDC provider, or container registry.

## Implemented fixes

- Fixed quota enforcement fail-open caused by case-sensitive `quota_mode` comparison. `Memory` and `Redis` are now normalized before rate-limit checks.
- Renamed the three misnamed primary input schemas so the runtime loader validates `shadowproof_shadowhott_state`, `shadowproof_pilot_plan`, and `shadowproof_compile_repair_prompt`.
- Added descriptor/family/generic schema fallback so every one of the 83 HTTP/ASGI tool routes resolves to a boundary input schema.
- Added tests proving malformed ShadowHoTT, pilot-plan, repair-prompt, descriptor-only, and family-schema requests are rejected before tool dispatch.
- Added root-guarding for memory, optimization, eval/regression, retrieval, release-report, license-scan, domain-authoring, and onboarding paths.
- Moved additional file-writing HTTP routes behind admin-token scope: `shadowproof_create_domain_pack`, `shadowproof_domain_pack_eval_stub`, `shadowproof_onboarding_packet`, and `shadowproof_release_report`.
- Corrected buyer-facing docs that overstated bundled SDK/MkDocs/hosted-CI assets.
- Replaced the empty eval-harness document with a usable evaluation-harness note.

## Verification run locally

```bash
python -m pytest -q                 # 89 passed
python -m compileall -q shadowproof_core
```

## Still deferred to deployment

- Live Lean/lake kernel check of the template project.
- Production OIDC/JWKS, Redis, Postgres, container runtime, and observability verification.
- External security review.
- Live LLM/frontier-model integration testing.
- Generated PPTX/PDF buyer collateral and hosted SDK/documentation publishing.
