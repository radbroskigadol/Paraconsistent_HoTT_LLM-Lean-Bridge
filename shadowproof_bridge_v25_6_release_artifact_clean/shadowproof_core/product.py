from __future__ import annotations

from typing import Any

from .config import ShadowProofConfig
from .sandbox import sandbox_check
from .shadowhott import bilattice_axiom_report


REQUIRED_COMMERCIAL_AREAS = [
    "actual_shadowhott_math",
    "pinned_lean_mathlib",
    "hardened_sandbox",
    "production_api_mcp",
    "auth_tenancy_quotas",
    "persistent_storage_retention",
    "observability_dashboard",
    "full_mathlib_retrieval",
    "large_domain_eval_corpus",
    "ci_cd_release_gates",
    "security_threat_model",
    "privacy_compliance_controls",
    "human_review_workflow",
    "model_provider_abstraction",
    "cost_accounting",
    "documentation_site",
    "acquisition_readiness_assets",
    "claims_boundary",
]


def product_readiness_report(cfg: ShadowProofConfig) -> dict[str, Any]:
    checks = []

    def add(area: str, status: str, evidence: str, next_step: str):
        checks.append({"area": area, "status": status, "evidence": evidence, "next_step": next_step})

    axioms = bilattice_axiom_report()
    add(
        "actual_shadowhott_math",
        "production_ready" if axioms.get("all_passed") else "missing",
        "L=2×2 bilattice, designation predicate, De Morgan involution, ∧_L composition, refl-top, patch morphisms, bilattice-driven repair selection, strict labels, and No-Glutty-J monitor are implemented and tested.",
        "expand translator path coverage across all supported mathematical domains",
    )
    add("pinned_lean_mathlib", "partial", "lean_project_template now includes lean-toolchain, pinned lakefile.lean, and lake-manifest.json inputs; this audit environment did not run live Lean/lake", "run lake build in Lean-equipped buyer CI and preserve the transcript")
    add("hardened_sandbox", "partial", "Docker/compose now include non-root users, no-new-privileges, cap-drop, read-only/tmpfs where compatible, request limits, and health checks; the Lean worker remains a stub", "replace stub with real isolated no-network Lean worker and validate with gVisor/Firecracker/seccomp/AppArmor plus hostile corpus")
    add("production_api_mcp", "partial", "HTTP/ASGI now enforce request-size bounds, all-route schema validation, admin-route separation, and fail-closed auth outside development; MCP has timeout/buffer bounds and a checked lockfile/build output, but still needs conformance evidence", "publish MCP conformance tests and harden ingress/gateway policies")
    add("auth_tenancy_quotas", "partial", "bearer tenant binding, OIDC/JWT scaffold, Redis-backed quota adapter, cached Redis limiter, and disabled-auth fail-closed outside development are implemented", "connect to customer IdP and run tenant-isolation audit")
    add("persistent_storage_retention", "partial", "the package includes StorageBackend protocol with JSONL demo backend and optional Postgres backend/migration scaffold", "enable row-level security and immutable audit-event storage in production Postgres")
    add("observability_dashboard", "partial", "the package includes active readiness checks, Prometheus counters/histograms, structured JSON logs, and OpenTelemetry hooks", "connect to customer Prometheus/Grafana/OTel collector and define alert SLOs")
    add("full_mathlib_retrieval", "partial", "domain packs and lexical/index retrieval exist", "index full Mathlib and add vector/reranking backend")
    add("large_domain_eval_corpus", "partial", "regression suite and ShadowHoTT axiom/property tests exist", "add thousands of domain cases and negative theorem-drift attacks")
    add("ci_cd_release_gates", "partial", "release-gate, regression, ShadowHoTT eval, product-readiness, and license-scan commands are implemented; hosted CI/SBOM/signing hooks are not bundled in this code package", "add hosted CI, SBOM generation, image signing, registry publishing, and vulnerability scanning")
    add("security_threat_model", "partial", "security docs plus regression fixes for payload Lean-command rejection, theorem-lock errors, admin route scoping, path-root guards, and schema validation are implemented", "perform external security review and implement findings")
    add("privacy_compliance_controls", "scaffolded", "privacy modes/retention controls exist", "map to company DPA/security requirements")
    add("human_review_workflow", "partial", "review packet generation exists and glutty BOTH routes to HUMAN_REVIEW", "build reviewer UI and GitHub/Lean export")
    add("model_provider_abstraction", "scaffolded", "model provider interface plus mock/frontier_http/local_deterministic adapters and local behavior simulation exist", "add production provider adapters, auth, streaming, retries, redaction, and model-specific schemas")
    add("cost_accounting", "scaffolded", "metrics can record estimated tokens and cost estimator exists", "plug in actual model billing and worker compute costs")
    add("documentation_site", "partial", "the package includes README quickstart, OpenAPI generation, MCP notes, and acquisition packet docs; hosted docs and generated SDKs are not bundled", "publish hosted docs and generate Python/TypeScript SDKs from OpenAPI")
    add("acquisition_readiness_assets", "partial", "core markdown acquisition packet, claims boundary, diligence checklist, demo playbook, valuation memo, roadmap, security questionnaire starter, and architecture note are included; generated PPTX/PDF collateral is not included in this code package", "generate buyer-branded PPTX/PDF collateral if needed")
    add("claims_boundary", "production_ready", "a conservative claims boundary separates implemented facts from buyer/compliance work", "review wording with buyer legal/security before external publication")

    score_map = {"missing": 0, "scaffolded": 1, "partial": 2, "production_ready": 3}
    score = sum(score_map.get(c["status"], 0) for c in checks)
    max_score = len(checks) * 3
    status = "production_ready" if all(c["status"] == "production_ready" for c in checks) else "pilot_ready" if score >= 24 else "technical_preview"
    return {
        "status": status,
        "readiness_score": score,
        "max_score": max_score,
        "readiness_ratio": score / max_score if max_score else None,
        "config": cfg.to_dict(),
        "shadowhott_axioms": axioms,
        "sandbox": sandbox_check(cfg),
        "checks": checks,
        "release_gate": {
            "must_have_before_pilot": [
                "claims-boundary reviewed",
                "buyer demo script run",
                "company-mirrored pinned Lean/Mathlib worker image",
                "auth enabled in deployed environment",
                "tenant storage configured",
                "regression and ShadowHoTT axiom CI passing",
                "sandbox validated with hostile proofs",
                "observability connected",
            ],
            "must_have_before_enterprise_ga": [
                "full retrieval backend",
                "large eval corpus",
                "external security review",
                "privacy/legal review",
                "admin controls",
                "SLAs/support playbooks",
                "artifact signing and SBOM",
            ],
        },
    }
