"""Repair-engine tests, including the REPAIR-1 fix that makes
`replace_body` honest when it cannot find a proof-body anchor.
"""
from shadowproof_core.models import LeanDraft, PatchKind, TheoremFingerprint
from shadowproof_core.repair import ShadowHoTTRepairEngine, replace_body


def _draft(code: str, family: str = "group_assoc"):
    fp = TheoremFingerprint(
        theorem_family=family,
        objects=["G : Type u", "[Group G]", "a b c : G"],
        conclusion="(a * b) * c = a * (b * c)",
        forbidden_drift=["CommGroup", "axiom", "sorry"],
    )
    return LeanDraft(name="t", code=code, fingerprint=fp, proof_graph=[])


def test_replace_body_anchored_on_print_axioms():
    code = """import Mathlib

theorem t (a b c : G) : (a * b) * c = a * (b * c) := by
  sorry_placeholder

#print axioms t
"""
    new = replace_body(code, "by\n  exact mul_assoc a b c")
    assert new is not None
    assert "exact mul_assoc a b c" in new
    assert "sorry_placeholder" not in new


def test_replace_body_fallback_to_by_block():
    code = """theorem t (a b c : G) : (a * b) * c = a * (b * c) := by
  sorry_placeholder
"""
    new = replace_body(code, "by\n  exact mul_assoc a b c")
    assert new is not None
    assert "exact mul_assoc a b c" in new


def test_replace_body_returns_none_when_no_by_block():
    code = "def trivial : Nat := 42\n"
    assert replace_body(code, "by\n  exact mul_assoc a b c") is None


def test_repair_engine_produces_no_patch_when_anchor_missing():
    # Code that has no `:= by` site at all should NOT silently produce a
    # patch whose new_code equals the original.
    draft = _draft("def trivial : Nat := 42\n")
    eng = ShadowHoTTRepairEngine()

    class _Result:
        diagnostics = []

    cands = eng.candidate_patches(draft, _Result(), iteration=0, allow_theorem_mutation=False)
    assert cands
    # First candidate should be a NO_PATCH (anchor missing) rather than a
    # REPLACE_TACTIC with new_code == original.
    p = cands[0]
    assert p.kind == PatchKind.NO_PATCH
    assert any(d.message.startswith("repair.replace_body") for d in p.diagnostics)


def test_repair_engine_bad_commutativity_rejects_drift():
    draft = _draft("import Mathlib\n", family="bad_group_commutativity")
    eng = ShadowHoTTRepairEngine()

    class _Result:
        diagnostics = []

    cands = eng.candidate_patches(draft, _Result(), iteration=0, allow_theorem_mutation=False)
    assert cands
    # The bad-commutativity family always rejects drift.
    assert cands[0].kind == PatchKind.REJECT_DRIFT


def test_replace_body_ignores_fake_anchor_inside_string_literal():
    code = 'def fake : String := ":= by\\n  sorry\\n\\n#print axioms fake"\n'
    assert replace_body(code, "by\n  trivial") is None


def test_replace_body_uses_real_anchor_not_comment_or_string_noise():
    code = '''def fake : String := ":= by\n  sorry\n\n#print axioms fake"
-- := by should not count here
/- #print axioms fake -/
theorem t : True := by
  trivial

#print axioms t
'''
    new = replace_body(code, "by\n  exact True.intro")
    assert new is not None
    assert "exact True.intro" in new
    assert "def fake" in new
    assert new.count("#print axioms") == 3  # string literal, preserved comment, and real directive
