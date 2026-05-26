from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .path_guard import resolve_under_allowed_root
from typing import Any


@dataclass
class PilotTask:
    week: int
    owner: str
    area: str
    task: str
    deliverable: str
    acceptance_criteria: list[str]
    blockers: list[str]


@dataclass
class PilotPlan:
    company_id: str
    pilot_id: str
    duration_weeks: int
    target_domains: list[str]
    model_providers: list[str]
    storage_backend: str
    retrieval_backend: str
    lean_worker_mode: str
    success_metrics: dict[str, Any]
    tasks: list[PilotTask]


def generate_pilot_plan(payload: dict[str, Any]) -> dict[str, Any]:
    company_id = str(payload.get("company_id", "example_company"))
    pilot_id = str(payload.get("pilot_id", f"pilot_{int(time.time())}"))
    domains = list(payload.get("target_domains", ["algebra", "order", "topology"]))
    providers = list(payload.get("model_providers", ["frontier_http"]))
    storage = str(payload.get("storage_backend", "postgres_or_company_storage"))
    retrieval = str(payload.get("retrieval_backend", "vector_http_or_company_retrieval"))
    lean_worker = str(payload.get("lean_worker_mode", "http_container_worker"))

    tasks = [
        PilotTask(1, "Company platform", "environment", "Provision dev namespace, secrets, and artifact storage.", "ShadowProof dev environment reachable by engineers.", ["API health check passes", "secrets are not stored in repo"], []),
        PilotTask(1, "Formal methods lead", "Lean/Mathlib", "Pin Lean, Mathlib, and company private Lean libraries.", "Committed lean-toolchain/lake-manifest or approved pinned image.", ["Lean worker can prove `example : True := by trivial`", "Mathlib import test passes"], ["Lean build/cache time"]),
        PilotTask(1, "Security", "sandbox", "Review Lean worker sandbox configuration.", "Approved sandbox profile.", ["network disabled or controlled", "CPU/RAM/time limits enforced", "filesystem isolation documented"], ["container runtime policy"]),
        PilotTask(1, "ML platform", "model provider", "Connect frontier model adapter.", "Provider returns schema-valid DraftProposal JSON in mock flow.", ["mock provider replaced or routed", "tokens/costs recorded"], ["provider API approval"]),
        PilotTask(2, "Retrieval owner", "retrieval", "Index Mathlib and selected private libraries.", "Retrieval endpoint or JSONL index available.", ["candidate theorem lookup works", "domain-pack retrieval eval passes"], ["private library access"]),
        PilotTask(2, "Formal methods lead", "eval corpus", "Create 100-300 pilot eval cases across target domains.", "Pilot eval corpus committed.", ["valid proofs", "theorem-drift traps", "wrong theorem-name repairs", "typeclass failures"], ["SME availability"]),
        PilotTask(2, "Bridge owner", "integration", "Run ShadowHoTT/regression suite against company environment.", "Regression report artifact.", ["false theorem-drift escapes = 0", "ShadowHoTT eval pass rate = 1.0"], ["Lean worker readiness"]),
        PilotTask(2, "Security", "privacy", "Configure tenant storage, retention, audit logs, and privacy mode.", "Approved data-flow and retention config.", ["hash_only or approved raw mode", "deletion workflow tested"], ["legal/DPA review"]),
        PilotTask(3, "Pilot users", "workflow", "Run real user formalization tasks through review workflow.", "Review packets and accepted proofs for pilot tasks.", ["review packet generated", "certificate captured", "no sorry/axiom leaks"], ["domain expert time"]),
        PilotTask(3, "ML platform", "optimization", "Enable policy logging and compare repair strategies by provider/domain.", "Optimization report.", ["tokens per accepted proof measured", "repair turns per accepted proof measured"], ["sufficient traffic"]),
        PilotTask(3, "Product owner", "go/no-go", "Evaluate pilot metrics against acceptance criteria.", "Pilot go/no-go report.", ["release gate result understood", "blockers listed with owners"], []),
    ]

    success_metrics = {
        "shadowhott_eval_pass_rate": 1.0,
        "false_theorem_drift_escape_count": 0,
        "sorry_axiom_escape_count": 0,
        "retrieval_eval_pass_rate_min": 0.95,
        "pilot_eval_acceptance_rate_target": payload.get("pilot_eval_acceptance_rate_target", 0.70),
        "median_repair_turns_target": payload.get("median_repair_turns_target", 3),
        "review_packet_required": True,
        "certificate_required": True,
    }

    plan = PilotPlan(
        company_id=company_id,
        pilot_id=pilot_id,
        duration_weeks=3,
        target_domains=domains,
        model_providers=providers,
        storage_backend=storage,
        retrieval_backend=retrieval,
        lean_worker_mode=lean_worker,
        success_metrics=success_metrics,
        tasks=tasks,
    )
    return {"status": "ok", "pilot_plan": dataclass_to_dict(plan)}


