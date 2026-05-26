/-
  ShadowProof Bridge v25.7 — Lean-formalized finite ShadowHoTT
  bilattice core.

  This file is intentionally small and axiom-free.  It mirrors the runtime
  governance semantics in shadowproof_core/bilattice.py:

    L = Bool × Bool
    coordinates = (truth, refutation)
    designation = truth coordinate is true
    path composition = meet, with truth AND and refutation OR
    De Morgan duality = coordinate swap

  The point is not to implement full HoTT inside Lean.  The point is to keep
  the finite ShadowHoTT governance semantics kernel-checkable and resistant to
  runtime drift.
-/

import Mathlib

namespace ShadowProof.BilatticeCore

/-- The four named ShadowHoTT governance values. -/
inductive Shadow where
  | top      -- (true, false): clean proof signal
  | bottom   -- (false, true): refutation signal
  | both     -- (true, true): designated glut / proof plus refutation
  | neither  -- (false, false): gap / unchecked
  deriving DecidableEq, Repr

/-- Truth coordinate. -/
def truth : Shadow → Bool
  | .top => true
  | .bottom => false
  | .both => true
  | .neither => false

/-- Refutation coordinate. -/
def refutation : Shadow → Bool
  | .top => false
  | .bottom => true
  | .both => true
  | .neither => false

/-- Convert coordinates back to the named value. -/
def ofCoordinates : Bool → Bool → Shadow
  | true, false => .top
  | false, true => .bottom
  | true, true => .both
  | false, false => .neither

/-- Designation is exactly the truth coordinate. -/
def designated (x : Shadow) : Prop := truth x = true

/-- Truth-order meet / path composition: truth is fragile; refutation accumulates. -/
def meet (x y : Shadow) : Shadow :=
  ofCoordinates (truth x && truth y) (refutation x || refutation y)

/-- Truth-order join, dual to meet. -/
def join (x y : Shadow) : Shadow :=
  ofCoordinates (truth x || truth y) (refutation x && refutation y)

/-- De Morgan duality: swap truth and refutation. -/
def demorgan (x : Shadow) : Shadow :=
  ofCoordinates (refutation x) (truth x)

/-- Runtime name aliases. -/
abbrev topL : Shadow := .top
abbrev bottomL : Shadow := .bottom
abbrev bothL : Shadow := .both
abbrev neitherL : Shadow := .neither

@[simp] theorem truth_ofCoordinates (t r : Bool) : truth (ofCoordinates t r) = t := by
  cases t <;> cases r <;> rfl

@[simp] theorem refutation_ofCoordinates (t r : Bool) : refutation (ofCoordinates t r) = r := by
  cases t <;> cases r <;> rfl

@[simp] theorem ofCoordinates_truth_refutation (x : Shadow) :
    ofCoordinates (truth x) (refutation x) = x := by
  cases x <;> rfl

/-- Meet is exactly coordinatewise `(truth && truth, refutation || refutation)`. -/
theorem truth_fragile_for_meet (x y : Shadow) :
    truth (meet x y) = (truth x && truth y) := by
  cases x <;> cases y <;> rfl

/-- Refutation accumulates under meet/path composition. -/
theorem refutation_accumulates_for_meet (x y : Shadow) :
    refutation (meet x y) = (refutation x || refutation y) := by
  cases x <;> cases y <;> rfl

/-- Join is exactly coordinatewise `(truth || truth, refutation && refutation)`. -/
theorem truth_accumulates_for_join (x y : Shadow) :
    truth (join x y) = (truth x || truth y) := by
  cases x <;> cases y <;> rfl

/-- Refutation is fragile under join. -/
theorem refutation_fragile_for_join (x y : Shadow) :
    refutation (join x y) = (refutation x && refutation y) := by
  cases x <;> cases y <;> rfl

/-- The De Morgan swap is involutive. -/
theorem demorgan_order_two (x : Shadow) : demorgan (demorgan x) = x := by
  cases x <;> rfl

/-- Top and bottom are exchanged by De Morgan duality. -/
theorem demorgan_top_eq_bottom : demorgan topL = bottomL := rfl
theorem demorgan_bottom_eq_top : demorgan bottomL = topL := rfl

/-- Both and neither are fixed by De Morgan duality. -/
theorem demorgan_both_fixed : demorgan bothL = bothL := rfl
theorem demorgan_neither_fixed : demorgan neitherL = neitherL := rfl

/-- The only fixed points of De Morgan duality are `both` and `neither`. -/
theorem demorgan_fixed_points (x : Shadow) :
    demorgan x = x ↔ x = bothL ∨ x = neitherL := by
  cases x <;> decide

/-- The De Morgan map is not designation-preserving. -/
theorem demorgan_not_designation_preserving :
    ∃ x : Shadow, designated x ∧ ¬ designated (demorgan x) := by
  refine ⟨topL, ?_⟩
  constructor <;> decide

/-- Meet algebra laws. -/
theorem meet_assoc (a b c : Shadow) : meet (meet a b) c = meet a (meet b c) := by
  cases a <;> cases b <;> cases c <;> rfl

theorem meet_comm (a b : Shadow) : meet a b = meet b a := by
  cases a <;> cases b <;> rfl

theorem meet_idem (a : Shadow) : meet a a = a := by
  cases a <;> rfl

/-- Join algebra laws. -/
theorem join_assoc (a b c : Shadow) : join (join a b) c = join a (join b c) := by
  cases a <;> cases b <;> cases c <;> rfl

theorem join_comm (a b : Shadow) : join a b = join b a := by
  cases a <;> cases b <;> rfl

theorem join_idem (a : Shadow) : join a a = a := by
  cases a <;> rfl

/-- Absorption laws for the truth-order lattice. -/
theorem meet_join_absorb (a b : Shadow) : meet a (join a b) = a := by
  cases a <;> cases b <;> rfl

theorem join_meet_absorb (a b : Shadow) : join a (meet a b) = a := by
  cases a <;> cases b <;> rfl

/-- Meet identity/zero laws. -/
theorem top_meet_identity (a : Shadow) : meet topL a = a ∧ meet a topL = a := by
  cases a <;> decide

theorem bottom_meet_zero (a : Shadow) : meet bottomL a = bottomL ∧ meet a bottomL = bottomL := by
  cases a <;> decide

/-- Join identity/zero laws. -/
theorem bottom_join_identity (a : Shadow) : join bottomL a = a ∧ join a bottomL = a := by
  cases a <;> decide

theorem top_join_zero (a : Shadow) : join topL a = topL ∧ join a topL = topL := by
  cases a <;> decide

/-- De Morgan duality between meet and join. -/
theorem demorgan_meet_dual (a b : Shadow) :
    demorgan (meet a b) = join (demorgan a) (demorgan b) := by
  cases a <;> cases b <;> rfl

theorem demorgan_join_dual (a b : Shadow) :
    demorgan (join a b) = meet (demorgan a) (demorgan b) := by
  cases a <;> cases b <;> rfl

/-- Both is designated, but it carries a refutation coordinate. -/
theorem both_designated : designated bothL := by decide

theorem both_refuted : refutation bothL = true := rfl

/-- Neither is neither designated nor refuted. -/
theorem neither_not_designated : ¬ designated neitherL := by decide

theorem neither_not_refuted : refutation neitherL = false := rfl

end ShadowProof.BilatticeCore
