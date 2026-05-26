from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .path_guard import resolve_under_allowed_root
from .schema_validation import strict_bool


PROOF_STATES = [
    "drafted",
    "security_checked",
    "lean_checked",
    "shadowhott_audited",
    "review_ready",
    "approved",
    "archived",
    "exported",
    "rejected",
    "deprecated",
]

ALLOWED_TRANSITIONS = {
    "drafted": {"security_checked", "rejected"},
    "security_checked": {"lean_checked", "rejected"},
    "lean_checked": {"shadowhott_audited", "rejected"},
    "shadowhott_audited": {"review_ready", "rejected"},
    "review_ready": {"approved", "rejected"},
    "approved": {"archived", "deprecated"},
    "archived": {"exported", "deprecated"},
    "exported": {"deprecated"},
    "deprecated": {"archived"},
    "rejected": {"drafted"},
}

REQUIRED_APPROVALS_FOR_APPROVED = {"formal_methods", "domain_expert"}
REQUIRED_APPROVALS_FOR_EXPORT = {"formal_methods", "domain_expert", "release_owner"}


@dataclass
class ProofReview:
    reviewer: str
    role: str
    decision: str  # approve | reject | request_changes
    notes: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProofValidationAttachment:
    kind: str  # security | lean | shadowhott | regression
    status: str
    lean_status: str | None = None
    certificate_hash: str | None = None
    report_path: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProofArtifactEntry:
    artifact_id: str
    theorem_name: str
    theorem_fingerprint: dict[str, Any]
    draft_path: str | None
    lean_code_hash: str
    state: str
    created_at: float
    updated_at: float
    history: list[dict[str, Any]] = field(default_factory=list)
    validation_attachments: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    archived_path: str | None = None
    exported_path: str | None = None
    certificate_path: str | None = None
    review_packet_path: str | None = None


def registry_path(payload: dict[str, Any]) -> Path:
    return resolve_under_allowed_root(payload.get("registry_path"), default="proof_artifact_registry/registry.json", kind="proof registry_path")


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def submit_proof_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    lean_code = payload.get("lean_code")
    draft_path = payload.get("draft_path")
    artifact = payload.get("artifact") or {}

    if lean_code is None and draft_path:
        lean_code = resolve_under_allowed_root(draft_path, must_exist=True, kind="draft_path").read_text(encoding="utf-8")
    if lean_code is None and artifact:
        lean_code = artifact.get("lean_code", "")
    lean_code = str(lean_code or "")

    theorem_fingerprint = payload.get("theorem_fingerprint") or artifact.get("theorem_fingerprint") or {}
    theorem_name = str(payload.get("theorem_name") or artifact.get("theorem_name") or theorem_fingerprint.get("theorem_name") or "unnamed_theorem")
    lean_hash = sha256_text(lean_code)
    artifact_id = str(payload.get("artifact_id") or f"{safe(theorem_name)}_{lean_hash[:12]}")

    rpath = registry_path(payload)
    reg = load_registry(rpath)
    if artifact_id in reg["entries"] and not strict_bool(payload.get("replace"), False, field="replace"):
        return {
            "status": "conflict",
            "message": f"Proof artifact {artifact_id} already exists. Use replace=true to overwrite draft metadata.",
            "artifact_id": artifact_id,
            "registry_path": str(rpath),
        }

    now = time.time()
    entry = ProofArtifactEntry(
        artifact_id=artifact_id,
        theorem_name=theorem_name,
        theorem_fingerprint=theorem_fingerprint,
        draft_path=draft_path,
        lean_code_hash=lean_hash,
        state="drafted",
        created_at=now,
        updated_at=now,
        history=[event("submit", "drafted", payload.get("actor", "unknown"), f"Submitted proof artifact {artifact_id}")],
    )

    artifact_dir = resolve_under_allowed_root(payload.get("artifact_dir"), default="proof_artifact_registry/artifacts", kind="artifact_dir")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    lean_path = artifact_dir / f"{artifact_id}.lean"
    lean_path.write_text(lean_code, encoding="utf-8")
    entry.draft_path = str(lean_path)

    reg["entries"][artifact_id] = asdict(entry)
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "entry": reg["entries"][artifact_id]}


