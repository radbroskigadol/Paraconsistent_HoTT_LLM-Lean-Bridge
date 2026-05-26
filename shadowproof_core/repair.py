from __future__ import annotations

from .lean_text import replace_first_by_proof_body

from .models import (
    Diagnostic,
    DiagnosticSeverity,
    LeanDraft,
    LeanRunResult,
    ObstructionKind,
    Patch,
    PatchKind,
)


class ShadowHoTTRepairEngine:
    def propose_patch(self, draft: LeanDraft, lean_result: LeanRunResult, iteration: int, allow_theorem_mutation: bool = False) -> Patch:
        """Backward-compatible single-patch API; returns the bilattice candidate front-runner."""
        return self.candidate_patches(draft, lean_result, iteration, allow_theorem_mutation)[0]

    def candidate_patches(self, draft: LeanDraft, lean_result: LeanRunResult, iteration: int, allow_theorem_mutation: bool = False) -> list[Patch]:
        """Return theorem-lock-preserving patch candidates for bilattice scoring.

        The single-patch compatibility API chooses one patch by family/iteration.
        This candidate API exposes the patch frontier so the pipeline can evaluate each
        candidate as a ShadowHoTT patch morphism before applying it.
        """
        drift_diagnostics = draft.fingerprint.diff_summary(draft.code)
        if drift_diagnostics and not allow_theorem_mutation:
            return [Patch(
                kind=PatchKind.REJECT_DRIFT,
                description="Theorem lock rejected this draft.",
                diagnostics=drift_diagnostics,
            )]

        family = draft.fingerprint.theorem_family

        if family == "group_assoc":
            return self._group_assoc_candidates(draft, iteration)

        if family == "group_left_cancel":
            return self._left_cancel_candidates(draft, iteration)

        if family == "bad_group_commutativity":
            return [Patch(
                kind=PatchKind.REJECT_DRIFT,
                description="Plain Group does not imply commutativity; adding CommGroup would mutate the theorem.",
                diagnostics=[Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.THEOREM_DRIFT,
                    message="Rejecting proof attempt: theorem is false for nonabelian groups.",
                    source="repair",
                )],
            )]

        return [Patch(
            kind=PatchKind.REQUEST_LLM_REWRITE,
            description="No deterministic patch available; request a new LLM DraftProposal constrained by current diagnostics.",
            diagnostics=[Diagnostic(
                severity=DiagnosticSeverity.WARNING,
                kind=ObstructionKind.UNSUPPORTED_NL,
                message="Unsupported theorem family.",
                source="repair",
            )],
        )]

    def _group_assoc_patch(self, draft: LeanDraft, iteration: int) -> Patch:
        return self._group_assoc_candidates(draft, iteration)[0]

    def _group_assoc_candidates(self, draft: LeanDraft, iteration: int) -> list[Patch]:
        bodies = [
            "by\n  simpa using mul_assoc a b c",
            "by\n  exact mul_assoc a b c",
            "by\n  rw [mul_assoc]",
            "by\n  group",
        ]
        start = min(iteration, len(bodies) - 1)
        return [_body_patch(draft, body, f"Try associativity candidate {i + 1}.")
                for i, body in enumerate(bodies[start:], start=start)]

    def _left_cancel_patch(self, draft: LeanDraft, iteration: int) -> Patch:
        return self._left_cancel_candidates(draft, iteration)[0]

    def _left_cancel_candidates(self, draft: LeanDraft, iteration: int) -> list[Patch]:
        bodies = [
            "by\n  exact mul_left_cancel h",
            "by\n  simpa using mul_left_cancel h",
            """by
  calc
    b = 1 * b := by simp
    _ = (a⁻¹ * a) * b := by simp
    _ = a⁻¹ * (a * b) := by rw [mul_assoc]
    _ = a⁻¹ * (a * c) := by rw [h]
    _ = (a⁻¹ * a) * c := by rw [mul_assoc]
    _ = 1 * c := by simp
    _ = c := by simp""",
            "by\n  group at h\n  exact h",
        ]
        start = min(iteration, len(bodies) - 1)
        return [_body_patch(draft, body, f"Try left-cancellation candidate {i + 1}.")
                for i, body in enumerate(bodies[start:], start=start)]


def _body_patch(draft: LeanDraft, body: str, description: str) -> Patch:
    new_code = replace_body(draft.code, body)
    if new_code is None:
        return Patch(
            kind=PatchKind.NO_PATCH,
            description=f"{description} skipped: no recognizable proof-body anchor in draft code.",
            diagnostics=[Diagnostic(
                severity=DiagnosticSeverity.WARNING,
                kind=ObstructionKind.UNKNOWN_LEAN_FAILURE,
                message="repair.replace_body found no `:= by ...` site to rewrite",
                source="repair",
            )],
        )
    return Patch(kind=PatchKind.REPLACE_TACTIC, description=description, new_code=new_code)


def replace_body(code: str, body: str) -> str | None:
    """Replace the proof body of a translator-emitted theorem.

    This uses a delimiter-aware source splitter rather than regex substitution:
    anchors inside comments or strings are ignored, ``#print axioms`` trailers
    are preserved, and following top-level declarations are not consumed.  If no
    ``:= by`` proof body is found, ``None`` is returned so the caller can record
    an honest no-patch diagnostic.
    """
    return replace_first_by_proof_body(code, body)
