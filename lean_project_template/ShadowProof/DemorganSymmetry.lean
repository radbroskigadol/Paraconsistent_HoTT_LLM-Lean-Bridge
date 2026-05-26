/-
  ShadowProof Bridge v25.7 — De Morgan order-two symmetry on the
  paraconsistent bilattice L = Bool × Bool.

  Coordinates are (truth, refutation).  Designation is the truth coordinate.
  Path composition in the Python runtime is the truth-order meet

      (t, f) ∧L (t', f') = (t && t', f || f')

  and its dual join is

      (t, f) ∨L (t', f') = (t || t', f && f').

  This file is the standalone Lean witness for the finite algebraic claims
  reported by `shadowproof demorgan-symmetry` and `bilattice_axiom_report()`.
-/

import Mathlib

namespace ShadowProof.DemorganSymmetry

/-- The bilattice carrier as `Bool × Bool` (truth × refutation). -/
abbrev L := Bool × Bool

/-- The four named values used in the rest of the codebase. -/
def topL     : L := (true,  false)   -- classical proof / meet identity / join zero
def bottomL  : L := (false, true)    -- classical refutation / meet zero / join identity
def bothL    : L := (true,  true)    -- designated glut  (⊥⊤_L)
def neitherL : L := (false, false)   -- gap              (n_L)

/-- Truth-order meet: truth is conjunctive, refutation accumulates. -/
def meetL (x y : L) : L := (x.1 && y.1, x.2 || y.2)

/-- Truth-order join: dual to `meetL`. -/
def joinL (x y : L) : L := (x.1 || y.1, x.2 && y.2)

/-- The De Morgan involution: swap the truth/refutation coordinates. -/
def demorganSwap (x : L) : L := (x.2, x.1)

/-- Designation: the truth coordinate (matching `BilatticeValue.designated`). -/
def designated (x : L) : Bool := x.1

/-- The swap is involutive. -/
theorem demorganSwap_involutive (x : L) :
    demorganSwap (demorganSwap x) = x := by
  rcases x with ⟨t, r⟩
  rfl

/-- As a function, the swap squares to the identity. -/
theorem demorganSwap_sq_eq_id :
    demorganSwap ∘ demorganSwap = id := by
  funext x; exact demorganSwap_involutive x

/-- `top` and `bottom` are swapped by the De Morgan involution. -/
theorem demorganSwap_top_eq_bottom : demorganSwap topL = bottomL := rfl
theorem demorganSwap_bottom_eq_top : demorganSwap bottomL = topL := rfl

/-- `both` and `neither` are fixed by the De Morgan involution. -/
theorem demorganSwap_both_fixed    : demorganSwap bothL    = bothL    := rfl
theorem demorganSwap_neither_fixed : demorganSwap neitherL = neitherL := rfl

/-- The swap is NOT designation-preserving: it sends `top` (designated) to
    `bottom` (not designated). -/
theorem demorganSwap_not_designation_preserving :
    ∃ x : L, designated x ≠ designated (demorganSwap x) := by
  refine ⟨topL, ?_⟩
  decide

/-- Exhaustive case analysis: the only fixed points of `demorganSwap` are
    `both` and `neither`. -/
theorem demorganSwap_fixed_points (x : L) :
    demorganSwap x = x ↔ x = bothL ∨ x = neitherL := by
  rcases x with ⟨t, r⟩
  cases t <;> cases r <;> decide

/-- Meet is associative. -/
theorem meetL_assoc (a b c : L) : meetL (meetL a b) c = meetL a (meetL b c) := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩; rcases c with ⟨ct, cf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> cases ct <;> cases cf <;> decide

/-- Join is associative. -/
theorem joinL_assoc (a b c : L) : joinL (joinL a b) c = joinL a (joinL b c) := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩; rcases c with ⟨ct, cf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> cases ct <;> cases cf <;> decide

/-- Meet is commutative. -/
theorem meetL_comm (a b : L) : meetL a b = meetL b a := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

/-- Join is commutative. -/
theorem joinL_comm (a b : L) : joinL a b = joinL b a := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

/-- Meet and join are idempotent. -/
theorem meetL_idem (a : L) : meetL a a = a := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

theorem joinL_idem (a : L) : joinL a a = a := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

/-- Absorption laws for the truth-order lattice. -/
theorem meetL_joinL_absorb (a b : L) : meetL a (joinL a b) = a := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

theorem joinL_meetL_absorb (a b : L) : joinL a (meetL a b) = a := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

/-- Top is meet identity and bottom is meet zero. -/
theorem topL_meet_identity (a : L) : meetL topL a = a ∧ meetL a topL = a := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

theorem bottomL_meet_zero (a : L) : meetL bottomL a = bottomL ∧ meetL a bottomL = bottomL := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

/-- Bottom is join identity and top is join zero. -/
theorem bottomL_join_identity (a : L) : joinL bottomL a = a ∧ joinL a bottomL = a := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

theorem topL_join_zero (a : L) : joinL topL a = topL ∧ joinL a topL = topL := by
  rcases a with ⟨at, af⟩
  cases at <;> cases af <;> decide

/-- De Morgan duality for meet and join. -/
theorem demorgan_meet_dual (a b : L) :
    demorganSwap (meetL a b) = joinL (demorganSwap a) (demorganSwap b) := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

theorem demorgan_join_dual (a b : L) :
    demorganSwap (joinL a b) = meetL (demorganSwap a) (demorganSwap b) := by
  rcases a with ⟨at, af⟩; rcases b with ⟨bt, bf⟩
  cases at <;> cases af <;> cases bt <;> cases bf <;> decide

/-- The order-two function action generated by `identity` and `demorganSwap`
    is cyclic of order two.  The nontrivial map is a De Morgan duality, not a
    designation-preserving automorphism of the truth-order lattice. -/
theorem aut_L_is_Z2 :
    (id : L → L) ∘ id           = id           ∧
    (id : L → L) ∘ demorganSwap = demorganSwap ∧
    demorganSwap ∘ (id : L → L) = demorganSwap ∧
    demorganSwap ∘ demorganSwap = (id : L → L) := by
  refine ⟨?_, ?_, ?_, ?_⟩ <;> funext x <;> simp [demorganSwap_involutive]

end ShadowProof.DemorganSymmetry
