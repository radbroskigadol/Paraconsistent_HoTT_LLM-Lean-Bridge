from __future__ import annotations

from .lean_runner import LeanRunner
from .env_info import certificate_environment_payload, code_hash, stable_json_hash
from .models import (
    Diagnostic,
    DiagnosticSeverity,
    LeanDraft,
    LeanStatus,
    NLProblem,
    ObstructionKind,
    PatchKind,
    PolicySpec,
    SecurityLevel,
    TargetSpec,
    ToolResponse,
    ToolStatus,
    ValidationCertificate,
)
from .repair import ShadowHoTTRepairEngine
from .repair_selection import choose_patch_by_bilattice
from .security import SecurityPolicy
from .translator import LLMBridgeTranslator
from .shadowhott import build_shadowhott_state, compute_node_labels
from .bilattice import TOP_L, BOTTOM_L, BOTH_L, NEITHER_L
from .repair_retrieval import compile_retrieval_augmented_repair_context
from .prompting import compile_repair_prompt


class ShadowProofBridge:
    def __init__(self):
        self.translator = LLMBridgeTranslator()
        self.repair_engine = ShadowHoTTRepairEngine()

    def validate(self, request_id: str, problem: NLProblem, target: TargetSpec, policy: PolicySpec, direct_lean_code: str | None = None) -> ToolResponse:
        if direct_lean_code:
            draft = direct_code_to_draft(request_id, direct_lean_code, target, problem)
        else:
            draft = self.translator.translate(problem, target, request_id=request_id)

        if draft.fingerprint.theorem_family == "unsupported":
            return ToolResponse(
                request_id=request_id,
                tool="shadowproof_validate",
                status=ToolStatus.REJECTED,
                lean_status=LeanStatus.NOT_RUN,
                diagnostics=[Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    kind=ObstructionKind.UNSUPPORTED_NL,
                    message="Unsupported natural-language input. Provide direct Lean code or an LLM DraftProposal.",
                    source="pipeline",
                )],
                theorem_fingerprint=draft.fingerprint,
                proof_graph=draft.proof_graph,
                final_lean_code=draft.code if policy.return_code else None,
            )

        runner = LeanRunner(
            command=None,  # deployment-owned via SHADOWPROOF_LEAN_CMD; never request-controlled
            timeout_seconds=policy.timeout_seconds,
            security_policy=SecurityPolicy(
                level=policy.security_level if isinstance(policy.security_level, SecurityLevel) else SecurityLevel(policy.security_level),
                allow_sorry=target.allow_sorry,
            ),
        )

        patches = []
        current = draft
        last_result = None

        for iteration in range(policy.max_iterations):
            drift = current.fingerprint.diff_summary(current.code)
            if drift and not policy.allow_theorem_mutation:
                return ToolResponse(
                    request_id=request_id,
                    tool="shadowproof_validate",
                    status=ToolStatus.REJECTED,
                    lean_status=LeanStatus.NOT_RUN,
                    diagnostics=drift,
                    theorem_fingerprint=current.fingerprint,
                    proof_graph=current.proof_graph if policy.return_proof_graph else [],
                    patches=patches,
                    final_lean_code=current.code if policy.return_code else None,
                )

            result = runner.check_code(current.code)
            last_result = result

            if result.ok:
                env = certificate_environment_payload(None, None, timeout_seconds=10)
                node_labels = compute_node_labels(current.proof_graph)
                has_refutation_path = any(label.refutation for label in node_labels.values())
                cert_label = BOTH_L if has_refutation_path else TOP_L
                cert = ValidationCertificate(
                    theorem_name=current.name,
                    accepted_by_lean=True,
                    axiom_report=result.axiom_report,
                    theorem_fingerprint=current.fingerprint,
                    notes=["Lean accepted the theorem under the supplied environment and policy."],
                    bilattice_label=cert_label,
                    lean_version=env.get("lean_version"),
                    lake_version=env.get("lake_version"),
                    lean_toolchain=env.get("lean_toolchain"),
                    mathlib_revision=env.get("mathlib_revision"),
                    project_manifest_hash=env.get("project_manifest_hash"),
                    lakefile_hash=env.get("lakefile_hash"),
                    code_hash=code_hash(current.code),
                    theorem_fingerprint_hash=stable_json_hash(current.fingerprint.__dict__),
                    security_policy={
                        "security_level": str(policy.security_level.value if hasattr(policy.security_level, "value") else policy.security_level),
                        "allow_sorry": target.allow_sorry,
                        "allow_theorem_mutation": policy.allow_theorem_mutation,
                    },
                    elapsed_ms=result.elapsed_ms,
                )
                return ToolResponse(
                    request_id=request_id,
                    tool="shadowproof_validate",
                    status=ToolStatus.HUMAN_REVIEW if cert_label == BOTH_L else ToolStatus.OK,
                    lean_status=result.lean_status,
                    diagnostics=result.diagnostics,
                    theorem_fingerprint=current.fingerprint,
                    proof_graph=current.proof_graph if policy.return_proof_graph else [],
                    patches=patches,
                    certificate=cert,
                    final_lean_code=current.code if policy.return_code else None,
                    raw_lean_stdout=result.stdout,
                    raw_lean_stderr=result.stderr,
                )

            if result.lean_status in {LeanStatus.NOT_AVAILABLE, LeanStatus.TIMEOUT, LeanStatus.NOT_RUN}:
                return ToolResponse(
                    request_id=request_id,
                    tool="shadowproof_validate",
                    status=ToolStatus.UNCHECKED if result.lean_status == LeanStatus.NOT_AVAILABLE else ToolStatus.ERROR,
                    lean_status=result.lean_status,
                    diagnostics=result.diagnostics,
                    theorem_fingerprint=current.fingerprint,
                    proof_graph=current.proof_graph if policy.return_proof_graph else [],
                    patches=patches,
                    final_lean_code=current.code if policy.return_code else None,
                    raw_lean_stdout=result.stdout,
                    raw_lean_stderr=result.stderr,
                )

            candidates = self.repair_engine.candidate_patches(current, result, iteration, policy.allow_theorem_mutation)
            patch, _candidate_assessments = choose_patch_by_bilattice(current, result, candidates)
            patches.append(patch)

            if patch.kind in {PatchKind.REJECT_DRIFT, PatchKind.REQUEST_LLM_REWRITE, PatchKind.NO_PATCH} or not patch.new_code:
                return ToolResponse(
                    request_id=request_id,
                    tool="shadowproof_validate",
                    status=ToolStatus.NEEDS_REPAIR if patch.kind == PatchKind.REQUEST_LLM_REWRITE else ToolStatus.REJECTED,
                    lean_status=result.lean_status,
                    diagnostics=result.diagnostics + patch.diagnostics,
                    theorem_fingerprint=current.fingerprint,
                    proof_graph=current.proof_graph if policy.return_proof_graph else [],
                    patches=patches,
                    final_lean_code=current.code if policy.return_code else None,
                    raw_lean_stdout=result.stdout,
                    raw_lean_stderr=result.stderr,
                )

            current = LeanDraft(
                name=current.name,
                code=patch.new_code,
                fingerprint=current.fingerprint,
                proof_graph=current.proof_graph,
            )

        diagnostics = []
        if last_result:
            diagnostics.extend(last_result.diagnostics)
        diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.WARNING,
            kind=ObstructionKind.UNSOLVED_GOAL,
            message="Maximum repair iterations reached.",
            source="pipeline",
        ))

        return ToolResponse(
            request_id=request_id,
            tool="shadowproof_validate",
            status=ToolStatus.NEEDS_REPAIR,
            lean_status=last_result.lean_status if last_result else LeanStatus.NOT_RUN,
            diagnostics=diagnostics,
            theorem_fingerprint=current.fingerprint,
            proof_graph=current.proof_graph if policy.return_proof_graph else [],
            patches=patches,
            final_lean_code=current.code if policy.return_code else None,
            raw_lean_stdout=last_result.stdout if last_result else None,
            raw_lean_stderr=last_result.stderr if last_result else None,
        )


