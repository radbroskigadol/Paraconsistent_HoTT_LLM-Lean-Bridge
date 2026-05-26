from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable

from .path_guard import resolve_under_allowed_root


@dataclass
class ReleaseGateResult:
    gate: str
    status: str  # pass | warn | fail | skipped
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


def generate_release_report(payload: dict[str, Any], tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    release_id = str(payload.get("release_id", f"release_{int(time.time())}"))
    release_mode = str(payload.get("release_mode", "pilot"))  # pilot | enterprise_ga
    out_dir = resolve_under_allowed_root(payload.get("output_dir"), default="release_reports", kind="release_report output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    sections: dict[str, Any] = {}
    gates: list[ReleaseGateResult] = []

    # 1. Regression suite
    if payload.get("regression_suite_path"):
        regression_payload = load_json_with_base(payload["regression_suite_path"])
        regression = safe_call(tool_caller, "shadowproof_regression_suite", regression_payload)
        sections["regression"] = regression
        gates.append(gate_regression(regression))
    else:
        sections["regression"] = {"status": "skipped", "reason": "no regression_suite_path"}
        gates.append(ReleaseGateResult("regression", "skipped", "No regression suite path supplied."))

    # 2. Product readiness
    readiness = safe_call(tool_caller, "shadowproof_product_readiness", payload.get("product_readiness_payload", {}))
    sections["product_readiness"] = readiness
    gates.append(gate_readiness(readiness, release_mode))

    # 3. Threat model
    threat_payload = payload.get("threat_model_payload", {})
    threat_model = safe_call(tool_caller, "shadowproof_security_threat_model", threat_payload)
    sections["threat_model"] = threat_model
    gates.append(gate_threat_model(threat_model, release_mode))

    # 4. License scan
    license_payload = payload.get("license_scan_payload", {"root": ".", "max_files": 1000})
    license_scan = safe_call(tool_caller, "shadowproof_license_scan", license_payload)
    sections["license_scan"] = license_scan
    gates.append(gate_license_scan(license_scan, release_mode))

    # 5. Domain-pack registry
    domain_payload = payload.get("domain_pack_registry_payload", {})
    if domain_payload.get("registry_path"):
        domain_registry = safe_call(tool_caller, "shadowproof_domain_pack_registry", domain_payload)
    else:
        domain_registry = {"status": "skipped", "reason": "no domain_pack_registry_payload.registry_path"}
    sections["domain_pack_registry"] = domain_registry
    gates.append(gate_domain_registry(domain_registry, release_mode))

    # 6. Proof-artifact registry
    proof_payload = payload.get("proof_artifact_registry_payload", {})
    if proof_payload.get("registry_path"):
        proof_registry = safe_call(tool_caller, "shadowproof_proof_artifact_registry", proof_payload)
    else:
        proof_registry = {"status": "skipped", "reason": "no proof_artifact_registry_payload.registry_path"}
    sections["proof_artifact_registry"] = proof_registry
    gates.append(gate_proof_registry(proof_registry, release_mode))

    # 7. Optional existing conservative release gate
    if payload.get("include_existing_release_gate", True):
        release_gate_payload = payload.get("release_gate_payload", {"root": ".", "max_files": 1000})
        release_gate = safe_call(tool_caller, "shadowproof_release_gate", release_gate_payload)
        sections["existing_release_gate"] = release_gate
        gates.append(gate_existing_release_gate(release_gate, release_mode))

    hard_failures = [g for g in gates if g.status == "fail"]
    warnings = [g for g in gates if g.status == "warn"]
    skipped = [g for g in gates if g.status == "skipped"]

    overall_status = "pass"
    if hard_failures:
        overall_status = "blocked"
    elif warnings and release_mode == "enterprise_ga":
        overall_status = "blocked"
    elif warnings or skipped:
        overall_status = "conditional_pass"

    report = {
        "status": overall_status,
        "release_id": release_id,
        "release_mode": release_mode,
        "created_at": time.time(),
        "summary": {
            "gate_count": len(gates),
            "pass_count": sum(1 for g in gates if g.status == "pass"),
            "warn_count": len(warnings),
            "fail_count": len(hard_failures),
            "skipped_count": len(skipped),
        },
        "gates": [asdict(g) for g in gates],
        "sections": sections,
        "next_actions": next_actions(gates, release_mode),
    }

    json_path = out_dir / f"{release_id}.release_report.json"
    md_path = out_dir / f"{release_id}.release_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_release_markdown(report), encoding="utf-8")

    return {
        "status": overall_status,
        "release_id": release_id,
        "release_mode": release_mode,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": report["summary"],
        "gates": report["gates"],
        "next_actions": report["next_actions"],
    }


def release_checklist(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    mode = str(payload.get("release_mode", "pilot"))
    common = [
        "Run full ShadowProof regression suite.",
        "Confirm false theorem-drift escape count is zero.",
        "Confirm sorry/axiom/security trap escapes are zero.",
        "Attach domain-pack eval evidence for any active packs.",
        "Attach proof validation evidence for any exported proof artifacts.",
        "Generate human review packets for high-risk proof artifacts.",
        "Review threat model report.",
        "Run license scan scaffold and company SBOM scan.",
        "Archive release report JSON and Markdown.",
    ]
    enterprise = [
        "Confirm production Lean worker sandbox is externally reviewed.",
        "Confirm SSO/OIDC/SAML and tenant isolation are configured.",
        "Confirm Postgres/S3/Redis or company equivalents are configured.",
        "Confirm monitoring, alerts, and incident playbooks are active.",
        "Confirm legal/privacy/DPA review is complete.",
        "Confirm release gate passes with no critical blockers.",
    ]
    return {
        "status": "ok",
        "release_mode": mode,
        "checklist": common + (enterprise if mode == "enterprise_ga" else []),
    }


def gate_regression(regression: dict[str, Any]) -> ReleaseGateResult:
    if regression.get("status") in {"error", "failed"}:
        return ReleaseGateResult("regression", "fail", f"Regression status is {regression.get('status')}.", regression)
    metrics = regression.get("metrics", {})
    failed = int(metrics.get("failed_count", 0) or 0)
    drift = int(metrics.get("false_theorem_drift_escape_count", 0) or 0)
    if failed > 0:
        return ReleaseGateResult("regression", "fail", f"{failed} regression cases failed.", metrics)
    if drift > 0:
        return ReleaseGateResult("regression", "fail", f"{drift} theorem-drift escapes detected.", metrics)
    if regression.get("status") == "skipped":
        return ReleaseGateResult("regression", "skipped", regression.get("reason", "Skipped."), regression)
    return ReleaseGateResult("regression", "pass", "Regression gate passed.", metrics)


def gate_readiness(readiness: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    status = readiness.get("status")
    if status == "production_ready":
        return ReleaseGateResult("product_readiness", "pass", "Product readiness is production_ready.", readiness)
    if release_mode == "pilot" and status in {"technical_preview", "ok"}:
        return ReleaseGateResult("product_readiness", "warn", "Product is acceptable for pilot but not GA.", {"status": status})
    return ReleaseGateResult("product_readiness", "fail", f"Product readiness status is {status}.", {"status": status})


def gate_threat_model(threat_model: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    blockers = threat_model.get("release_blockers", []) or []
    critical = [b for b in blockers if b.get("severity") == "critical"]
    if critical and release_mode == "enterprise_ga":
        return ReleaseGateResult("threat_model", "fail", f"{len(critical)} critical threat controls unresolved.", {"critical_blockers": critical})
    if critical:
        return ReleaseGateResult("threat_model", "warn", f"{len(critical)} critical threat controls unresolved; acceptable only for constrained pilot.", {"critical_blockers": critical})
    return ReleaseGateResult("threat_model", "pass", "No critical threat blockers reported.", {"blocker_count": len(blockers)})


def gate_license_scan(scan: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    findings = scan.get("findings", []) or []
    copyleft = [f for f in findings if f.get("license_hint") in {"GPL", "LGPL"}]
    if copyleft and release_mode == "enterprise_ga":
        return ReleaseGateResult("license_scan", "fail", "Possible copyleft license findings require legal review.", {"findings": copyleft[:20]})
    if copyleft:
        return ReleaseGateResult("license_scan", "warn", "Possible copyleft findings; legal review required before GA.", {"findings": copyleft[:20]})
    return ReleaseGateResult("license_scan", "pass", "No obvious copyleft findings in lightweight scan.", {"finding_count": len(findings)})


def gate_domain_registry(registry: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    if registry.get("status") == "skipped":
        return ReleaseGateResult("domain_pack_registry", "skipped", registry.get("reason", "Skipped."), registry)
    if registry.get("status") != "ok":
        return ReleaseGateResult("domain_pack_registry", "fail", "Could not read domain-pack registry.", registry)
    entries = registry.get("registry", {}).get("entries", {})
    active = [e for e in entries.values() if e.get("state") == "active"]
    bad_active = []
    for e in active:
        roles = {r.get("role") for r in e.get("reviews", []) if r.get("decision") == "approve"}
        if not {"domain_expert", "formal_methods", "release_owner"}.issubset(roles):
            bad_active.append(e.get("domain"))
        evals = e.get("eval_attachments", [])
        if not evals or evals[-1].get("failed_count", 1) > 0 or evals[-1].get("false_theorem_drift_escape_count", 0) > 0:
            bad_active.append(e.get("domain"))
    if bad_active:
        return ReleaseGateResult("domain_pack_registry", "fail", "Active domain packs missing approvals or clean eval evidence.", {"bad_active": bad_active})
    return ReleaseGateResult("domain_pack_registry", "pass", f"{len(active)} active domain packs pass registry checks.", {"active_count": len(active)})


def gate_proof_registry(registry: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    if registry.get("status") == "skipped":
        return ReleaseGateResult("proof_artifact_registry", "skipped", registry.get("reason", "Skipped."), registry)
    if registry.get("status") != "ok":
        return ReleaseGateResult("proof_artifact_registry", "fail", "Could not read proof-artifact registry.", registry)
    entries = registry.get("registry", {}).get("entries", {})
    exported = [e for e in entries.values() if e.get("state") == "exported"]
    bad = []
    for e in exported:
        roles = {r.get("role") for r in e.get("reviews", []) if r.get("decision") == "approve"}
        if not {"domain_expert", "formal_methods", "release_owner"}.issubset(roles):
            bad.append(e.get("artifact_id"))
        kinds = {a.get("kind"): a for a in e.get("validation_attachments", [])}
        if not ("security" in kinds and "lean" in kinds and "shadowhott" in kinds):
            bad.append(e.get("artifact_id"))
        if kinds.get("lean", {}).get("lean_status") != "accepted":
            bad.append(e.get("artifact_id"))
    if bad:
        return ReleaseGateResult("proof_artifact_registry", "fail", "Exported proof artifacts missing approvals or validation evidence.", {"bad_artifacts": bad})
    return ReleaseGateResult("proof_artifact_registry", "pass", f"{len(exported)} exported proof artifacts pass registry checks.", {"exported_count": len(exported)})


def gate_existing_release_gate(release_gate: dict[str, Any], release_mode: str) -> ReleaseGateResult:
    status = release_gate.get("status")
    blockers = release_gate.get("blockers", []) or []
    if status == "pass":
        return ReleaseGateResult("existing_release_gate", "pass", "Conservative release gate passed.", release_gate)
    if release_mode == "pilot":
        return ReleaseGateResult("existing_release_gate", "warn", "Conservative GA release gate is blocked; acceptable for technical pilot only.", {"blockers": blockers})
    return ReleaseGateResult("existing_release_gate", "fail", "Conservative release gate blocked enterprise GA.", {"blockers": blockers})


def next_actions(gates: list[ReleaseGateResult], release_mode: str) -> list[str]:
    actions = []
    for g in gates:
        if g.status in {"fail", "warn"}:
            if g.gate == "regression":
                actions.append("Fix failing regression cases and rerun the suite.")
            elif g.gate == "product_readiness":
                actions.append("Complete production readiness blockers or restrict release to pilot.")
            elif g.gate == "threat_model":
                actions.append("Resolve critical threat controls or obtain explicit pilot risk acceptance.")
            elif g.gate == "license_scan":
                actions.append("Run real SBOM/license review and resolve flagged dependencies.")
            elif g.gate == "domain_pack_registry":
                actions.append("Ensure active domain packs have clean evals and required approvals.")
            elif g.gate == "proof_artifact_registry":
                actions.append("Ensure exported proof artifacts have security/Lean/ShadowHoTT evidence and approvals.")
            elif g.gate == "existing_release_gate":
                actions.append("Resolve conservative release-gate blockers before enterprise GA.")
    if not actions:
        actions.append("Archive release report and proceed according to release policy.")
    return actions


def safe_call(tool_caller: Callable[[str, dict[str, Any]], dict[str, Any]], tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return tool_caller(tool_name, payload)
    except Exception as e:
        return {"status": "error", "tool": tool_name, "error": str(e)}


def load_json_with_base(pathlike: str | Path) -> dict[str, Any]:
    path = resolve_under_allowed_root(pathlike, must_exist=True, kind="release_report input file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("_suite_base_dir", str(path.parent))
    return payload


def render_release_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append(f"# ShadowProof Release Report: {report['release_id']}")
    lines.append("")
    lines.append(f"Mode: `{report['release_mode']}`")
    lines.append(f"Status: `{report['status']}`")
    lines.append("")
    lines.append("## Summary")
    for k, v in report["summary"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Gates")
    for g in report["gates"]:
        lines.append(f"### {g['gate']} — {g['status']}")
        lines.append(g["summary"])
        lines.append("")
    lines.append("## Next actions")
    for a in report["next_actions"]:
        lines.append(f"- {a}")
    lines.append("")
    return "\n".join(lines)
