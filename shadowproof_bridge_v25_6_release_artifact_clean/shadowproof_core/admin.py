from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import ShadowProofConfig
from .observability import metrics_report
from .storage import tenant_dir


def tenant_report(payload: dict[str, Any], cfg: ShadowProofConfig) -> dict[str, Any]:
    tenant_id = str(payload.get("tenant_id", cfg.default_tenant_id))
    base = tenant_dir(cfg, tenant_id)
    files = []
    total_bytes = 0
    for p in base.rglob("*"):
        if p.is_file():
            size = p.stat().st_size
            total_bytes += size
            files.append({"path": str(p), "bytes": size, "modified": p.stat().st_mtime})
    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files[-100:],
        "metrics": metrics_report(cfg, limit=10000),
    }


def delete_tenant_data(payload: dict[str, Any], cfg: ShadowProofConfig) -> dict[str, Any]:
    tenant_id = str(payload.get("tenant_id", cfg.default_tenant_id))
    confirm = payload.get("confirm") == f"delete:{tenant_id}"
    if not confirm:
        return {
            "status": "confirmation_required",
            "tenant_id": tenant_id,
            "required_confirm": f"delete:{tenant_id}",
        }
    base = tenant_dir(cfg, tenant_id)
    removed = 0
    for p in sorted(base.rglob("*"), reverse=True):
        if p.is_file():
            p.unlink()
            removed += 1
        elif p.is_dir():
            try:
                p.rmdir()
            except Exception:
                pass
    return {"status": "ok", "tenant_id": tenant_id, "removed_files": removed}
