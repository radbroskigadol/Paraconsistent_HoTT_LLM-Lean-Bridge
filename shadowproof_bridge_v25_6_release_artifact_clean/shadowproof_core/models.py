from __future__ import annotations

from dataclasses import dataclass, field, asdict
import re
from enum import Enum
from typing import Any, Optional

from .bilattice import BilatticeValue, TOP_L, BOTTOM_L, BOTH_L, NEITHER_L


class ToolStatus(str, Enum):
    OK = "ok"
    REJECTED = "rejected"
    ERROR = "error"
    NEEDS_REPAIR = "needs_repair"
    UNCHECKED = "unchecked"
    HUMAN_REVIEW = "human_review"


class LeanStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_RUN = "not_run"
    NOT_AVAILABLE = "not_available"
    TIMEOUT = "timeout"


class SecurityLevel(str, Enum):
    CONSERVATIVE = "conservative"
    PERMISSIVE = "permissive"


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ObstructionKind(str, Enum):
    NONE = "none"
    SECURITY_REJECTION = "security_rejection"
    UNKNOWN_IDENTIFIER = "unknown_identifier"
    UNSOLVED_GOAL = "unsolved_goal"
    TYPE_MISMATCH = "type_mismatch"
    MISSING_IMPORT = "missing_import"
    MISSING_TYPECLASS_INSTANCE = "missing_typeclass_instance"
    THEOREM_DRIFT = "theorem_drift"
    AXIOM_LEAK = "axiom_leak"
    SORRY_LEAK = "sorry_leak"
    UNSUPPORTED_NL = "unsupported_natural_language"
    LEAN_NOT_AVAILABLE = "lean_not_available"
    TIMEOUT = "timeout"
    UNKNOWN_LEAN_FAILURE = "unknown_lean_failure"


class PatchKind(str, Enum):
    REPLACE_TACTIC = "replace_tactic"
    ADD_IMPORT = "add_import"
    ADD_LOCAL_LEMMA = "add_local_lemma"
    REJECT_DRIFT = "reject_drift"
    REQUEST_LLM_REWRITE = "request_llm_rewrite"
    NO_PATCH = "no_patch"


@dataclass
class Diagnostic:
    severity: DiagnosticSeverity
    kind: ObstructionKind
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    source: str = "shadowproof"

    def to_dict(self) -> dict[str, Any]:
        return enum_clean(asdict(self))


@dataclass
class TargetSpec:
    system: str = "lean4"
    imports: list[str] = field(default_factory=lambda: ["Mathlib"])
    lean_command: Optional[str] = None
    allow_sorry: bool = False
    theorem_name: Optional[str] = None


@dataclass
class PolicySpec:
    max_iterations: int = 4
    timeout_seconds: int = 30
    allow_theorem_mutation: bool = False
    security_level: SecurityLevel = SecurityLevel.CONSERVATIVE
    return_code: bool = True
    return_proof_graph: bool = True
    return_shadowhott_state: bool = True
    auto_repair_context: bool = False
    auto_retrieve: bool = True


@dataclass
class NLProblem:
    theorem: str
    proof: str = ""
    context: str = ""


@dataclass
class TheoremFingerprint:
    theorem_family: str
    objects: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    conclusion: str = ""
    forbidden_drift: list[str] = field(default_factory=list)
    source_theorem: str = ""

    def diff_summary(self, code: str) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        lower = code.lower()
        stripped = strip_lean_comments_for_fingerprint(code)
        stripped_lower = stripped.lower()

        for token in self.forbidden_drift:
            token_lower = token.lower().strip()

            # `#print axioms theorem_name` is an audit command, not an axiom leak.
            # Actual axiom leakage is checked by declaration regex below.
            if token_lower in {"axiom", "axioms"}:
                continue

            if token_lower == "sorry":
                # handled below so the diagnostic kind is SORRY_LEAK
                continue

            if token_lower and token_lower in stripped_lower:
                diagnostics.append(Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.THEOREM_DRIFT,
                    message=f"Forbidden theorem-drift token detected: {token}",
                    source="theorem_lock",
                ))

        if re.search(r"\bsorry\b", stripped_lower):
            diagnostics.append(Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                kind=ObstructionKind.SORRY_LEAK,
                message="Draft contains `sorry`, which is forbidden by default.",
                source="theorem_lock",
            ))

        if re.search(r"^\s*axiom\s+", stripped, flags=re.M):
            diagnostics.append(Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                kind=ObstructionKind.AXIOM_LEAK,
                message="Draft contains an axiom declaration.",
                source="theorem_lock",
            ))

        return diagnostics


@dataclass
class TruthLane:
    claim: str
    dependencies: list[str] = field(default_factory=list)
    lean_goal: Optional[str] = None


@dataclass
class FalsityLane:
    counterconditions: list[str] = field(default_factory=list)
    counterexample_hint: Optional[str] = None


@dataclass
class BoundaryLane:
    ambiguities: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    lean_error_excerpt: Optional[str] = None


