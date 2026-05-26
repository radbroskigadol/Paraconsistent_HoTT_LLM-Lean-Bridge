from __future__ import annotations

from typing import Any

from .product import product_readiness_report
from .threat_model import threat_model_report
from .license_scan import license_scan
from .config import ShadowProofConfig


def release_gate(payload: dict[str, Any], cfg: ShadowProofConfig) -> dict[str, Any]:
    readiness = product_readiness_report(cfg)
    threats = threat_model_report(payload)
    licenses = license_scan({"root": payload.get("root", "."), "max_files": payload.get("max_files", 1000)})

    blockers = []
    if readiness.get("status") != "production_ready":
        blockers.append("product readiness is not production_ready")
    if threats.get("release_blockers"):
        blockers.append(f"{len(threats['release_blockers'])} threat controls are not production_ready")
    if any(f.get("license_hint") in {"GPL", "LGPL"} for f in licenses.get("findings", [])):
        blockers.append("possible copyleft license findings require legal review")

    return {
        "status": "blocked" if blockers else "pass",
        "blockers": blockers,
        "readiness": readiness,
        "threat_model": threats,
        "license_scan": licenses,
        "notes": ["This gate is intentionally conservative for enterprise deployment."],
    }
