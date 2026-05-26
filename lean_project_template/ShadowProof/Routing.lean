/-
  ShadowProof Bridge v25.7 — Lean reference model for ShadowHoTT disposition
  routing.

  The production Python runtime remains the operational gateway.  This file is
  the kernel-checked reference semantics for the small routing invariant that
  matters most commercially and mathematically:

      Lean acceptance plus a refutation-bearing Shadow state is never silently
      auto-accepted.
-/

import ShadowProof.BilatticeCore

namespace ShadowProof.Routing

open ShadowProof.BilatticeCore

/-- Runtime Lean status mirror. -/
inductive LeanStatus where
  | accepted
  | rejected
  | not_run
  | not_available
  | timeout
  deriving DecidableEq, Repr

/-- Runtime tool/status mirror. -/
inductive ToolStatus where
  | ok
  | rejected
  | error
  | needs_repair
  | unchecked
  | human_review
  deriving DecidableEq, Repr

/-- Buyer-facing disposition states. -/
inductive Disposition where
  | accept
  | repair
  | reject
  | human_review
  | unchecked
  deriving DecidableEq, Repr

/-- Pure reference routing over final Shadow label and runtime status. -/
def route (leanStatus : LeanStatus) (status : ToolStatus) (label : Shadow) : Disposition :=
  match label with
  | .both => .human_review
  | .top =>
      if leanStatus = .accepted ∧ status = .ok then .accept else .repair
  | .bottom => .reject
  | .neither =>
      match leanStatus, status with
      | .not_available, .unchecked => .unchecked
      | .timeout, .unchecked => .unchecked
      | .not_run, .unchecked => .unchecked
      | .not_available, .error => .unchecked
      | .timeout, .error => .unchecked
      | .not_run, .error => .unchecked
      | _, _ => .repair

/-- No-Glutty-J: a glutty state routes to human review for every status pair. -/
theorem no_glutty_j (leanStatus : LeanStatus) (status : ToolStatus) :
    route leanStatus status bothL = .human_review := by
  rfl

/-- The operationally central case: Lean accepted + ok + both is not accepted. -/
theorem accepted_ok_both_never_accept :
    route .accepted .ok bothL ≠ .accept := by
  decide

/-- A refutation-bearing accepted state is routed to human review. -/
theorem accepted_ok_both_routes_human_review :
    route .accepted .ok bothL = .human_review := by
  rfl

/-- Acceptance can only occur for top label with accepted Lean and ok status. -/
theorem accept_requires_clean_top (leanStatus : LeanStatus) (status : ToolStatus) (label : Shadow) :
    route leanStatus status label = .accept →
      label = topL ∧ leanStatus = .accepted ∧ status = .ok := by
  cases leanStatus <;> cases status <;> cases label <;> simp [route]

/-- Bottom is always rejected in the reference routing table. -/
theorem bottom_routes_reject (leanStatus : LeanStatus) (status : ToolStatus) :
    route leanStatus status bottomL = .reject := by
  rfl

/-- Clean Lean acceptance of top is accepted. -/
theorem accepted_ok_top_accepts :
    route .accepted .ok topL = .accept := by
  decide

end ShadowProof.Routing