def integration_checklist(payload: dict[str, Any]) -> dict[str, Any]:
    domains = list(payload.get("target_domains", ["algebra", "order", "topology"]))
    checklist = [
        section("Repository", [
            "Fork or vendor ShadowProof Bridge.",
            "Decide whether domain packs live in product repo or private proof repo.",
            "Pin dependencies and enable CI regression workflow.",
        ]),
        section("Lean/Mathlib", [
            "Pin `lean-toolchain`.",
            "Pin `lake-manifest.json`.",
            "Build and cache Mathlib.",
            "Add private Lean libraries if needed.",
            "Run Lean smoke: `example : True := by trivial`.",
        ]),
        section("Sandbox", [
            "Build Lean worker image.",
            "Disable network during proof checks unless explicitly approved.",
            "Enforce CPU/RAM/wall-time limits.",
            "Verify worker temp directories are cleaned.",
            "Document sandbox escape threat controls.",
        ]),
        section("Model provider", [
            "Implement `frontier_http` or provider-specific adapter.",
            "Enforce DraftProposal JSON-only output.",
            "Record model id, prompt tokens, completion tokens, cost.",
            "Disable provider training/data retention where required by contract.",
        ]),
        section("Retrieval", [
            "Index Mathlib declarations.",
            "Index private Lean libraries.",
            "Add company domain packs.",
            "Run retrieval evals for: " + ", ".join(domains),
            "Track retrieval hit rate and wrong-candidate rate.",
        ]),
        section("Storage/privacy", [
            "Choose Postgres/S3/company storage backend.",
            "Choose privacy mode: hash_only/redacted/raw_local.",
            "Set retention days.",
            "Test tenant deletion/export workflow.",
            "Review data flow with security/legal.",
        ]),
        section("Observability", [
            "Connect metrics to Prometheus/OpenTelemetry.",
            "Dashboard: acceptance rate, repair turns, token cost, false drift escapes.",
            "Alert on theorem-drift escape > 0.",
            "Alert on sorry/axiom escape > 0.",
        ]),
        section("Human review", [
            "Generate review packets for all pilot proofs.",
            "Define reviewer roles.",
            "Store review decision and notes.",
            "Export accepted Lean proofs into company Lean repo.",
        ]),
        section("Release gates", [
            "Run `shadowproof_regression_suite` in CI.",
            "Run ShadowHoTT eval suite.",
            "Run retrieval eval suite.",
            "Run theorem-drift/security trap suite.",
            "Run Lean validation suite.",
            "Run threat model and license scan scaffolds.",
        ]),
    ]
    return {"status": "ok", "checklist": checklist}


def acceptance_criteria(payload: dict[str, Any]) -> dict[str, Any]:
    phase = str(payload.get("phase", "pilot"))
    base = {
        "pilot": {
            "must_pass": [
                "ShadowHoTT core eval pass_rate = 1.0",
                "false_theorem_drift_escape_count = 0",
                "sorry/axiom/security trap escapes = 0",
                "retrieval eval pass_rate >= 0.95 on pilot corpus",
                "all accepted proofs have versioned certificate",
                "all high-risk repairs have review packet",
                "Lean worker sandbox approved for pilot",
                "tenant privacy/retention settings approved",
            ],
            "should_pass": [
                "median repair turns <= 3",
                "tokens per accepted proof measured by domain/model",
                "model-provider cost accounting enabled",
                "pilot users can reproduce accepted proofs in company Lean repo",
            ],
        },
        "enterprise_ga": {
            "must_pass": [
                "external security review completed",
                "legal/license review completed",
                "SSO/OIDC/SAML integrated",
                "Postgres/S3/Redis or company equivalents configured",
                "full Mathlib/private-library retrieval benchmark passing",
                "large domain eval corpus passing",
                "production monitoring/alerts enabled",
                "incident/support playbooks approved",
                "release gate passes without critical blockers",
            ],
            "should_pass": [
                "canary rollout plan approved",
                "policy rollback tested",
                "admin data export/delete tested",
                "cost dashboard reviewed by product owner",
            ],
        },
    }
    return {"status": "ok", "phase": phase, "criteria": base.get(phase, base["pilot"])}