def proof_artifact_status(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    artifact_id = resolve_artifact_id(payload, reg)
    if artifact_id not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "artifact_id": artifact_id}
    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "entry": reg["entries"][artifact_id]}


def proof_artifact_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    return {
        "status": "ok",
        "registry_path": str(rpath),
        "entry_count": len(reg.get("entries", {})),
        "registry": reg,
    }


def attach_proof_validation(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    artifact_id = resolve_artifact_id(payload, reg)
    if artifact_id not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "artifact_id": artifact_id}

    report = payload.get("report") or {}
    if payload.get("report_path"):
        report = json.loads(resolve_under_allowed_root(payload["report_path"], must_exist=True, kind="report_path").read_text(encoding="utf-8"))

    certificate_hash = None
    if report.get("certificate"):
        certificate_hash = sha256_text(json.dumps(report["certificate"], sort_keys=True, default=str))
    elif payload.get("certificate_path"):
        p = resolve_under_allowed_root(payload["certificate_path"], must_exist=True, kind="certificate_path")
        certificate_hash = sha256_text(p.read_text(encoding="utf-8"))

    attachment = ProofValidationAttachment(
        kind=str(payload.get("kind", report.get("kind", "lean"))),
        status=str(payload.get("status", report.get("status", "unknown"))),
        lean_status=payload.get("lean_status", report.get("lean_status")),
        certificate_hash=certificate_hash,
        report_path=payload.get("report_path"),
        summary=summarize_report(report),
    )

    entry = reg["entries"][artifact_id]
    entry.setdefault("validation_attachments", []).append(asdict(attachment))
    entry.setdefault("history", []).append(event("attach_validation", entry["state"], payload.get("actor", "unknown"), f"Attached {attachment.kind} validation: {attachment.status}"))
    entry["updated_at"] = time.time()
    reg["entries"][artifact_id] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "entry": entry}