@dataclass
class ProofPath:
    """
    A labelled path in the ShadowHoTT proof graph.

    The semantic valuation is the four-valued bilattice label L = 2 × 2.
    Reflexivity paths must be ⊤_L.  Composition uses ∧_L.
    """

    id: str
    source: str
    target: str
    label: BilatticeValue = TOP_L
    witness: str = ""
    kind: str = "path"

    @classmethod
    def refl(cls, point: str, id: str | None = None, witness: str = "J/reflexivity") -> "ProofPath":
        return cls(id=id or f"refl_{safe_identifier(point)}", source=point, target=point, label=TOP_L, witness=witness, kind="refl")

    @property
    def is_refl(self) -> bool:
        return self.kind == "refl" or self.source == self.target

    def compose(self, other: "ProofPath", id: str | None = None) -> "ProofPath":
        if self.target != other.source:
            raise ValueError(f"cannot compose path {self.id}: {self.source}->{self.target} with {other.id}: {other.source}->{other.target}")
        return ProofPath(
            id=id or f"{self.id}_then_{other.id}",
            source=self.source,
            target=other.target,
            label=self.label.meet(other.label),
            witness="; ".join(x for x in [self.witness, other.witness] if x),
            kind="composition",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label.to_dict(),
            "witness": self.witness,
            "kind": self.kind,
        }


@dataclass
class ProofNode:
    id: str
    source_text: str
    truth: TruthLane
    falsity: FalsityLane
    boundary: BoundaryLane
    obstruction: ObstructionKind = ObstructionKind.NONE
    paths: list[ProofPath] = field(default_factory=list)

    def composed_label(self) -> BilatticeValue:
        if not self.paths:
            if self.obstruction in {ObstructionKind.THEOREM_DRIFT, ObstructionKind.AXIOM_LEAK, ObstructionKind.SORRY_LEAK, ObstructionKind.SECURITY_REJECTION}:
                return BOTTOM_L
            if self.obstruction != ObstructionKind.NONE:
                return NEITHER_L
            return TOP_L
        acc = self.paths[0].label
        for path in self.paths[1:]:
            acc = acc.meet(path.label)
        return acc


def safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned[:64] or "point"


@dataclass
class LeanDraft:
    name: str
    code: str
    fingerprint: TheoremFingerprint
    proof_graph: list[ProofNode] = field(default_factory=list)


@dataclass
class LeanRunResult:
    lean_status: LeanStatus
    ok: bool
    stdout: str = ""
    stderr: str = ""
    diagnostics: list[Diagnostic] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    elapsed_ms: Optional[int] = None
    axiom_report: Optional[str] = None


@dataclass
class Patch:
    kind: PatchKind
    description: str
    new_code: Optional[str] = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class ValidationCertificate:
    theorem_name: str
    accepted_by_lean: bool
    axiom_report: Optional[str]
    theorem_fingerprint: TheoremFingerprint
    notes: list[str] = field(default_factory=list)
    bilattice_label: BilatticeValue = NEITHER_L
    truth_coordinate: bool = False
    refutation_coordinate: bool = False
    designated: bool = False
    human_review_required: bool = False
    lean_version: Optional[str] = None
    lake_version: Optional[str] = None
    lean_toolchain: Optional[str] = None
    mathlib_revision: Optional[str] = None
    project_manifest_hash: Optional[str] = None
    lakefile_hash: Optional[str] = None
    code_hash: Optional[str] = None
    theorem_fingerprint_hash: Optional[str] = None
    security_policy: Optional[dict[str, Any]] = None
    elapsed_ms: Optional[int] = None

    def __post_init__(self):
        label = BilatticeValue.from_label(self.bilattice_label)
        object.__setattr__(self, "bilattice_label", label)
        object.__setattr__(self, "truth_coordinate", label.truth)
        object.__setattr__(self, "refutation_coordinate", label.refutation)
        object.__setattr__(self, "designated", label.designated)
        object.__setattr__(self, "human_review_required", label == BOTH_L)


@dataclass
class ToolResponse:
    request_id: str
    tool: str
    status: ToolStatus
    lean_status: LeanStatus = LeanStatus.NOT_RUN
    diagnostics: list[Diagnostic] = field(default_factory=list)
    theorem_fingerprint: Optional[TheoremFingerprint] = None
    proof_graph: list[ProofNode] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    certificate: Optional[ValidationCertificate] = None
    final_lean_code: Optional[str] = None
    raw_lean_stdout: Optional[str] = None
    raw_lean_stderr: Optional[str] = None
    shadowhott_state: Optional[dict[str, Any]] = None
    repair_context: Optional[dict[str, Any]] = None
    compiled_repair_prompt: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return enum_clean(asdict(self))


def enum_clean(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BilatticeValue):
        return value.to_dict()
    if hasattr(value, "to_dict") and value.__class__.__name__ == "ProofPath":
        return value.to_dict()
    if isinstance(value, list):
        return [enum_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: enum_clean(v) for k, v in value.items()}
    return value


def strip_lean_comments_for_fingerprint(code: str) -> str:
    """
    Lightweight comment stripper used by theorem-lock token checks.
    It intentionally allows `#print axioms` while still detecting actual axiom declarations.
    """
    code = re.sub(r"/-.*?-/", "", code, flags=re.S)
    code = re.sub(r"--.*", "", code)
    return code
