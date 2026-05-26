from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bilattice import BilatticeValue, TOP_L, BOTTOM_L, BOTH_L, NEITHER_L
from .models import Diagnostic, LeanDraft, LeanRunResult, Patch, PatchKind
from .shadowhott import PatchMorphism, build_shadowhott_state, check_J_conservation


@dataclass(frozen=True)
class PatchCandidateAssessment:
    patch: Patch
    morphism: PatchMorphism
    conservation_status: str
    score: tuple[int, int, int, int, int]
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_kind": str(self.patch.kind.value if hasattr(self.patch.kind, "value") else self.patch.kind),
            "description": self.patch.description,
            "morphism": self.morphism.to_dict(),
            "conservation_status": self.conservation_status,
            "score": list(self.score),
            "selected": self.selected,
        }


LABEL_RANK = {
    TOP_L: 4,
    NEITHER_L: 3,
    BOTH_L: 2,
    BOTTOM_L: 1,
}

PATCH_KIND_RANK = {
    "replace_tactic": 4,
    "add_local_lemma": 3,
    "add_import": 3,
    "request_llm_rewrite_with_retrieval": 2,
    "request_llm_rewrite": 1,
    "no_patch": 0,
    "reject_drift": 0,
}


def choose_patch_by_bilattice(
    draft: LeanDraft,
    lean_result: LeanRunResult,
    candidates: list[Patch],
    *,
    status: str = "needs_repair",
) -> tuple[Patch, list[PatchCandidateAssessment]]:
    """Choose a repair candidate by its ShadowHoTT patch-morphism evidence.

    This is deliberately conservative: a repair patch does not get to claim
    ⊤_L merely because it changes code.  It remains n_L until Lean supplies
    classical acceptance.  The chooser filters theorem-drift and failed
    No-Glutty-J candidates before using ordinary deterministic order.
    """
    if not candidates:
        raise ValueError("choose_patch_by_bilattice requires at least one candidate")

    before = build_shadowhott_state({
        "status": status,
        "lean_status": lean_status_value(lean_result),
        "theorem_fingerprint": draft.fingerprint,
        "proof_graph": draft.proof_graph,
        "diagnostics": lean_result.diagnostics,
        "final_lean_code": draft.code,
    })

    assessments: list[PatchCandidateAssessment] = []
    for idx, patch in enumerate(candidates):
        kind = patch_kind_value(patch)
        target_code = patch.new_code or draft.code
        drift = draft.fingerprint.diff_summary(target_code)
        has_hard_patch_diagnostic = any(diagnostic_kind(d) in {"theorem_drift", "axiom_leak", "sorry_leak", "security_rejection"} for d in patch.diagnostics)
        fingerprint_preserved = not drift
        theorem_safe = (
            fingerprint_preserved
            and not has_hard_patch_diagnostic
            and kind not in {"reject_drift", "no_patch"}
        )
        target_label = semantic_target_label(patch, theorem_safe)
        morphism = PatchMorphism(
            id=f"mu_candidate_{idx+1}",
            kind=kind,
            source_state=before.state_id,
            target_state=f"{before.state_id}_candidate_{idx+1}" if theorem_safe else None,
            theorem_safe=theorem_safe,
            fingerprint_preserved=fingerprint_preserved,
            description=f"Bilattice-scored candidate: {patch.description}",
            obstruction_ids=[o.id for o in before.obstructions],
            permitted_delta=permitted_delta_for_kind(kind),
            source_label=before.global_label,
            target_label=target_label,
            conservation_checked=before.global_label.nonreal,
            conservation_ok=None,
        )
        after = build_shadowhott_state({
            "status": status,
            "lean_status": lean_status_value(lean_result),
            "theorem_fingerprint": draft.fingerprint,
            "proof_graph": draft.proof_graph,
            "diagnostics": list(lean_result.diagnostics) + list(patch.diagnostics) + list(drift),
            "patches": [patch],
            "final_lean_code": target_code,
        })
        report = check_J_conservation(before, after, morphism)
        if report.status == "ok":
            morphism.conservation_ok = True
        elif report.status == "violation":
            morphism.conservation_ok = False
            morphism.theorem_safe = False
        else:
            morphism.conservation_ok = None
        conservation_good = 0 if report.status == "violation" else 1
        has_code = 1 if patch.new_code else 0
        score = (
            conservation_good,
            1 if morphism.theorem_safe else 0,
            LABEL_RANK.get(morphism.target_label, 0),
            has_code,
            PATCH_KIND_RANK.get(kind, 0),
            -idx,
        )
        assessments.append(PatchCandidateAssessment(patch, morphism, report.status, score))

    best = max(assessments, key=lambda a: a.score)
    marked = [PatchCandidateAssessment(a.patch, a.morphism, a.conservation_status, a.score, selected=(a is best)) for a in assessments]
    selected = best.patch
    selected.description = selected.description + f" [bilattice-selected: target={best.morphism.target_label.pretty}, conservation={best.conservation_status}]"
    return selected, marked


def semantic_target_label(patch: Patch, theorem_safe: bool) -> BilatticeValue:
    kind = patch_kind_value(patch)
    if kind in {"reject_drift", "no_patch"}:
        return BOTTOM_L
    if not theorem_safe:
        return BOTTOM_L
    # A repair candidate changes the proof state but cannot be classical until
    # Lean checks it; it is therefore a gap-preserving morphism.
    return NEITHER_L


def patch_kind_value(patch: Patch) -> str:
    return str(patch.kind.value if hasattr(patch.kind, "value") else patch.kind)


def diagnostic_kind(d: Diagnostic | Any) -> str:
    if isinstance(d, Diagnostic):
        k = d.kind
        return str(k.value if hasattr(k, "value") else k)
    if isinstance(d, dict):
        return str(d.get("kind", ""))
    return ""


def lean_status_value(result: LeanRunResult) -> str:
    s = result.lean_status
    return str(s.value if hasattr(s, "value") else s)


def permitted_delta_for_kind(kind: str) -> list[str]:
    mapping = {
        "replace_tactic": ["proof_body"],
        "add_import": ["allowed_imports"],
        "add_local_lemma": ["local_lemmas", "proof_body"],
        "request_llm_rewrite": ["proof_body", "proof_graph_boundary_notes"],
        "request_llm_rewrite_with_retrieval": ["proof_body", "allowed_imports", "local_lemmas", "proof_graph_boundary_notes"],
        "reject_drift": [],
        "no_patch": [],
    }
    return mapping.get(kind, ["proof_body"])
