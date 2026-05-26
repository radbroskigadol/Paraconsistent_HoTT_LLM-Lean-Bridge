from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .domain_authoring import validate_domain_pack
from .path_guard import resolve_under_allowed_root
from .schema_validation import strict_bool


PROMOTION_STATES = [
    "draft",
    "linted",
    "eval_tested",
    "expert_reviewed",
    "approved",
    "active",
    "deprecated",
    "rejected",
]

ALLOWED_TRANSITIONS = {
    "draft": {"linted", "rejected"},
    "linted": {"eval_tested", "rejected"},
    "eval_tested": {"expert_reviewed", "rejected"},
    "expert_reviewed": {"approved", "rejected"},
    "approved": {"active", "deprecated", "rejected"},
    "active": {"deprecated"},
    "deprecated": {"active"},
    "rejected": {"draft"},
}

REQUIRED_APPROVALS_FOR_APPROVED = {
    "domain_expert",
    "formal_methods",
}

REQUIRED_APPROVALS_FOR_ACTIVE = {
    "domain_expert",
    "formal_methods",
    "release_owner",
}


@dataclass
class DomainPackReview:
    reviewer: str
    role: str
    decision: str  # approve | reject | request_changes
    notes: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class DomainPackEvalAttachment:
    suite_id: str
    pass_rate: float | None
    false_theorem_drift_escape_count: int
    failed_count: int
    report_path: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class DomainPackRegistryEntry:
    domain: str
    version: str
    pack_hash: str
    pack_path: str
    state: str
    created_at: float
    updated_at: float
    history: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    eval_attachments: list[dict[str, Any]] = field(default_factory=list)
    active_path: str | None = None
    previous_active_path: str | None = None


def registry_path(payload: dict[str, Any]) -> Path:
    return resolve_under_allowed_root(payload.get("registry_path"), default="domain_pack_registry/registry.json", kind="domain registry_path")


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "entries": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def pack_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack_identity(pack: dict[str, Any], path: Path) -> tuple[str, str]:
    domain = str(pack.get("domain") or path.stem)
    version = str(pack.get("version") or "0.0.0")
    return domain, version


def entry_key(domain: str, version: str) -> str:
    return f"{domain}@{version}"


def submit_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    path = resolve_under_allowed_root(payload["path"], must_exist=True, kind="domain pack path")
    pack = json.loads(path.read_text(encoding="utf-8"))
    domain, version = pack_identity(pack, path)
    key = entry_key(domain, version)
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    now = time.time()

    if key in reg["entries"] and not strict_bool(payload.get("replace"), False, field="replace"):
        return {
            "status": "conflict",
            "message": f"Domain pack {key} already exists. Use replace=true to overwrite draft metadata.",
            "registry_path": str(rpath),
            "key": key,
        }

    h = pack_hash(path)
    entry = DomainPackRegistryEntry(
        domain=domain,
        version=version,
        pack_hash=h,
        pack_path=str(path),
        state="draft",
        created_at=now,
        updated_at=now,
        history=[event("submit", "draft", payload.get("actor", "unknown"), f"Submitted {key}")],
    )
    reg["entries"][key] = asdict(entry)
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": reg["entries"][key]}


def domain_pack_status(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    key = resolve_key(payload, reg)
    if key not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "key": key}
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": reg["entries"][key]}


def domain_pack_registry(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    return {
        "status": "ok",
        "registry_path": str(rpath),
        "entry_count": len(reg.get("entries", {})),
        "registry": reg,
    }


def promote_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    key = resolve_key(payload, reg)
    target = str(payload["target_state"])
    actor = str(payload.get("actor", "unknown"))
    note = str(payload.get("note", ""))

    if key not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "key": key}
    entry = reg["entries"][key]
    current = entry["state"]

    if target not in PROMOTION_STATES:
        return {"status": "rejected", "reason": f"Unknown target state {target}", "allowed_states": PROMOTION_STATES}
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

    if target == "active":
        active_dir = resolve_under_allowed_root(payload.get("active_dir"), default="domains/active", kind="active_dir")
        active_dir.mkdir(parents=True, exist_ok=True)
        source = resolve_under_allowed_root(entry["pack_path"], must_exist=True, kind="registered domain pack")
        active_path = active_dir / f"{entry['domain']}.json"
        if active_path.exists():
            backup_dir = resolve_under_allowed_root(payload.get("backup_dir"), default="domain_pack_registry/backups", kind="backup_dir")
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{entry['domain']}_{int(time.time())}.json"
            shutil.copy2(active_path, backup_path)
            entry["previous_active_path"] = str(backup_path)
        shutil.copy2(source, active_path)
        entry["active_path"] = str(active_path)

    entry["state"] = target
    entry["updated_at"] = time.time()
    entry.setdefault("history", []).append(event("promote", target, actor, note or f"{current} -> {target}"))
    reg["entries"][key] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": entry}


