from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any

from .bilattice import (
    BilatticeValue,
    TOP_L,
    BOTTOM_L,
    BOTH_L,
    NEITHER_L,
    L_VALUES,
    aut_L,
    bilattice_meet_all,
)
from .models import (
    Diagnostic,
    ObstructionKind,
    Patch,
    PatchKind,
    ProofNode,
    ProofPath,
    TheoremFingerprint,
    enum_clean,
)


class ShadowLane(str, Enum):
    TRUTH = "truth"
    FALSITY = "falsity"
    BOUNDARY = "boundary"


class Repairability(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_GUIDED = "llm_guided"
    RETRIEVAL_GUIDED = "retrieval_guided"
    UNPATCHABLE = "unpatchable"
    POLICY_BLOCKED = "policy_blocked"
    ENVIRONMENTAL = "environmental"


class ShadowVerdict(str, Enum):
    ACCEPT = "accept"
    REPAIR = "repair"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"
    UNCHECKED = "unchecked"


@dataclass
class TriValSummary:
    """Derived UI/routing summary.  Not the semantic ShadowHoTT valuation."""

    truth: float = 0.0
    falsity: float = 0.0
    boundary: float = 1.0

    @classmethod
    def from_bilattice(cls, label: BilatticeValue, boundary_bias: float = 0.0) -> "TriValSummary":
        label = BilatticeValue.from_label(label)
        if label == TOP_L:
            return cls(1.0, 0.0, max(0.0, boundary_bias * 0.25)).normalized()
        if label == BOTTOM_L:
            return cls(0.0, 1.0, max(0.0, boundary_bias * 0.25)).normalized()
        if label == BOTH_L:
            # Glutty states are designated but review-bound, so keep an explicit boundary mass.
            return cls(1.0, 1.0, max(0.5, boundary_bias * 0.5)).normalized()
        return cls(0.0, 0.0, max(1.0, boundary_bias)).normalized()

    def normalized(self) -> "TriValSummary":
        vals = [max(0.0, float(self.truth)), max(0.0, float(self.falsity)), max(0.0, float(self.boundary))]
        total = sum(vals)
        if total <= 0:
            return TriValSummary(0.0, 0.0, 1.0)
        return TriValSummary(vals[0] / total, vals[1] / total, vals[2] / total)

    def to_dict(self) -> dict[str, float]:
        n = self.normalized()
        return {"truth": round(n.truth, 6), "falsity": round(n.falsity, 6), "boundary": round(n.boundary, 6)}


# Backward-compatible name; the actual semantic object is BilatticeValue.
ShadowValuation = TriValSummary


@dataclass
class ShadowObstruction:
    id: str
    kind: str
    lane: ShadowLane
    locus: str
    witness: str
    severity: str
    repairability: Repairability
    blocks_validation: bool
    suggested_patch_kind: str | None = None
    diagnostic_source: str | None = None
    bilattice_label: BilatticeValue = NEITHER_L

    def to_dict(self) -> dict[str, Any]:
        return enum_clean(asdict(self))


@dataclass
class PatchMorphism:
    """
    ShadowHoTT patch morphism μ : S → S′.

    It carries the theorem-fingerprint preservation bit and a declared permitted
    delta region.  `compose` gives the Π-component monoid law used by the
    theorem-safe repair loop.  The concrete textual patch remains in Patch;
    this object is the semantic action/certificate for that patch.
    """

    id: str
    kind: str
    source_state: str
    target_state: str | None
    theorem_safe: bool
    fingerprint_preserved: bool
    description: str
    obstruction_ids: list[str] = field(default_factory=list)
    permitted_delta: list[str] = field(default_factory=list)
    source_label: BilatticeValue = NEITHER_L
    target_label: BilatticeValue = NEITHER_L
    conservation_checked: bool = False
    conservation_ok: bool | None = None

    def compose(self, other: "PatchMorphism", id: str | None = None) -> "PatchMorphism":
        if self.target_state is not None and other.source_state is not None and self.target_state != other.source_state:
            # In repair traces we sometimes only know symbolic S/S_prime names.  Do not silently compose mismatched concrete states.
            if not {self.target_state, other.source_state} <= {"S", "S_prime", "S_prime_candidate", None}:
                raise ValueError(f"cannot compose morphisms {self.id} and {other.id}: state mismatch")
        return PatchMorphism(
            id=id or f"{self.id}_then_{other.id}",
            kind=f"{self.kind};{other.kind}",
            source_state=self.source_state,
            target_state=other.target_state,
            theorem_safe=self.theorem_safe and other.theorem_safe,
            fingerprint_preserved=self.fingerprint_preserved and other.fingerprint_preserved,
            description=f"Composition of {self.id} then {other.id}.",
            obstruction_ids=list(dict.fromkeys(self.obstruction_ids + other.obstruction_ids)),
            permitted_delta=list(dict.fromkeys(self.permitted_delta + other.permitted_delta)),
            source_label=self.source_label,
            target_label=self.target_label.meet(other.target_label),
            conservation_checked=self.conservation_checked and other.conservation_checked,
            conservation_ok=compose_conservation_ok(self.conservation_ok, other.conservation_ok),
        )

    def to_dict(self) -> dict[str, Any]:
        return enum_clean(asdict(self))


@dataclass
class ShadowHoTTState:
    state_id: str
    theorem_fingerprint: TheoremFingerprint | dict[str, Any] | None
    proof_graph: list[ProofNode] | list[dict[str, Any]]
    global_label: BilatticeValue
    node_labels: dict[str, BilatticeValue]
    path_labels: dict[str, BilatticeValue]
    global_valuation: TriValSummary
    node_valuations: dict[str, TriValSummary]
    obstructions: list[ShadowObstruction]
    patch_morphisms: list[PatchMorphism]
    verdict: ShadowVerdict
    certificate_status: str
    notes: list[str] = field(default_factory=list)
    semantics_version: str = "shadowhott-j-conserved-bilattice-v25"

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw = enum_clean(raw)
        raw["global_label"] = self.global_label.to_dict()
        raw["node_labels"] = {k: v.to_dict() for k, v in self.node_labels.items()}
        raw["path_labels"] = {k: v.to_dict() for k, v in self.path_labels.items()}
        raw["global_valuation"] = self.global_valuation.to_dict()
        raw["node_valuations"] = {k: v.to_dict() for k, v in self.node_valuations.items()}
        raw["obstructions"] = [o.to_dict() for o in self.obstructions]
        raw["patch_morphisms"] = [p.to_dict() for p in self.patch_morphisms]
        raw["bilattice_axioms"] = bilattice_axiom_report()
        return raw

    def classical_targets(self) -> set[str]:
        targets: set[str] = set()
        for node in self.proof_graph:
            for path in paths_from_node(node, strict=False):
                if path.label.classical:
                    targets.add(path.target)
        return targets


@dataclass
class ConservationReport:
    status: str
    violations: list[str] = field(default_factory=list)
    checked_paths: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compose_conservation_ok(a: bool | None, b: bool | None) -> bool | None:
    """Tri-state conjunction for conservation evidence.

    True means both components were checked and passed.  False means at least
    one failed.  None means the composed morphism includes unchecked evidence,
    so it must not be advertised as fully conservation-certified.
    """
    if a is False or b is False:
        return False
    if a is True and b is True:
        return True
    return None


# ---------------------------------------------------------------------------
# State construction
# ---------------------------------------------------------------------------


def build_shadowhott_state(payload: dict[str, Any]) -> ShadowHoTTState:
    fp = payload.get("theorem_fingerprint")
    if fp is None and isinstance(payload.get("draft"), dict):
        fp = payload["draft"].get("theorem_fingerprint")
    if fp is None:
        fp = payload.get("fingerprint")

    proof_graph = payload.get("proof_graph") or []
    diagnostics = normalize_diagnostics(payload.get("diagnostics", []) or [])
    patches = payload.get("patches", []) or []
    lean_status = str(payload.get("lean_status", "not_run"))
    status = str(payload.get("status", "unchecked"))
    final_code = str(payload.get("final_lean_code") or payload.get("lean_code") or "")
    retrieval = payload.get("retrieval") or {}
    certificate = payload.get("certificate")

    obstructions = diagnostics_to_obstructions(diagnostics, final_code=final_code)
    obstructions.extend(fingerprint_obstructions(fp, final_code))
    strict_labels = bool(payload.get("strict_bilattice_labels", True))

    node_labels = compute_node_labels(proof_graph, strict=strict_labels)
    path_labels = compute_path_labels(proof_graph, strict=strict_labels)
    proof_label = bilattice_meet_all(node_labels.values(), default=NEITHER_L) if node_labels else NEITHER_L
    global_label = compute_global_label(
        proof_label=proof_label,
        diagnostics=diagnostics,
        obstructions=obstructions,
        lean_status=lean_status,
        status=status,
        certificate=certificate,
    )
    valuation = TriValSummary.from_bilattice(global_label, boundary_bias=boundary_bias(obstructions, lean_status, status))
    node_vals = {k: TriValSummary.from_bilattice(v).normalized() for k, v in node_labels.items()} or {"global": valuation}

    patch_morphisms = patches_to_morphisms(
        patches,
        obstructions,
        fingerprint_preserved=not has_hard_drift(obstructions),
        source_label=proof_label,
        target_label=global_label,
    )
    if retrieval:
        patch_morphisms.append(retrieval_patch_morphism(obstructions, source_label=proof_label, target_label=global_label))

    verdict = compute_verdict(global_label, valuation, obstructions, lean_status, status)

    notes = [
        "ShadowHoTT semantics are L = 2×2 bilattice labels on proof paths, not probability triples.",
        "Designation is the binary predicate truth_coordinate = true; glutty BOTH is designated but routed to human review.",
        "Path composition uses ∧_L: truth is AND, refutation is OR; refl paths are forced to ⊤_L.",
        "Patch morphisms are theorem-safe only when fingerprint preservation and No-Glutty-J conservation hold.",
    ]
    if retrieval:
        notes.append("Retrieval context is advisory; it cannot override theorem-lock, bilattice conservation, or Lean validation.")

    return ShadowHoTTState(
        state_id=state_id_from_payload(payload),
        theorem_fingerprint=coerce_fingerprint(fp),
        proof_graph=proof_graph,
        global_label=global_label,
        node_labels=node_labels,
        path_labels=path_labels,
        global_valuation=valuation,
        node_valuations=node_vals,
        obstructions=obstructions,
        patch_morphisms=patch_morphisms,
        verdict=verdict,
        certificate_status=certificate_status(certificate, lean_status, status, global_label),
        notes=notes,
    )


def audit_shadowhott_state(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("strict_bilattice_labels", False)
    state = build_shadowhott_state(payload)
    d = state.to_dict()
    failures: list[str] = []

    ax = bilattice_axiom_report()
    if not ax["all_passed"]:
        failures.append("bilattice axiom report failed")

    gv = d["global_valuation"]
    total = gv["truth"] + gv["falsity"] + gv["boundary"]
    if abs(total - 1.0) > 0.00001:
        failures.append("derived global tri-summary is not normalized")

    if state.verdict == ShadowVerdict.ACCEPT and any(o.blocks_validation for o in state.obstructions):
        failures.append("accept verdict despite blocking obstruction")

    if state.verdict == ShadowVerdict.ACCEPT and state.certificate_status != "accepted_by_lean_top":
        failures.append("accept verdict without top Lean certificate status")

    if state.verdict == ShadowVerdict.ACCEPT and state.global_label != TOP_L:
        failures.append("accept verdict without ⊤_L global label")

    if state.verdict == ShadowVerdict.HUMAN_REVIEW and state.global_label != BOTH_L:
        failures.append("human_review verdict without glutty ⊥⊤_L label")

    failures.extend(translator_invariant_failures(state.proof_graph, strict=False))

    for node in state.proof_graph:
        for path in paths_from_node(node, strict=False):
            if path.is_refl and path.label != TOP_L:
                failures.append(f"refl path {path.id} is not labelled ⊤_L")

    for pm in state.patch_morphisms:
        if not pm.fingerprint_preserved and pm.theorem_safe:
            failures.append(f"patch morphism {pm.id} marked theorem_safe despite fingerprint drift")
        if pm.conservation_checked and pm.conservation_ok is False and pm.theorem_safe:
            failures.append(f"patch morphism {pm.id} theorem_safe despite failed conservation")

    return {
        "status": "ok" if not failures else "failed",
        "audit_failures": failures,
        "shadowhott_state": d,
    }


# ---------------------------------------------------------------------------
# Bilattice/path axiom surface
# ---------------------------------------------------------------------------


def bilattice_axiom_report() -> dict[str, Any]:
    involution_order_two = all(v.involution().involution() == v for v in L_VALUES)
    fixed_points = sorted(v.label for v in L_VALUES if v.involution() == v)
    meet_assoc = all(a.meet(b).meet(c) == a.meet(b.meet(c)) for a in L_VALUES for b in L_VALUES for c in L_VALUES)
    meet_comm = all(a.meet(b) == b.meet(a) for a in L_VALUES for b in L_VALUES)
    meet_idempotent = all(a.meet(a) == a for a in L_VALUES)
    join_assoc = all(a.join(b).join(c) == a.join(b.join(c)) for a in L_VALUES for b in L_VALUES for c in L_VALUES)
    join_comm = all(a.join(b) == b.join(a) for a in L_VALUES for b in L_VALUES)
    join_idempotent = all(a.join(a) == a for a in L_VALUES)
    absorption = all(a.meet(a.join(b)) == a and a.join(a.meet(b)) == a for a in L_VALUES for b in L_VALUES)
    demorgan_meet_join = all(a.meet(b).involution() == a.involution().join(b.involution()) for a in L_VALUES for b in L_VALUES)
    demorgan_join_meet = all(a.join(b).involution() == a.involution().meet(b.involution()) for a in L_VALUES for b in L_VALUES)
    refl_top = ProofPath.refl("x").label == TOP_L
    designation_binary = all(isinstance(v.designated, bool) and v.designated == v.truth for v in L_VALUES)
    aut = aut_L()
    aut_z2 = aut["composition_table"].get("involution∘involution") == "identity"
    checks = [
        involution_order_two,
        meet_assoc,
        meet_comm,
        meet_idempotent,
        join_assoc,
        join_comm,
        join_idempotent,
        absorption,
        demorgan_meet_join,
        demorgan_join_meet,
        refl_top,
        designation_binary,
        aut_z2,
        fixed_points == ["both", "neither"],
    ]
    return {
        "all_passed": all(checks),
        "L": [v.to_dict() for v in L_VALUES],
        "designation": "designated iff truth_coordinate is true",
        "involution_order_two": involution_order_two,
        "involution_fixed_points": fixed_points,
        "aut_L": aut,
        "composition_meet_associative": meet_assoc,
        "composition_meet_commutative": meet_comm,
        "composition_meet_idempotent": meet_idempotent,
        "join_associative": join_assoc,
        "join_commutative": join_comm,
        "join_idempotent": join_idempotent,
        "absorption": absorption,
        "demorgan_meet_join_duality": demorgan_meet_join,
        "demorgan_join_meet_duality": demorgan_join_meet,
        "refl_label_top": refl_top,
        "designation_binary": designation_binary,
    }


def normalize_diagnostics(items: list[Any]) -> list[dict[str, Any]]:
    out = []
    for i in items:
        if isinstance(i, Diagnostic):
            out.append(i.to_dict())
        elif isinstance(i, dict):
            out.append(i)
        else:
            out.append({"severity": "error", "kind": "unknown_lean_failure", "message": str(i), "source": "unknown"})
    return out


def paths_from_node(node: Any, *, strict: bool = True) -> list[ProofPath]:
    raw_paths: list[Any] = []
    if isinstance(node, ProofNode):
        raw_paths = node.paths
    elif isinstance(node, dict):
        raw_paths = node.get("paths", []) or []
    out: list[ProofPath] = []
    for idx, p in enumerate(raw_paths):
        if isinstance(p, ProofPath):
            out.append(p)
        elif isinstance(p, dict):
            label_raw = p.get("label", NEITHER_L)
            try:
                label = BilatticeValue.from_label(label_raw)
            except Exception as exc:
                if strict:
                    raise ValueError(f"unknown bilattice label in proof path {p.get('id', idx + 1)!r}: {label_raw!r}") from exc
                label = NEITHER_L
            out.append(ProofPath(
                id=str(p.get("id", f"path_{idx+1}")),
                source=str(p.get("source", "unknown")),
                target=str(p.get("target", "unknown")),
                label=label,
                witness=str(p.get("witness", "")),
                kind=str(p.get("kind", "path")),
            ))
    return out


def node_id_and_obstruction(node: Any, idx: int) -> tuple[str, str]:
    if isinstance(node, ProofNode):
        return node.id, str(node.obstruction.value if hasattr(node.obstruction, "value") else node.obstruction)
    if isinstance(node, dict):
        return str(node.get("id", f"n{idx+1}")), str(node.get("obstruction", "none"))
    return f"n{idx+1}", "none"


def compute_path_labels(proof_graph: list[Any], *, strict: bool = True) -> dict[str, BilatticeValue]:
    out: dict[str, BilatticeValue] = {}
    for node in proof_graph:
        for path in paths_from_node(node, strict=strict):
            out[path.id] = path.label
    return out


def compute_node_labels(proof_graph: list[Any], *, strict: bool = True) -> dict[str, BilatticeValue]:
    out: dict[str, BilatticeValue] = {}
    for idx, node in enumerate(proof_graph):
        node_id, obstruction_kind = node_id_and_obstruction(node, idx)
        paths = paths_from_node(node, strict=strict)
        if paths:
            out[node_id] = bilattice_meet_all((p.label for p in paths), default=NEITHER_L)
            continue
        if obstruction_kind and obstruction_kind != "none":
            lane = lane_for_kind(obstruction_kind)
            out[node_id] = BOTTOM_L if lane == ShadowLane.FALSITY else NEITHER_L
        else:
            out[node_id] = TOP_L
    return out


def compose_paths(paths: list[ProofPath]) -> ProofPath | None:
    if not paths:
        return None
    acc = paths[0]
    for p in paths[1:]:
        acc = acc.compose(p)
    return acc


def translator_invariant_failures(proof_graph: list[Any], *, strict: bool = True) -> list[str]:
    """Check the minimum path discipline every translator must preserve.

    Each node should carry at least one refl path and at least one non-refl
    tactical/counter/boundary path.  Empty or uncovered nodes must remain
    non-classical unless Lean acceptance later supplies classical evidence.
    """
    failures: list[str] = []
    for idx, node in enumerate(proof_graph):
        node_id, obstruction_kind = node_id_and_obstruction(node, idx)
        paths = paths_from_node(node, strict=strict)
        if not paths:
            if not obstruction_kind or obstruction_kind == "none":
                failures.append(f"node {node_id} has no paths and no obstruction; uncovered nodes must default to n_L")
            continue
        if not any(p.is_refl for p in paths):
            failures.append(f"node {node_id} has no refl path")
        if not any(not p.is_refl for p in paths):
            failures.append(f"node {node_id} has no tactical/counter/boundary path")
        for p in paths:
            if p.is_refl and p.label != TOP_L:
                failures.append(f"refl path {p.id} is labelled {p.label.pretty}, expected ⊤_L")
    return failures


# ---------------------------------------------------------------------------
# Obstructions and labels
# ---------------------------------------------------------------------------


def diagnostics_to_obstructions(diagnostics: list[dict[str, Any]], final_code: str = "") -> list[ShadowObstruction]:
    out = []
    for idx, d in enumerate(diagnostics):
        kind = str(d.get("kind", "unknown_lean_failure"))
        lane = lane_for_kind(kind)
        repairability = repairability_for_kind(kind)
        severity = str(d.get("severity", "error"))
        blocks = blocks_validation(kind, severity)
        out.append(ShadowObstruction(
            id=f"omega_{idx+1}",
            kind=kind,
            lane=lane,
            locus=locus_for_diagnostic(d),
            witness=str(d.get("message", ""))[:600],
            severity=severity,
            repairability=repairability,
            blocks_validation=blocks,
            suggested_patch_kind=suggested_patch_for_kind(kind),
            diagnostic_source=str(d.get("source", "unknown")),
            bilattice_label=label_for_obstruction(kind, severity),
        ))
    return out


def fingerprint_obstructions(fp: Any, code: str) -> list[ShadowObstruction]:
    if not fp or not code:
        return []
    forbidden = []
    if isinstance(fp, TheoremFingerprint):
        forbidden = fp.forbidden_drift
    elif isinstance(fp, dict):
        forbidden = list(fp.get("forbidden_drift", []))
    out = []
    stripped = strip_comments(code)
    lower = stripped.lower()
    for token in forbidden:
        t = str(token).strip()
        if not t or t.lower() in {"axiom", "axioms", "sorry"}:
            continue
        if t.lower() in lower:
            out.append(ShadowObstruction(
                id=f"omega_fp_{len(out)+1}",
                kind="theorem_drift",
                lane=ShadowLane.FALSITY,
                locus="theorem_fingerprint",
                witness=f"Forbidden theorem-drift token detected in code: {t}",
                severity="error",
                repairability=Repairability.UNPATCHABLE,
                blocks_validation=True,
                suggested_patch_kind="reject_drift",
                diagnostic_source="shadowhott_fingerprint",
                bilattice_label=BOTTOM_L,
            ))
    if re.search(r"\bsorry\b", lower):
        out.append(ShadowObstruction(
            id=f"omega_fp_{len(out)+1}",
            kind="sorry_leak",
            lane=ShadowLane.FALSITY,
            locus="trust_basis",
            witness="Forbidden `sorry` appears in Lean code.",
            severity="error",
            repairability=Repairability.POLICY_BLOCKED,
            blocks_validation=True,
            suggested_patch_kind="no_patch",
            diagnostic_source="shadowhott_fingerprint",
            bilattice_label=BOTTOM_L,
        ))
    if re.search(r"^\s*axiom\s+", stripped, flags=re.M):
        out.append(ShadowObstruction(
            id=f"omega_fp_{len(out)+1}",
            kind="axiom_leak",
            lane=ShadowLane.FALSITY,
            locus="trust_basis",
            witness="Forbidden axiom declaration appears in Lean code.",
            severity="error",
            repairability=Repairability.POLICY_BLOCKED,
            blocks_validation=True,
            suggested_patch_kind="no_patch",
            diagnostic_source="shadowhott_fingerprint",
            bilattice_label=BOTTOM_L,
        ))
    return out


def label_for_obstruction(kind: str, severity: str) -> BilatticeValue:
    lane = lane_for_kind(kind)
    if lane == ShadowLane.FALSITY:
        return BOTTOM_L
    if lane == ShadowLane.TRUTH:
        return TOP_L
    return NEITHER_L


def lane_for_kind(kind: str) -> ShadowLane:
    kind = kind.lower()
    if kind in {"theorem_drift", "axiom_leak", "sorry_leak", "security_rejection"}:
        return ShadowLane.FALSITY
    if kind in {"lean_not_available", "timeout"}:
        return ShadowLane.BOUNDARY
    if kind in {
        "unknown_identifier", "unsolved_goal", "type_mismatch", "missing_import",
        "missing_typeclass_instance", "unsupported_natural_language", "unknown_lean_failure",
    }:
        return ShadowLane.BOUNDARY
    return ShadowLane.BOUNDARY


def repairability_for_kind(kind: str) -> Repairability:
    kind = kind.lower()
    if kind in {"unknown_identifier", "missing_import"}:
        return Repairability.RETRIEVAL_GUIDED
    if kind in {"unsolved_goal", "type_mismatch", "missing_typeclass_instance"}:
        return Repairability.LLM_GUIDED
    if kind == "theorem_drift":
        return Repairability.UNPATCHABLE
    if kind in {"axiom_leak", "sorry_leak", "security_rejection"}:
        return Repairability.POLICY_BLOCKED
    if kind in {"lean_not_available", "timeout"}:
        return Repairability.ENVIRONMENTAL
    return Repairability.LLM_GUIDED


def blocks_validation(kind: str, severity: str) -> bool:
    kind = kind.lower()
    severity = severity.lower()
    if severity == "error":
        return True
    if kind in {"theorem_drift", "axiom_leak", "sorry_leak", "security_rejection"}:
        return True
    return False


def suggested_patch_for_kind(kind: str) -> str:
    kind = kind.lower()
    mapping = {
        "unknown_identifier": "request_llm_rewrite_with_retrieval",
        "missing_import": "add_import",
        "unsolved_goal": "replace_tactic",
        "type_mismatch": "replace_tactic",
        "missing_typeclass_instance": "request_llm_rewrite",
        "theorem_drift": "reject_drift",
        "axiom_leak": "no_patch",
        "sorry_leak": "no_patch",
        "security_rejection": "no_patch",
        "lean_not_available": "environment_fix",
        "timeout": "environment_or_search_limit",
    }
    return mapping.get(kind, "request_llm_rewrite")


def locus_for_diagnostic(d: dict[str, Any]) -> str:
    line = d.get("line")
    col = d.get("column")
    if line is not None:
        return f"lean:{line}:{col if col is not None else 0}"
    return str(d.get("source", "unknown"))


def boundary_bias(obstructions: list[ShadowObstruction], lean_status: str, status: str) -> float:
    bias = 0.0
    if any(o.lane == ShadowLane.BOUNDARY for o in obstructions):
        bias += 1.0
    if status in {"needs_repair", "unchecked", "error"}:
        bias += 0.5
    if lean_status in {"not_available", "timeout", "not_run"}:
        bias += 1.0
    return bias


def compute_global_label(
    proof_label: BilatticeValue,
    diagnostics: list[dict[str, Any]],
    obstructions: list[ShadowObstruction],
    lean_status: str,
    status: str,
    certificate: Any,
) -> BilatticeValue:
    hard_falsity = any(o.lane == ShadowLane.FALSITY and o.blocks_validation for o in obstructions)
    boundary_block = any(o.lane == ShadowLane.BOUNDARY and o.blocks_validation for o in obstructions)
    lean_accepted = lean_status == "accepted" and status == "ok"

    if lean_accepted and hard_falsity:
        return BOTH_L
    if lean_accepted and proof_label.refutation:
        return BOTH_L
    if lean_accepted:
        return TOP_L
    if hard_falsity or proof_label == BOTTOM_L:
        return BOTTOM_L
    if proof_label == BOTH_L:
        return BOTH_L
    if boundary_block or lean_status in {"not_available", "timeout", "not_run"} or status in {"unchecked", "error", "needs_repair"}:
        return NEITHER_L
    return NEITHER_L


def compute_verdict(label: BilatticeValue, valuation: TriValSummary, obstructions: list[ShadowObstruction], lean_status: str, status: str) -> ShadowVerdict:
    label = BilatticeValue.from_label(label)
    if label == BOTH_L:
        return ShadowVerdict.HUMAN_REVIEW
    if label == TOP_L and lean_status == "accepted" and status == "ok" and not any(o.blocks_validation for o in obstructions):
        return ShadowVerdict.ACCEPT
    if label == BOTTOM_L:
        return ShadowVerdict.REJECT
    if any(
        o.lane == ShadowLane.FALSITY
        and o.blocks_validation
        and o.repairability in {Repairability.UNPATCHABLE, Repairability.POLICY_BLOCKED}
        for o in obstructions
    ):
        return ShadowVerdict.REJECT
    if lean_status in {"not_available", "timeout", "not_run"} and status in {"unchecked", "error"}:
        return ShadowVerdict.UNCHECKED
    return ShadowVerdict.REPAIR


# ---------------------------------------------------------------------------
# Patch morphisms and conservation
# ---------------------------------------------------------------------------


def patches_to_morphisms(
    patches: list[Any],
    obstructions: list[ShadowObstruction],
    fingerprint_preserved: bool,
    source_label: BilatticeValue = NEITHER_L,
    target_label: BilatticeValue = NEITHER_L,
) -> list[PatchMorphism]:
    out = []
    obstruction_ids = [o.id for o in obstructions]

    if not patches:
        for idx, o in enumerate(obstructions):
            kind = o.suggested_patch_kind or "no_patch"
            theorem_safe = (
                fingerprint_preserved
                and o.lane == ShadowLane.BOUNDARY
                and o.repairability not in {Repairability.UNPATCHABLE, Repairability.POLICY_BLOCKED}
                and kind not in {"reject_drift", "no_patch"}
            )
            out.append(PatchMorphism(
                id=f"mu_{idx+1}",
                kind=kind,
                source_state="S",
                target_state="S_prime" if theorem_safe else None,
                theorem_safe=theorem_safe,
                fingerprint_preserved=fingerprint_preserved,
                description=f"Synthesized ShadowHoTT patch morphism for obstruction {o.id}: {o.kind} -> {kind}.",
                obstruction_ids=[o.id],
                permitted_delta=permitted_delta_for_patch(kind),
                source_label=source_label,
                target_label=target_label,
                conservation_checked=o.bilattice_label.nonreal,
                conservation_ok=True if o.bilattice_label.nonreal else None,
            ))
        return out

    for idx, p in enumerate(patches):
        if isinstance(p, Patch):
            kind = str(p.kind.value if hasattr(p.kind, "value") else p.kind)
            desc = p.description
            drift_diags = [d for d in p.diagnostics if getattr(d, "kind", None) in {ObstructionKind.THEOREM_DRIFT, ObstructionKind.AXIOM_LEAK, ObstructionKind.SORRY_LEAK}]
            theorem_safe = fingerprint_preserved and not drift_diags and kind not in {"reject_drift", "no_patch"}
        elif isinstance(p, dict):
            kind = str(p.get("kind", "unknown"))
            desc = str(p.get("description", ""))
            theorem_safe = fingerprint_preserved and kind not in {"reject_drift", "no_patch"}
        else:
            kind = "unknown"
            desc = str(p)
            theorem_safe = fingerprint_preserved

        out.append(PatchMorphism(
            id=f"mu_{idx+1}",
            kind=kind,
            source_state="S",
            target_state="S_prime" if theorem_safe else None,
            theorem_safe=theorem_safe,
            fingerprint_preserved=fingerprint_preserved,
            description=desc,
            obstruction_ids=obstruction_ids,
            permitted_delta=permitted_delta_for_patch(kind),
            source_label=source_label,
            target_label=target_label,
            conservation_checked=True,
            conservation_ok=theorem_safe or kind in {"reject_drift", "no_patch"},
        ))
    return out


def compose_patches(patches: list[PatchMorphism]) -> PatchMorphism | None:
    if not patches:
        return None
    acc = patches[0]
    for p in patches[1:]:
        acc = acc.compose(p)
    return acc


def retrieval_patch_morphism(obstructions: list[ShadowObstruction], source_label: BilatticeValue = NEITHER_L, target_label: BilatticeValue = NEITHER_L) -> PatchMorphism:
    return PatchMorphism(
        id="mu_retrieval",
        kind="request_llm_rewrite_with_retrieval",
        source_state="S",
        target_state="S_prime_candidate",
        theorem_safe=True,
        fingerprint_preserved=True,
        description="Use retrieval-augmented context to produce a revised DraftProposal while preserving theorem fingerprint.",
        obstruction_ids=[o.id for o in obstructions],
        permitted_delta=["proof_body", "allowed_imports", "local_lemmas", "proof_graph_boundary_notes"],
        source_label=source_label,
        target_label=target_label,
        conservation_checked=True,
        conservation_ok=True,
    )


def permitted_delta_for_patch(kind: str) -> list[str]:
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


def check_J_conservation(before: ShadowHoTTState, after: ShadowHoTTState, morphism: PatchMorphism) -> ConservationReport:
    """
    No-Glutty-J runtime monitor.

    If μ only touches glutty/gap regions, it may not create a new classical path
    to a claim that had no classical path before.
    """
    if morphism.source_label not in {BOTH_L, NEITHER_L}:
        return ConservationReport(status="not_applicable")
    before_targets = before.classical_targets()
    violations: list[str] = []
    checked = 0
    for node in after.proof_graph:
        for path in paths_from_node(node, strict=False):
            checked += 1
            if path.label.classical and path.target not in before_targets:
                violations.append(f"new classical path {path.id} to {path.target} created from non-real source label {morphism.source_label.pretty}")
    return ConservationReport(status="ok" if not violations else "violation", violations=violations, checked_paths=checked)


def has_hard_drift(obstructions: list[ShadowObstruction]) -> bool:
    return any(o.kind in {"theorem_drift", "axiom_leak", "sorry_leak", "security_rejection"} and o.blocks_validation for o in obstructions)


def certificate_status(certificate: Any, lean_status: str, status: str, label: BilatticeValue) -> str:
    if certificate and lean_status == "accepted" and status == "ok" and label == TOP_L:
        return "accepted_by_lean_top"
    if certificate and label == BOTH_L:
        return "accepted_by_lean_glutty_human_review"
    if lean_status == "accepted" and label == BOTH_L:
        return "lean_accepted_with_refutation"
    if lean_status == "accepted":
        return "lean_accepted_without_top_certificate"
    if lean_status in {"not_available", "not_run", "timeout"}:
        return "not_checked"
    return "not_accepted"


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def state_id_from_payload(payload: dict[str, Any]) -> str:
    basis = json.dumps({
        "theorem_fingerprint": payload.get("theorem_fingerprint") or (payload.get("draft") or {}).get("theorem_fingerprint"),
        "diagnostics": payload.get("diagnostics", []),
        "lean_status": payload.get("lean_status"),
        "status": payload.get("status"),
        "code": payload.get("final_lean_code") or payload.get("lean_code") or "",
        "proof_graph": payload.get("proof_graph") or [],
    }, ensure_ascii=False, sort_keys=True, default=str)
    return "S_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def coerce_fingerprint(fp: Any) -> Any:
    if isinstance(fp, TheoremFingerprint):
        return fp
    return fp


def strip_comments(code: str) -> str:
    code = re.sub(r"/-.*?-/", "", code, flags=re.S)
    code = re.sub(r"--.*", "", code)
    return code
