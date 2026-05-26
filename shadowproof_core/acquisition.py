from __future__ import annotations

from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

ACQUISITION_DOCS = {
    "diligence_status": "docs/acquisition/DILIGENCE_STATUS.md",
    "diligence_index": "docs/acquisition/DILIGENCE_INDEX.md",
    "executive_packet": "docs/acquisition/EXECUTIVE_ACQUISITION_PACKET.md",
    "claims_boundary": "docs/acquisition/CLAIMS_BOUNDARY.md",
    "technical_due_diligence": "docs/acquisition/TECHNICAL_DUE_DILIGENCE_CHECKLIST.md",
    "demo_playbook": "docs/acquisition/BUYER_DEMO_PLAYBOOK.md",
    "architecture": "docs/architecture/SHADOWPROOF_ARCHITECTURE.md",
    "buyer_deck_notes": "docs/acquisition/BUYER_DECK_NOTES.md",
    "day_one_package": "docs/acquisition/DAY_ONE_ACQUIRER_PACKAGE.md",
    "release_gate_positioning": "docs/acquisition/RELEASE_GATE_POSITIONING.md",
    "valuation_memo": "docs/acquisition/ONE_PAGE_VALUATION_MEMO.md",
    "valuation_assumptions": "docs/acquisition/VALUATION_ASSUMPTIONS.md",
    "roadmap": "docs/acquisition/PRE_ACQUISITION_ROADMAP.md",
    "security_questionnaire": "docs/acquisition/SECURITY_QUESTIONNAIRE_RESPONSES.md",
}


def _doc_status(path: str) -> dict[str, Any]:
    p = PACKAGE_ROOT / path
    exists = p.exists()
    return {
        "path": path,
        "exists": exists,
        "bytes": p.stat().st_size if exists else 0,
    }


def acquisition_packet(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    docs = {name: _doc_status(path) for name, path in ACQUISITION_DOCS.items()}
    missing = [name for name, status in docs.items() if not status["exists"]]
    return {
        "status": "ready" if not missing else "incomplete",
        "version": "0.25.6",
        "audience": payload.get("audience", "technical acquirer / strategic buyer"),
        "positioning": "self-hostable pilot stack and diligence-ready package for a J-conserved ShadowHoTT bridge to Lean",
        "core_claims": [
            "L = 2×2 bilattice semantics are implemented in code, not merely described.",
            "Proof paths carry bilattice labels and compose by ∧_L.",
            "Glutty BOTH states route to human review instead of silent acceptance.",
            "Theorem fingerprints and No-Glutty-J conservation checks guard against silent theorem drift.",
            "Markdown acquisition packet, valuation memo, day-one acquirer checklist, claims boundary, and diligence index are included; generated PPTX/PDF deck assets are optional collateral and may be supplied separately.",
        ],
        "docs": docs,
        "missing": missing,
        "recommended_demo_order": [
            "python -m pytest -q",
            "python -m shadowproof_core.cli shadowhott-eval examples/evals/shadowhott_eval.json",
            "python -m shadowproof_core.cli regression examples/evals/regression_suite.json",
            "bash scripts/run_buyer_demo.sh",
            "review docs/acquisition/BUYER_DECK_NOTES.md",
            "review docs/acquisition/ONE_PAGE_VALUATION_MEMO.md",
            "review docs/acquisition/DAY_ONE_ACQUIRER_PACKAGE.md",
        ],
        "not_included": [
            "external penetration test",
            "legal DPA/SLA commitments",
            "customer-specific domain packs/eval corpora",
            "customer private model adapters",
            "hosted billing/admin production service",
        ],
    }


def claims_boundary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.25.6",
        "allowed_claims": [
            "implements the operational L = 2×2 ShadowHoTT bilattice core",
            "uses bilattice labels in proof paths, certificates, repair selection, and human-review routing",
            "ships a self-hostable pilot stack with optional Postgres, Redis, ASGI, OIDC scaffold, and Prometheus/OTel hooks",
            "provides acquisition-readiness markdown documentation and buyer-demo scripts",
        ],
        "disallowed_claims_without_buyer_work": [
            "enterprise GA ready",
            "externally penetration-tested",
            "SOC 2 / ISO compliant",
            "legally complete DPA/SLA",
            "validated on a full production Mathlib-scale corpus",
            "ready for every customer domain without professional-services integration",
        ],
        "release_gate_positioning": ACQUISITION_DOCS["release_gate_positioning"],
        "see": ACQUISITION_DOCS["claims_boundary"],
    }


def due_diligence_checklist(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.25.6",
        "tracks": [
            "mathematical correctness",
            "Lean/Mathlib reproducibility",
            "sandbox and worker isolation",
            "tenant isolation and storage",
            "auth/quota readiness",
            "observability and operations",
            "release engineering",
            "security/legal/compliance",
            "buyer integration surface",
        ],
        "critical_pre_pilot_evidence": [
            "pytest/regression/ShadowHoTT eval pass",
            "Lean bilattice proof file kernel-checked in Lean-equipped CI",
            "buyer mirrors pinned worker image",
            "auth mode enabled and tenant mapping verified",
            "sandbox hostile-proof corpus run",
            "claims-boundary reviewed by buyer technical lead",
        ],
        "diligence_index": ACQUISITION_DOCS["diligence_index"],
        "day_one_package": ACQUISITION_DOCS["day_one_package"],
        "see": ACQUISITION_DOCS["technical_due_diligence"],
    }


def investor_deck_index(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    required_paths = {
        "notes": "docs/acquisition/BUYER_DECK_NOTES.md",
        "valuation_memo_md": "docs/acquisition/ONE_PAGE_VALUATION_MEMO.md",
        "day_one_package_md": "docs/acquisition/DAY_ONE_ACQUIRER_PACKAGE.md",
        "claims_boundary_md": "docs/acquisition/CLAIMS_BOUNDARY.md",
    }
    optional_paths = {
        "pptx": "assets/deck/shadowproof_bridge_v25_buyer_deck.pptx",
        "pdf": "assets/pdf/shadowproof_bridge_v25_buyer_deck.pdf",
        "valuation_memo_pdf": "assets/pdf/shadowproof_bridge_v25_one_page_valuation_memo.pdf",
        "day_one_checklist_pdf": "assets/pdf/shadowproof_bridge_v25_day_one_acquirer_checklist.pdf",
    }
    docs = {name: _doc_status(path) for name, path in required_paths.items()}
    optional = {name: _doc_status(path) for name, path in optional_paths.items()}
    missing = [name for name, status in docs.items() if not status["exists"]]
    optional_missing = [name for name, status in optional.items() if not status["exists"]]
    return {
        "status": "ready" if not missing else "incomplete",
        "version": "0.25.6",
        "audience": payload.get("audience", "strategic buyer / acquirer"),
        "positioning": "buyer-facing deck notes, valuation memo, and day-one acquirer checklist; binary deck/PDF assets are optional collateral",
        "docs": docs,
        "optional_collateral": optional,
        "missing": missing,
        "optional_missing": optional_missing,
        "recommended_use": [
            "Use BUYER_DECK_NOTES.md as the source for a first buyer conversation deck.",
            "Use the markdown valuation memo as the one-page leave-behind source.",
            "Pair the notes with scripts/run_buyer_demo.sh for live proof/glut/gap/refutation routing.",
            "Keep docs/acquisition/CLAIMS_BOUNDARY.md available for technical diligence.",
        ],
    }