def promote_proof_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    artifact_id = resolve_artifact_id(payload, reg)
    target = str(payload["target_state"])
    actor = str(payload.get("actor", "unknown"))
    note = str(payload.get("note", ""))

    if artifact_id not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "artifact_id": artifact_id}
    entry = reg["entries"][artifact_id]
    current = entry["state"]

    if target not in PROOF_STATES:
        return {"status": "rejected", "reason": f"Unknown proof state {target}", "allowed_states": PROOF_STATES}
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        return {
            "status": "rejected",
            "reason": f"Illegal transition {current} -> {target}",
            "allowed_transitions": sorted(ALLOWED_TRANSITIONS.get(current, set())),
            "entry": entry,
        }

    gate = transition_gate(entry, target, payload)
    if gate["status"] != "ok":
        return {"status": "blocked", "gate": gate, "entry": entry}

    if target == "archived":
        archive_dir = resolve_under_allowed_root(payload.get("archive_dir"), default="proof_artifact_registry/archive", kind="archive_dir")
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{artifact_id}.json"
        archive_payload = {
            "entry": entry,
            "lean_code": resolve_under_allowed_root(entry["draft_path"], kind="registered draft_path").read_text(encoding="utf-8") if entry.get("draft_path") and resolve_under_allowed_root(entry["draft_path"], kind="registered draft_path").exists() else None,
        }
        archive_path.write_text(json.dumps(archive_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        entry["archived_path"] = str(archive_path)

    if target == "exported":
        export_dir = resolve_under_allowed_root(payload.get("export_dir"), default="exported_lean", kind="export_dir")
        export_dir.mkdir(parents=True, exist_ok=True)
        source = resolve_under_allowed_root(entry["draft_path"], kind="registered draft_path")
        export_path = export_dir / f"{safe(entry['theorem_name'])}.lean"
        if source.exists():
            shutil.copy2(source, export_path)
        else:
            export_path.write_text("-- missing original Lean code\n", encoding="utf-8")
        entry["exported_path"] = str(export_path)

    entry["state"] = target
    entry["updated_at"] = time.time()
    entry.setdefault("history", []).append(event("promote", target, actor, note or f"{current} -> {target}"))
    reg["entries"][artifact_id] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "entry": entry}


def transition_gate(entry: dict[str, Any], target: str, payload: dict[str, Any]) -> dict[str, Any]:
    attachments = entry.get("validation_attachments", [])

    if target == "security_checked":
        ok = any(a.get("kind") == "security" and a.get("status") in {"ok", "accepted"} for a in attachments)
        if not ok and not strict_bool(payload.get("allow_missing_security"), False, field="allow_missing_security"):
            return {"status": "failed", "reason": "missing successful security validation attachment"}
        return {"status": "ok"}

    if target == "lean_checked":
        ok = any(a.get("kind") == "lean" and a.get("status") in {"ok", "accepted"} and a.get("lean_status") == "accepted" for a in attachments)
        if not ok and not strict_bool(payload.get("allow_unchecked_lean"), False, field="allow_unchecked_lean"):
            return {"status": "failed", "reason": "missing successful Lean acceptance attachment"}
        return {"status": "ok"}

    if target == "shadowhott_audited":
        ok = any(a.get("kind") == "shadowhott" and a.get("status") in {"ok", "accepted"} for a in attachments)
        if not ok and not strict_bool(payload.get("allow_missing_shadowhott"), False, field="allow_missing_shadowhott"):
            return {"status": "failed", "reason": "missing successful ShadowHoTT audit attachment"}
        return {"status": "ok"}

    if target == "review_ready":
        needed = ["security", "lean", "shadowhott"]
        missing = [k for k in needed if not any(a.get("kind") == k and a.get("status") in {"ok", "accepted"} for a in attachments)]
        if missing and not strict_bool(payload.get("allow_incomplete_review_ready"), False, field="allow_incomplete_review_ready"):
            return {"status": "failed", "reason": "missing validation attachments for review_ready", "missing": missing}
        return {"status": "ok"}

    if target == "approved":
        roles = approving_roles(entry)
        missing = sorted(REQUIRED_APPROVALS_FOR_APPROVED - roles)
        if missing:
            return {"status": "failed", "reason": "missing approvals for proof approval", "missing_roles": missing}
        return {"status": "ok"}

    if target == "archived":
        if entry.get("state") != "approved":
            return {"status": "failed", "reason": "only approved artifacts can be archived"}
        return {"status": "ok"}

    if target == "exported":
        roles = approving_roles(entry)
        missing = sorted(REQUIRED_APPROVALS_FOR_EXPORT - roles)
        if missing and not strict_bool(payload.get("allow_missing_release_owner"), False, field="allow_missing_release_owner"):
            return {"status": "failed", "reason": "missing approvals for export", "missing_roles": missing}
        if not entry.get("archived_path"):
            return {"status": "failed", "reason": "artifact must be archived before export"}
        return {"status": "ok"}

    return {"status": "ok"}


def record_proof_review(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    artifact_id = resolve_artifact_id(payload, reg)
    if artifact_id not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "artifact_id": artifact_id}

    review = ProofReview(
        reviewer=str(payload.get("reviewer", payload.get("actor", "unknown"))),
        role=str(payload["role"]),
        decision=str(payload.get("decision", "approve")),
        notes=str(payload.get("notes", "")),
    )
    entry = reg["entries"][artifact_id]
    entry.setdefault("reviews", []).append(asdict(review))
    entry.setdefault("history", []).append(event("review", entry["state"], review.reviewer, f"{review.role}: {review.decision}"))
    entry["updated_at"] = time.time()
    reg["entries"][artifact_id] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "entry": entry}


