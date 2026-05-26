from __future__ import annotations

from typing import Any

from .bilattice import BilatticeValue, NEITHER_L
from .shadowhott import (
    ConservationReport,
    PatchMorphism,
    ShadowHoTTState,
    build_shadowhott_state,
    check_J_conservation,
)


def check_conservation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convenience wrapper for JSON/tool callers."""
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    morphism_raw = payload.get("morphism") or {}
    before_state = before if isinstance(before, ShadowHoTTState) else build_shadowhott_state(before)
    after_state = after if isinstance(after, ShadowHoTTState) else build_shadowhott_state(after)
    morphism = morphism_raw if isinstance(morphism_raw, PatchMorphism) else PatchMorphism(
        id=str(morphism_raw.get("id", "mu")),
        kind=str(morphism_raw.get("kind", "unknown")),
        source_state=str(morphism_raw.get("source_state", "S")),
        target_state=morphism_raw.get("target_state", "S_prime"),
        theorem_safe=bool(morphism_raw.get("theorem_safe", False)),
        fingerprint_preserved=bool(morphism_raw.get("fingerprint_preserved", False)),
        description=str(morphism_raw.get("description", "payload morphism")),
        obstruction_ids=list(morphism_raw.get("obstruction_ids", [])),
        permitted_delta=list(morphism_raw.get("permitted_delta", [])),
        source_label=BilatticeValue.from_label(morphism_raw.get("source_label", NEITHER_L)),
        target_label=BilatticeValue.from_label(morphism_raw.get("target_label", NEITHER_L)),
        conservation_checked=bool(morphism_raw.get("conservation_checked", False)),
        conservation_ok=morphism_raw.get("conservation_ok"),
    )
    return check_J_conservation(before_state, after_state, morphism).to_dict()
