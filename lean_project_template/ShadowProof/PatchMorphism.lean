/-
  ShadowProof Bridge v25.7 — abstract theorem-fingerprint preserving patch
  morphisms.

  Repairs may transform proof bodies, imports, tactics, or local lemmas.  They
  are theorem-safe only when the theorem fingerprint is preserved.  This file
  formalizes the small invariant that the runtime enforces by theorem-locking.
-/

import Mathlib

namespace ShadowProof.PatchMorphism

/-- Minimal abstract patch morphism: source and target theorem fingerprints. -/
structure PatchMorphism where
  sourceFingerprint : String
  targetFingerprint : String
  deriving Repr

/-- The theorem-safety predicate for target-preserving repair. -/
def PreservesFingerprint (p : PatchMorphism) : Prop :=
  p.sourceFingerprint = p.targetFingerprint

/-- Identity patch on a theorem fingerprint. -/
def identity (fingerprint : String) : PatchMorphism :=
  { sourceFingerprint := fingerprint, targetFingerprint := fingerprint }

/-- Compose two patches when the first target matches the second source. -/
def compose (p q : PatchMorphism) (_h : p.targetFingerprint = q.sourceFingerprint) : PatchMorphism :=
  { sourceFingerprint := p.sourceFingerprint, targetFingerprint := q.targetFingerprint }

/-- Identity patch preserves the theorem fingerprint. -/
theorem identity_preserves (fingerprint : String) :
    PreservesFingerprint (identity fingerprint) := by
  rfl

/-- Composition of fingerprint-preserving patches preserves the fingerprint. -/
theorem compose_preserves
    (p q : PatchMorphism)
    (hlink : p.targetFingerprint = q.sourceFingerprint)
    (hp : PreservesFingerprint p)
    (hq : PreservesFingerprint q) :
    PreservesFingerprint (compose p q hlink) := by
  unfold PreservesFingerprint compose at *
  exact hp.trans (hlink.trans hq)

/-- A changed theorem fingerprint is not theorem-safe. -/
theorem changed_fingerprint_not_preserved
    (p : PatchMorphism)
    (h : p.sourceFingerprint ≠ p.targetFingerprint) :
    ¬ PreservesFingerprint p := by
  intro hp
  exact h hp

/-- Fingerprint preservation is symmetric as an equality, even though repair
    morphisms themselves are not claimed to be operationally reversible. -/
theorem preservation_symmetric (p : PatchMorphism) :
    PreservesFingerprint p → p.targetFingerprint = p.sourceFingerprint := by
  intro hp
  exact hp.symm

end ShadowProof.PatchMorphism
