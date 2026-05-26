from __future__ import annotations

import difflib
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .config import ShadowProofConfig


def create_review_packet(payload: dict[str, Any], cfg: ShadowProofConfig) -> dict[str, Any]:
    packet_id = payload.get("packet_id") or "review_" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]

    before = str(payload.get("before_lean_code", ""))
    after = str(payload.get("after_lean_code", payload.get("final_lean_code", "")))
    fingerprint = payload.get("theorem_fingerprint", {})
    diagnostics = payload.get("diagnostics", [])
    certificate = payload.get("certificate", payload.get("validation_certificate"))
    shadowhott_state = payload.get("shadowhott_state")
    repair_prompt = payload.get("compiled_repair_prompt") or payload.get("prompt")

    diff = "\n".join(difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="before.lean",
        tofile="after.lean",
        lineterm="",
    ))

    packet = {
        "packet_id": packet_id,
        "created_at": time.time(),
        "theorem_fingerprint": fingerprint,
        "diagnostics": diagnostics,
        "certificate": certificate,
        "shadowhott_state": shadowhott_state,
        "repair_prompt": repair_prompt,
        "lean_diff": diff,
        "review_status": "pending",
        "review_notes": [],
    }

    out_dir = Path(cfg.review_packet_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{packet_id}.json"
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = out_dir / f"{packet_id}.md"
    md_path.write_text(render_review_markdown(packet), encoding="utf-8")

    return {"status": "ok", "packet_id": packet_id, "json_path": str(path), "markdown_path": str(md_path), "packet": packet}


def render_review_markdown(packet: dict[str, Any]) -> str:
    parts = []
    parts.append(f"# ShadowProof Review Packet: {packet['packet_id']}")
    parts.append("")
    parts.append("## Theorem fingerprint")
    parts.append("```json")
    parts.append(json.dumps(packet.get("theorem_fingerprint", {}), indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("## Diagnostics")
    parts.append("```json")
    parts.append(json.dumps(packet.get("diagnostics", []), indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")
    parts.append("## Lean diff")
    parts.append("```diff")
    parts.append(packet.get("lean_diff", ""))
    parts.append("```")
    parts.append("")
    if packet.get("certificate"):
        parts.append("## Certificate")
        parts.append("```json")
        parts.append(json.dumps(packet["certificate"], indent=2, ensure_ascii=False, default=str))
        parts.append("```")
    if packet.get("shadowhott_state"):
        parts.append("## ShadowHoTT state")
        parts.append("```json")
        parts.append(json.dumps(packet["shadowhott_state"], indent=2, ensure_ascii=False, default=str))
        parts.append("```")
    return "\n".join(parts) + "\n"
