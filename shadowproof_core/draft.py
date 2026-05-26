from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .bilattice import BilatticeValue, NEITHER_L
from .schema_validation import strict_bool
from .models import (
    BoundaryLane,
    Diagnostic,
    DiagnosticSeverity,
    FalsityLane,
    LeanDraft,
    ObstructionKind,
    ProofNode,
    ProofPath,
    TheoremFingerprint,
    TruthLane,
)


@dataclass
class DeclaredTrust:
    uses_sorry: bool = False
    uses_axioms: bool = False
    mutates_theorem: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class NLToLeanMap:
    source_step_id: str
    source_text: str
    lean_fragment: str
    intended_claim: str
    confidence: str = "medium"


@dataclass
class DraftProposal:
    proposal_id: str
    source_language: str
    target_system: str
    theorem_name: str
    imports: list[str]
    natural_language_theorem: str
    natural_language_proof: str
    lean_code: str
    theorem_fingerprint: TheoremFingerprint
    proof_graph: list[ProofNode]
    nl_to_lean_map: list[NLToLeanMap]
    declared_trust: DeclaredTrust
    metadata: dict[str, Any] = field(default_factory=dict)


def proposal_from_payload(payload: dict[str, Any]) -> tuple[DraftProposal | None, list[Diagnostic]]:
    """
    Accept either:
      { "draft": { ... } }
    or a raw DraftProposal object.
    """
    raw = payload.get("draft", payload)
    diagnostics: list[Diagnostic] = []

    required = [
        "proposal_id",
        "source_language",
        "target_system",
        "theorem_name",
        "imports",
        "natural_language_theorem",
        "natural_language_proof",
        "lean_code",
        "theorem_fingerprint",
        "proof_graph",
        "nl_to_lean_map",
        "declared_trust",
    ]

    for key in required:
        if key not in raw:
            diagnostics.append(Diagnostic(
                severity=DiagnosticSeverity.ERROR,
                kind=ObstructionKind.UNKNOWN_LEAN_FAILURE,
                message=f"DraftProposal missing required key `{key}`.",
                source="draft_schema",
            ))

    if diagnostics:
        return None, diagnostics

    try:
        fp_raw = raw["theorem_fingerprint"]
        fingerprint = TheoremFingerprint(
            theorem_family=str(fp_raw.get("theorem_family", "")),
            objects=list(fp_raw.get("objects", [])),
            assumptions=list(fp_raw.get("assumptions", [])),
            conclusion=str(fp_raw.get("conclusion", "")),
            forbidden_drift=list(fp_raw.get("forbidden_drift", [])),
            source_theorem=str(fp_raw.get("source_theorem", raw.get("natural_language_theorem", ""))),
        )

        proof_graph = []
        for n in raw.get("proof_graph", []):
            paths = []
            for idx, p_raw in enumerate(n.get("paths", []) or []):
                try:
                    label = BilatticeValue.from_label(p_raw.get("label", NEITHER_L))
                except Exception:
                    label = NEITHER_L
                paths.append(ProofPath(
                    id=str(p_raw.get("id", f"path_{idx+1}")),
                    source=str(p_raw.get("source", "unknown")),
                    target=str(p_raw.get("target", "unknown")),
                    label=label,
                    witness=str(p_raw.get("witness", "")),
                    kind=str(p_raw.get("kind", "path")),
                ))
            proof_graph.append(ProofNode(
                id=str(n.get("id", "")),
                source_text=str(n.get("source_text", "")),
                truth=TruthLane(
                    claim=str(n.get("truth", {}).get("claim", "")),
                    dependencies=list(n.get("truth", {}).get("dependencies", [])),
                    lean_goal=n.get("truth", {}).get("lean_goal"),
                ),
                falsity=FalsityLane(
                    counterconditions=list(n.get("falsity", {}).get("counterconditions", [])),
                    counterexample_hint=n.get("falsity", {}).get("counterexample_hint"),
                ),
                boundary=BoundaryLane(
                    ambiguities=list(n.get("boundary", {}).get("ambiguities", [])),
                    missing_data=list(n.get("boundary", {}).get("missing_data", [])),
                    lean_error_excerpt=n.get("boundary", {}).get("lean_error_excerpt"),
                ),
                paths=paths,
            ))

        maps = []
        for m in raw.get("nl_to_lean_map", []):
            maps.append(NLToLeanMap(
                source_step_id=str(m.get("source_step_id", "")),
                source_text=str(m.get("source_text", "")),
                lean_fragment=str(m.get("lean_fragment", "")),
                intended_claim=str(m.get("intended_claim", "")),
                confidence=str(m.get("confidence", "medium")),
            ))

        trust_raw = raw.get("declared_trust", {})
        trust = DeclaredTrust(
            uses_sorry=strict_bool(trust_raw.get("uses_sorry"), False, field="declared_trust.uses_sorry"),
            uses_axioms=strict_bool(trust_raw.get("uses_axioms"), False, field="declared_trust.uses_axioms"),
            mutates_theorem=strict_bool(trust_raw.get("mutates_theorem"), False, field="declared_trust.mutates_theorem"),
            notes=list(trust_raw.get("notes", [])),
        )

        proposal = DraftProposal(
            proposal_id=str(raw["proposal_id"]),
            source_language=str(raw["source_language"]),
            target_system=str(raw["target_system"]),
            theorem_name=str(raw["theorem_name"]),
            imports=list(raw["imports"]),
            natural_language_theorem=str(raw["natural_language_theorem"]),
            natural_language_proof=str(raw["natural_language_proof"]),
            lean_code=str(raw["lean_code"]),
            theorem_fingerprint=fingerprint,
            proof_graph=proof_graph,
            nl_to_lean_map=maps,
            declared_trust=trust,
            metadata=dict(raw.get("metadata", {})),
        )
    except Exception as e:
        return None, [Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.UNKNOWN_LEAN_FAILURE,
            message=f"DraftProposal parse error: {e}",
            source="draft_schema",
        )]

    diagnostics.extend(validate_proposal_static(proposal))
    return proposal, diagnostics