def direct_code_to_draft(request_id: str, code: str, target: TargetSpec, problem: NLProblem) -> LeanDraft:
    from .translator import safe_theorem_name
    from .models import TheoremFingerprint, ProofNode, ProofPath, TruthLane, FalsityLane, BoundaryLane

    name = target.theorem_name or safe_theorem_name(request_id)
    fingerprint = TheoremFingerprint(
        theorem_family="direct_lean",
        source_theorem=problem.theorem or "direct Lean code",
        conclusion="unknown/direct Lean",
        forbidden_drift=["axiom", "unsafe", "#eval", "run_cmd"] + ([] if target.allow_sorry else ["sorry"]),
    )
    return LeanDraft(
        name=name,
        code=code,
        fingerprint=fingerprint,
        proof_graph=[ProofNode(
            id="direct",
            source_text=problem.proof or code[:500],
            truth=TruthLane(claim="Direct Lean proof attempt supplied by caller."),
            falsity=FalsityLane(counterconditions=["Code may not represent the intended informal theorem."]),
            boundary=BoundaryLane(missing_data=["No full semantic fingerprint extracted from direct Lean code."]),
            paths=[ProofPath(
                id="path_direct_unchecked",
                source="direct_input",
                target="lean_candidate",
                label=NEITHER_L,
                witness="Direct Lean code has not been semantically fingerprinted by the translator.",
                kind="gap",
            )],
        )],
    )