def generate_onboarding_packet(payload: dict[str, Any]) -> dict[str, Any]:
    out_dir = resolve_under_allowed_root(payload.get("output_dir"), default=".shadowproof_data/onboarding", kind="onboarding output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = generate_pilot_plan(payload)["pilot_plan"]
    checklist = integration_checklist(payload)["checklist"]
    criteria = acceptance_criteria({"phase": payload.get("phase", "pilot")})["criteria"]

    packet = {
        "company_id": payload.get("company_id", "example_company"),
        "created_at": time.time(),
        "pilot_plan": plan,
        "integration_checklist": checklist,
        "acceptance_criteria": criteria,
    }

    json_path = out_dir / "shadowproof_onboarding_packet.json"
    md_path = out_dir / "shadowproof_onboarding_packet.md"
    json_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_onboarding_markdown(packet), encoding="utf-8")

    return {
        "status": "ok",
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "packet": packet,
    }


def adapter_conformance_plan(payload: dict[str, Any]) -> dict[str, Any]:
    adapter_type = str(payload.get("adapter_type", "all"))
    plans = {
        "model_provider": [
            "accepts prompt/system/model_id/max_tokens",
            "returns text or structured JSON",
            "reports token usage when available",
            "returns stable error shape",
            "does not mutate theorem fingerprint",
            "supports timeout handling",
        ],
        "storage": [
            "put/get/delete round trip works per tenant",
            "tenant A cannot read tenant B keys",
            "retention sweep works",
            "audit logs are append-only",
            "large review packet storage works",
        ],
        "retrieval": [
            "returns candidate theorem names",
            "returns provenance/source",
            "respects domain filters",
            "surfaces theorem-drift traps",
            "does not return private library entries across tenants",
            "has retrieval eval pass-rate report",
        ],
        "lean_worker": [
            "accepts Lean code",
            "returns accepted/rejected/timeout/not_available",
            "enforces timeout",
            "runs without network",
            "limits memory and CPU",
            "cleans temp files",
            "captures Lean/Mathlib version",
        ],
    }
    selected = plans if adapter_type == "all" else {adapter_type: plans.get(adapter_type, [])}
    return {"status": "ok", "adapter_type": adapter_type, "conformance_plan": selected}


def section(name: str, items: list[str]) -> dict[str, Any]:
    return {"section": name, "items": [{"done": False, "item": x} for x in items]}


def dataclass_to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: dataclass_to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [dataclass_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    return obj


def render_onboarding_markdown(packet: dict[str, Any]) -> str:
    lines = []
    lines.append(f"# ShadowProof Pilot Onboarding Packet")
    lines.append("")
    lines.append(f"Company: `{packet.get('company_id')}`")
    lines.append("")
    lines.append("## Success metrics")
    for k, v in packet["pilot_plan"]["success_metrics"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Week-by-week tasks")
    for t in packet["pilot_plan"]["tasks"]:
        lines.append(f"### Week {t['week']} — {t['area']}")
        lines.append(f"- Owner: {t['owner']}")
        lines.append(f"- Task: {t['task']}")
        lines.append(f"- Deliverable: {t['deliverable']}")
        lines.append("- Acceptance:")
        for a in t["acceptance_criteria"]:
            lines.append(f"  - {a}")
        if t["blockers"]:
            lines.append("- Possible blockers:")
            for b in t["blockers"]:
                lines.append(f"  - {b}")
        lines.append("")
    lines.append("## Integration checklist")
    for s in packet["integration_checklist"]:
        lines.append(f"### {s['section']}")
        for item in s["items"]:
            lines.append(f"- [ ] {item['item']}")
        lines.append("")
    lines.append("## Acceptance criteria")
    lines.append("### Must pass")
    for x in packet["acceptance_criteria"].get("must_pass", []):
        lines.append(f"- [ ] {x}")
    lines.append("### Should pass")
    for x in packet["acceptance_criteria"].get("should_pass", []):
        lines.append(f"- [ ] {x}")
    return "\n".join(lines) + "\n"