def create_proof_review_packet(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    artifact_id = resolve_artifact_id(payload, reg)
    if artifact_id not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "artifact_id": artifact_id}

    entry = reg["entries"][artifact_id]
    out_dir = resolve_under_allowed_root(payload.get("review_packet_dir"), default="proof_artifact_registry/review_packets", kind="review_packet_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{artifact_id}.review.json"
    md_path = out_dir / f"{artifact_id}.review.md"

    lean_code = ""
    if entry.get("draft_path") and resolve_under_allowed_root(entry["draft_path"], kind="registered draft_path").exists():
        lean_code = resolve_under_allowed_root(entry["draft_path"], kind="registered draft_path").read_text(encoding="utf-8")

    packet = {
        "artifact_id": artifact_id,
        "theorem_name": entry.get("theorem_name"),
        "state": entry.get("state"),
        "theorem_fingerprint": entry.get("theorem_fingerprint"),
        "lean_code_hash": entry.get("lean_code_hash"),
        "lean_code": lean_code,
        "validation_attachments": entry.get("validation_attachments", []),
        "reviews": entry.get("reviews", []),
        "history": entry.get("history", []),
        "created_at": time.time(),
    }
    json_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_review_markdown(packet), encoding="utf-8")

    entry["review_packet_path"] = str(json_path)
    entry.setdefault("history", []).append(event("review_packet", entry["state"], payload.get("actor", "unknown"), "Created proof review packet."))
    entry["updated_at"] = time.time()
    reg["entries"][artifact_id] = entry
    save_registry(rpath, reg)

    return {"status": "ok", "registry_path": str(rpath), "artifact_id": artifact_id, "json_path": str(json_path), "markdown_path": str(md_path), "packet": packet}


def proof_artifact_export(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["target_state"] = "exported"
    return promote_proof_artifact(payload)


def approving_roles(entry: dict[str, Any]) -> set[str]:
    roles = set()
    for r in entry.get("reviews", []):
        if r.get("decision") == "approve":
            roles.add(str(r.get("role")))
    return roles


def resolve_artifact_id(payload: dict[str, Any], registry: dict[str, Any]) -> str:
    if payload.get("artifact_id"):
        return str(payload["artifact_id"])
    entries = registry.get("entries", {})
    if len(entries) == 1:
        return next(iter(entries.keys()))
    raise ValueError("Provide `artifact_id`.")


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "status", "lean_status", "verdict", "certificate_status",
        "false_theorem_drift_escape_count", "failed_count", "pass_rate",
    ]
    out = {k: report.get(k) for k in keys if k in report}
    if "shadowhott_state" in report:
        sh = report["shadowhott_state"]
        out["shadowhott_verdict"] = sh.get("verdict")
        out["shadowhott_valuation"] = sh.get("global_valuation") or sh.get("valuation")
    return out


def render_review_markdown(packet: dict[str, Any]) -> str:
    lines = []
    lines.append(f"# Proof Artifact Review: {packet['artifact_id']}")
    lines.append("")
    lines.append(f"Theorem: `{packet.get('theorem_name')}`")
    lines.append(f"State: `{packet.get('state')}`")
    lines.append("")
    lines.append("## Theorem fingerprint")
    lines.append("```json")
    lines.append(json.dumps(packet.get("theorem_fingerprint", {}), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Validation attachments")
    lines.append("```json")
    lines.append(json.dumps(packet.get("validation_attachments", []), indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    lines.append("")
    lines.append("## Lean code")
    lines.append("```lean")
    lines.append(packet.get("lean_code", ""))
    lines.append("```")
    return "\n".join(lines) + "\n"


def event(kind: str, state: str, actor: str, note: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "state": state,
        "actor": str(actor),
        "note": note,
        "timestamp": time.time(),
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:180]