def transition_gate(entry: dict[str, Any], target: str, payload: dict[str, Any]) -> dict[str, Any]:
    if target == "linted":
        validation = validate_domain_pack({"path": entry["pack_path"]})
        if validation["status"] != "ok":
            return {"status": "failed", "reason": "domain pack lint errors", "validation": validation}
        return {"status": "ok", "validation": validation}

    if target == "eval_tested":
        evals = entry.get("eval_attachments", [])
        if not evals and not strict_bool(payload.get("allow_missing_eval"), False, field="allow_missing_eval"):
            return {"status": "failed", "reason": "no eval attachment; attach eval report first or allow_missing_eval=true"}
        if evals:
            latest = evals[-1]
            if latest.get("failed_count", 1) > 0:
                return {"status": "failed", "reason": "latest eval attachment has failures", "latest_eval": latest}
            if latest.get("false_theorem_drift_escape_count", 0) > 0:
                return {"status": "failed", "reason": "theorem-drift escape detected", "latest_eval": latest}
        return {"status": "ok"}

    if target == "expert_reviewed":
        roles = approving_roles(entry)
        missing = sorted(REQUIRED_APPROVALS_FOR_APPROVED - roles)
        if missing:
            return {"status": "failed", "reason": "missing required expert approvals", "missing_roles": missing}
        return {"status": "ok"}

    if target == "approved":
        roles = approving_roles(entry)
        missing = sorted(REQUIRED_APPROVALS_FOR_APPROVED - roles)
        if missing:
            return {"status": "failed", "reason": "missing approvals for approval", "missing_roles": missing}
        return {"status": "ok"}

    if target == "active":
        roles = approving_roles(entry)
        missing = sorted(REQUIRED_APPROVALS_FOR_ACTIVE - roles)
        if missing and not strict_bool(payload.get("allow_missing_release_owner"), False, field="allow_missing_release_owner"):
            return {"status": "failed", "reason": "missing approvals for activation", "missing_roles": missing}
        if not resolve_under_allowed_root(entry["pack_path"], kind="registered domain pack").exists():
            return {"status": "failed", "reason": "pack path missing", "pack_path": entry["pack_path"]}
        return {"status": "ok"}

    return {"status": "ok"}


def record_domain_pack_review(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    key = resolve_key(payload, reg)
    if key not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "key": key}

    review = DomainPackReview(
        reviewer=str(payload.get("reviewer", payload.get("actor", "unknown"))),
        role=str(payload["role"]),
        decision=str(payload.get("decision", "approve")),
        notes=str(payload.get("notes", "")),
    )
    entry = reg["entries"][key]
    entry.setdefault("reviews", []).append(asdict(review))
    entry.setdefault("history", []).append(event("review", entry["state"], review.reviewer, f"{review.role}: {review.decision}"))
    entry["updated_at"] = time.time()
    reg["entries"][key] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": entry}


def attach_domain_pack_eval(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    key = resolve_key(payload, reg)
    if key not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "key": key}

    report = payload.get("report") or {}
    if payload.get("report_path"):
        report = json.loads(resolve_under_allowed_root(payload["report_path"], must_exist=True, kind="eval report_path").read_text(encoding="utf-8"))

    metrics = report.get("metrics", report)
    attachment = DomainPackEvalAttachment(
        suite_id=str(report.get("suite_id", metrics.get("suite_id", payload.get("suite_id", "unknown_suite")))),
        pass_rate=metrics.get("pass_rate"),
        false_theorem_drift_escape_count=int(metrics.get("false_theorem_drift_escape_count", metrics.get("false_theorem_drift_escape_count", 0)) or 0),
        failed_count=int(metrics.get("failed_count", 0) or 0),
        report_path=payload.get("report_path"),
    )
    entry = reg["entries"][key]
    entry.setdefault("eval_attachments", []).append(asdict(attachment))
    entry.setdefault("history", []).append(event("eval_attach", entry["state"], payload.get("actor", "unknown"), f"Attached eval {attachment.suite_id}"))
    entry["updated_at"] = time.time()
    reg["entries"][key] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": entry}


def rollback_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    rpath = registry_path(payload)
    reg = load_registry(rpath)
    key = resolve_key(payload, reg)
    if key not in reg["entries"]:
        return {"status": "not_found", "registry_path": str(rpath), "key": key}

    entry = reg["entries"][key]
    active_path = entry.get("active_path")
    previous = entry.get("previous_active_path")
    if not active_path or not previous or not Path(previous).exists():
        return {"status": "blocked", "reason": "no previous active backup available", "entry": entry}

    shutil.copy2(previous, active_path)
    entry["state"] = "deprecated"
    entry["updated_at"] = time.time()
    entry.setdefault("history", []).append(event("rollback", "deprecated", payload.get("actor", "unknown"), "Rolled back active pack from backup."))
    reg["entries"][key] = entry
    save_registry(rpath, reg)
    return {"status": "ok", "registry_path": str(rpath), "key": key, "entry": entry}


def approving_roles(entry: dict[str, Any]) -> set[str]:
    roles = set()
    for r in entry.get("reviews", []):
        if r.get("decision") == "approve":
            roles.add(str(r.get("role")))
    return roles


def resolve_key(payload: dict[str, Any], registry: dict[str, Any]) -> str:
    if payload.get("key"):
        return str(payload["key"])
    if payload.get("domain") and payload.get("version"):
        return entry_key(str(payload["domain"]), str(payload["version"]))
    entries = registry.get("entries", {})
    if len(entries) == 1:
        return next(iter(entries.keys()))
    raise ValueError("Provide `key`, or `domain` + `version`.")


def event(kind: str, state: str, actor: str, note: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "state": state,
        "actor": str(actor),
        "note": note,
        "timestamp": time.time(),
    }