def validate_proposal_static(proposal: DraftProposal) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if proposal.target_system != "lean4":
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.UNKNOWN_LEAN_FAILURE,
            message="Only target_system='lean4' is supported.",
            source="draft_schema",
        ))

    if proposal.theorem_name and proposal.theorem_name not in proposal.lean_code:
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.WARNING,
            kind=ObstructionKind.UNKNOWN_LEAN_FAILURE,
            message="The declared theorem_name does not appear in lean_code.",
            source="draft_schema",
        ))

    for imp in proposal.imports:
        if f"import {imp}" not in proposal.lean_code:
            diagnostics.append(Diagnostic(
                severity=DiagnosticSeverity.WARNING,
                kind=ObstructionKind.MISSING_IMPORT,
                message=f"Declared import `{imp}` does not appear in lean_code.",
                source="draft_schema",
            ))

    lower_code = proposal.lean_code.lower()

    if "sorry" in lower_code and not proposal.declared_trust.uses_sorry:
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.SORRY_LEAK,
            message="lean_code contains `sorry`, but declared_trust.uses_sorry=false.",
            source="draft_schema",
        ))

    if re.search(r"^\s*axiom\s+", proposal.lean_code, flags=re.M) and not proposal.declared_trust.uses_axioms:
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.AXIOM_LEAK,
            message="lean_code declares an axiom, but declared_trust.uses_axioms=false.",
            source="draft_schema",
        ))

    if proposal.declared_trust.mutates_theorem:
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.THEOREM_DRIFT,
            message="DraftProposal declares that it mutates the theorem.",
            source="draft_schema",
        ))

    diagnostics.extend(proposal.theorem_fingerprint.diff_summary(proposal.lean_code))

    theorem_header = extract_theorem_header(proposal.lean_code, proposal.theorem_name)
    if theorem_header:
        header_lower = theorem_header.lower()
        for obj in proposal.theorem_fingerprint.objects:
            if obj.strip() and simple_missing(obj, header_lower):
                diagnostics.append(Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.THEOREM_DRIFT,
                    message=f"Fingerprint object is missing from Lean theorem header: {obj}",
                    source="theorem_lock",
                ))
        if proposal.theorem_fingerprint.conclusion:
            norm_conc = normalize_math(proposal.theorem_fingerprint.conclusion)
            norm_head = normalize_math(theorem_header)
            if norm_conc not in norm_head:
                diagnostics.append(Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.THEOREM_DRIFT,
                    message="Fingerprint conclusion was not found verbatim in normalized Lean theorem header.",
                    source="theorem_lock",
                ))
    else:
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            kind=ObstructionKind.THEOREM_DRIFT,
            message="Could not extract theorem header for theorem-lock comparison.",
            source="theorem_lock",
        ))

    return diagnostics


def draft_to_lean_draft(proposal: DraftProposal) -> LeanDraft:
    return LeanDraft(
        name=proposal.theorem_name,
        code=proposal.lean_code,
        fingerprint=proposal.theorem_fingerprint,
        proof_graph=proposal.proof_graph,
    )


def proposal_fingerprint_hash(proposal: DraftProposal) -> str:
    blob = "\n".join([
        proposal.theorem_name,
        proposal.theorem_fingerprint.theorem_family,
        "|".join(proposal.theorem_fingerprint.objects),
        "|".join(proposal.theorem_fingerprint.assumptions),
        proposal.theorem_fingerprint.conclusion,
        proposal.natural_language_theorem,
    ])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def extract_theorem_header(code: str, theorem_name: str) -> str | None:
    """
    Extracts text from `theorem name` through the `:=` before the proof.
    This is intentionally lightweight, not a Lean parser.
    """
    if not theorem_name:
        pattern = r"\b(?:theorem|lemma|example)\b(.*?):="
    else:
        pattern = rf"\b(?:theorem|lemma)\s+{re.escape(theorem_name)}\b(.*?):="
    m = re.search(pattern, code, flags=re.S)
    if not m:
        return None
    return m.group(0)


def normalize_math(s: str) -> str:
    return re.sub(r"\s+", "", s).replace("·", "*")


def simple_missing(obj: str, header_lower: str) -> bool:
    """
    Weak string check used only to produce warnings.
    """
    cleaned = obj.lower().strip()
    if cleaned.startswith("["):
        return cleaned.replace(" ", "") not in header_lower.replace(" ", "")
    if ":" in cleaned:
        left = cleaned.split(":", 1)[0].strip()
        return left not in header_lower
    return cleaned not in header_lower
