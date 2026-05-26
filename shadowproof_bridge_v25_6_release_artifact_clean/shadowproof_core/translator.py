from __future__ import annotations

import re
from .bilattice import TOP_L, BOTTOM_L, BOTH_L, NEITHER_L
from .models import (
    BoundaryLane,
    FalsityLane,
    LeanDraft,
    NLProblem,
    ObstructionKind,
    ProofNode,
    ProofPath,
    TargetSpec,
    TheoremFingerprint,
    TruthLane,
)


class LLMBridgeTranslator:
    """
    This is a deterministic scaffold for an eventual LLM translator.

    In production, the LLM should emit a DraftProposal JSON object with:
      - theorem_name
      - lean_code
      - theorem_fingerprint
      - proof_graph

    This class accepts either:
      1. direct Lean code in payload["lean_code"], or
      2. a tiny controlled-NL subset for demonstration.
    """

    def translate(self, problem: NLProblem, target: TargetSpec, request_id: str = "request") -> LeanDraft:
        theorem_name = target.theorem_name or safe_theorem_name(request_id)

        raw = f"{problem.context}\n{problem.theorem}\n{problem.proof}".lower()
        imports = "\n".join(f"import {i}" for i in (target.imports or ["Mathlib"]))

        if is_group_assoc(raw):
            fingerprint = TheoremFingerprint(
                theorem_family="group_assoc",
                objects=["G : Type u", "[Group G]", "a b c : G"],
                assumptions=[],
                conclusion="(a * b) * c = a * (b * c)",
                forbidden_drift=["CommGroup", "axiom", "unsafe", "#eval", "run_cmd"],
                source_theorem=problem.theorem,
            )
            code = f"""{imports}

set_option autoImplicit false

theorem {theorem_name} {{G : Type u}} [Group G] (a b c : G) :
    (a * b) * c = a * (b * c) := by
  simpa using mul_assoc a b c

#print axioms {theorem_name}
"""
            return LeanDraft(theorem_name, code, fingerprint, [
                ProofNode(
                    id="n1",
                    source_text=problem.proof,
                    truth=TruthLane(
                        claim="Associativity of multiplication in a group establishes the equality.",
                        dependencies=["[Group G]", "a b c : G"],
                        lean_goal="(a * b) * c = a * (b * c)",
                    ),
                    falsity=FalsityLane(counterconditions=["G lacks associativity", "terms are not in G"]),
                    boundary=BoundaryLane(ambiguities=["Multiplicative notation maps to Lean's group multiplication."]),
                    paths=[
                        ProofPath.refl("group_assoc_goal", id="refl_group_assoc_goal"),
                        ProofPath(
                            id="path_mul_assoc_tactic",
                            source="group_assoc_goal",
                            target="lean_mul_assoc_witness",
                            label=TOP_L,
                            witness="simpa using mul_assoc a b c",
                            kind="lean_tactic",
                        ),
                    ],
                )
            ])

        if is_left_cancel(raw):
            fingerprint = TheoremFingerprint(
                theorem_family="group_left_cancel",
                objects=["G : Type u", "[Group G]", "a b c : G"],
                assumptions=["h : a * b = a * c"],
                conclusion="b = c",
                forbidden_drift=["CommGroup", "axiom", "unsafe", "#eval", "run_cmd", "assume b = c"],
                source_theorem=problem.theorem,
            )
            code = f"""{imports}

set_option autoImplicit false

theorem {theorem_name} {{G : Type u}} [Group G] {{a b c : G}} (h : a * b = a * c) :
    b = c := by
  exact mul_left_cancel h

#print axioms {theorem_name}
"""
            return LeanDraft(theorem_name, code, fingerprint, [
                ProofNode(
                    id="n1",
                    source_text=problem.proof,
                    truth=TruthLane(
                        claim="Left cancellation follows by multiplying by the inverse of a.",
                        dependencies=["[Group G]", "h : a * b = a * c"],
                        lean_goal="b = c",
                    ),
                    falsity=FalsityLane(
                        counterconditions=["The equality is not under the same left multiplier."],
                        counterexample_hint="Without group structure, cancellation may fail.",
                    ),
                    boundary=BoundaryLane(
                        ambiguities=["'multiply by inverse' has to be oriented and reassociated in Lean."],
                    ),
                    paths=[
                        ProofPath.refl("left_cancel_goal", id="refl_left_cancel_goal"),
                        ProofPath(
                            id="path_left_cancel_tactic",
                            source="left_cancel_goal",
                            target="lean_mul_left_cancel_witness",
                            label=TOP_L,
                            witness="exact mul_left_cancel h",
                            kind="lean_tactic",
                        ),
                    ],
                )
            ])

        if is_bad_comm(raw):
            fingerprint = TheoremFingerprint(
                theorem_family="bad_group_commutativity",
                objects=["G : Type u", "[Group G]", "a b : G"],
                assumptions=[],
                conclusion="a * b = b * a",
                forbidden_drift=["CommGroup", "axiom", "unsafe", "#eval", "run_cmd"],
                source_theorem=problem.theorem,
            )
            code = f"""{imports}

set_option autoImplicit false

theorem {theorem_name} {{G : Type u}} [Group G] (a b : G) :
    a * b = b * a := by
  simp

#print axioms {theorem_name}
"""
            return LeanDraft(theorem_name, code, fingerprint, [
                ProofNode(
                    id="n1",
                    source_text=problem.proof,
                    truth=TruthLane(
                        claim="The proof attempts to infer commutativity from group structure.",
                        dependencies=["[Group G]"],
                        lean_goal="a * b = b * a",
                    ),
                    falsity=FalsityLane(
                        counterconditions=["Nonabelian groups exist."],
                        counterexample_hint="Permutation groups are nonabelian.",
                    ),
                    boundary=BoundaryLane(
                        missing_data=["A commutativity assumption would mutate the theorem."],
                    ),
                    obstruction=ObstructionKind.THEOREM_DRIFT,
                    paths=[
                        ProofPath.refl("bad_comm_goal", id="refl_bad_comm_goal"),
                        ProofPath(
                            id="path_nonabelian_refutation",
                            source="bad_comm_goal",
                            target="nonabelian_countermodel",
                            label=BOTTOM_L,
                            witness="Nonabelian groups refute Group -> commutativity; adding CommGroup is theorem drift.",
                            kind="counterpath",
                        ),
                    ],
                )
            ])

        fingerprint = TheoremFingerprint(
            theorem_family="unsupported",
            source_theorem=problem.theorem,
            conclusion="unsupported",
            forbidden_drift=["axiom", "unsafe", "#eval", "run_cmd"],
        )
        code = f"""{imports}

-- Unsupported natural-language theorem family.
-- Provide `lean_code` directly or add a translator recognizer.
"""
        return LeanDraft(theorem_name, code, fingerprint, [
            ProofNode(
                id="n0",
                source_text=f"{problem.theorem}\n{problem.proof}",
                truth=TruthLane(claim="Unsupported theorem family."),
                falsity=FalsityLane(counterconditions=["No translation rule matched."]),
                boundary=BoundaryLane(
                    missing_data=["Need an LLM DraftProposal or a new deterministic recognizer."],
                ),
                obstruction=ObstructionKind.UNSUPPORTED_NL,
                paths=[ProofPath(
                    id="path_unsupported_gap",
                    source="unsupported_input",
                    target="draft_gap",
                    label=NEITHER_L,
                    witness="No translation rule produced a checkable path.",
                    kind="gap",
                )],
            )
        ])


def safe_theorem_name(request_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", request_id)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "shadow_" + cleaned
    return cleaned[:80]


def is_group_assoc(raw: str) -> bool:
    return "associat" in raw and re.search(r"\(a\s*\*\s*b\)\s*\*\s*c\s*=", raw) is not None


def is_left_cancel(raw: str) -> bool:
    return (
        re.search(r"a\s*\*\s*b\s*=\s*a\s*\*\s*c", raw) is not None
        and ("inverse" in raw or "cancel" in raw or "multiply both sides" in raw)
    )


def is_bad_comm(raw: str) -> bool:
    return "commutat" in raw and re.search(r"a\s*\*\s*b\s*=\s*b\s*\*\s*a", raw) is not None
