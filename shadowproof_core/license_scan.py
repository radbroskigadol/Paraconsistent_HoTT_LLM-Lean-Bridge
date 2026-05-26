from __future__ import annotations

import re
from pathlib import Path

from .path_guard import resolve_under_allowed_root
from typing import Any


LICENSE_PATTERNS = {
    "MIT": r"MIT License",
    "Apache-2.0": r"Apache License",
    "BSD": r"BSD License|Redistribution and use in source and binary forms",
    "GPL": r"GNU GENERAL PUBLIC LICENSE",
    "LGPL": r"GNU LESSER GENERAL PUBLIC LICENSE",
}


def license_scan(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    root = resolve_under_allowed_root(payload.get("root"), default=".", must_exist=True, kind="license scan root")
    max_files = int(payload.get("max_files", 2000))
    findings = []
    scanned = 0

    for p in root.rglob("*"):
        if scanned >= max_files:
            break
        if not p.is_file():
            continue
        rel = str(p).replace("\\", "/")
        if rel.endswith("shadowproof_core/license_scan.py") or "/__pycache__/" in rel:
            continue
        if p.name.lower() in {"license", "copying", "copying.txt", "license.txt"} or p.name.lower() in {"pyproject.toml", "package.json", "package-lock.json"} or p.suffix.lower() in {".md", ".toml"}:
            scanned += 1
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:20000]
            except Exception:
                continue
            for name, pat in LICENSE_PATTERNS.items():
                if re.search(pat, text, flags=re.I):
                    findings.append({"file": str(p), "license_hint": name})

    return {
        "status": "ok",
        "scanned_files": scanned,
        "findings": findings,
        "notes": [
            "This is a scaffold, not a legal opinion.",
            "Production release should use a real SBOM/license scanner and legal review.",
        ],
    }
