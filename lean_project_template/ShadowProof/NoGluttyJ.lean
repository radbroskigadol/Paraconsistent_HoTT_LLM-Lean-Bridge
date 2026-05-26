/-
  ShadowProof Bridge v25.7 — No-Glutty-J safety theorem.

  This file names the central governance invariant as a Lean theorem: a
  contradiction-bearing accepted state is designated, but it is not silently
  auto-accepted.  It routes to human review.
-/

import ShadowProof.BilatticeCore
import ShadowProof.Routing
import ShadowProof.PatchMorphism

namespace ShadowProof.NoGluttyJ

open ShadowProof.BilatticeCore
open ShadowProof.Routing

/-- The glutty state is designated in the bilattice semantics. -/
theorem glutty_is_designated : designated bothL := by
  exact both_designated

/-- The glutty state carries refutation. -/
theorem glutty_has_refutation : refutation bothL = true := by
  exact both_refuted

/-- No-Glutty-J, specialized to the most important runtime case. -/
theorem no_glutty_j_accepted_ok :
    route .accepted .ok bothL = .human_review := by
  rfl

/-- Therefore the same case is never auto-accepted. -/
theorem no_glutty_j_accepted_ok_not_accept :
    route .accepted .ok bothL ≠ .accept := by
  decide

/-- Any accepted route must have clean top Shadow label. -/
theorem accepted_route_has_clean_top
    (leanStatus : LeanStatus) (status : ToolStatus) (label : Shadow) :
    route leanStatus status label = .accept → label = topL := by
  intro h
  exact (accept_requires_clean_top leanStatus status label h).left

/-- Contradiction-bearing states are review-bound for every Lean/tool status. -/
theorem glutty_always_review_bound
    (leanStatus : LeanStatus) (status : ToolStatus) :
    route leanStatus status bothL = .human_review := by
  exact no_glutty_j leanStatus status

end ShadowProof.NoGluttyJ
