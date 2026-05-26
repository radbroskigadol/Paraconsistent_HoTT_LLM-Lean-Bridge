from __future__ import annotations
from .service_status import liveness, readiness, service_status, error_taxonomy, make_trace
from .acquisition import acquisition_packet, claims_boundary as acquisition_claims_boundary, due_diligence_checklist, investor_deck_index
from .release_report import generate_release_report, release_checklist
from .proof_promotion import submit_proof_artifact, proof_artifact_status, proof_artifact_registry, attach_proof_validation, promote_proof_artifact, record_proof_review, create_proof_review_packet, proof_artifact_export
from .domain_promotion import submit_domain_pack, domain_pack_status, domain_pack_registry, promote_domain_pack, record_domain_pack_review, attach_domain_pack_eval, rollback_domain_pack
from .domain_authoring import domain_pack_schema, create_domain_pack, validate_domain_pack, domain_pack_eval_stub, domain_pack_authoring_guide
from .pilot import generate_pilot_plan, integration_checklist, acceptance_criteria, generate_onboarding_packet, adapter_conformance_plan
from .release_gate import release_gate
from .license_scan import license_scan
from .threat_model import threat_model_report
from .openapi import build_openapi_spec
from .model_providers import call_model_provider
from .costs import estimate_cost
from .admin import tenant_report, delete_tenant_data
from .adapters import adapter_catalog
from .config import load_config
from .auth import require_request_allowed
from .observability import metrics_report, prometheus_text, record_metric, MetricEvent, make_proof_lifecycle_trace
from .storage import retention_sweep, store_event
from .review import create_review_packet
from .product import product_readiness_report
from .sandbox import run_lean_worker, sandbox_check


import json
from typing import Any

from .draft import draft_to_lean_draft, proposal_fingerprint_hash, proposal_from_payload
from .env_info import certificate_environment_payload, code_hash, stable_json_hash
from .eval_harness import run_eval_suite
from .lean_runner import LeanRunner
from .learning import LearningConfig, RejectionMemory, make_rejection_record
from .prompting import compile_repair_prompt
from .optimization import OptimizationConfig, OptimizationPolicyEngine, OptimizationStore, event_from_payload, dataclass_to_jsonable
from .retrieval import list_domain_packs, get_domain_pack, retrieve_mathlib_context, index_mathlib_sources, dataclass_to_jsonable as retrieval_jsonable
from .repair_retrieval import retrieve_for_diagnostics, compile_retrieval_augmented_repair_context
from .shadowhott_eval import run_shadowhott_eval_suite
from .regression import run_bridge_regression_suite
from .shadowhott import build_shadowhott_state, audit_shadowhott_state, compute_node_labels
from .models import (
    Diagnostic,
    DiagnosticSeverity,
    LeanStatus,
    NLProblem,
    ObstructionKind,
    PolicySpec,
    SecurityLevel,
    TargetSpec,
    ToolResponse,
    ToolStatus,
    ValidationCertificate,
)
from .pipeline import ShadowProofBridge
from .repair import ShadowHoTTRepairEngine
from .repair_selection import choose_patch_by_bilattice
from .security import SecurityPolicy
from .translator import LLMBridgeTranslator
from .bilattice import TOP_L, BOTH_L, demorgan_order_two_report
from .training_capacity import make_capacity_plan
from .local_simulation import run_local_behavior_simulation
from .schema_validation import strict_bool, strict_int
from .path_guard import resolve_under_allowed_root


def lean_check(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "lean_check"))
    target = parse_target(payload.get("target", {}))
    policy = parse_policy(payload.get("policy", {}))
    code = payload.get("lean_code", "")

    if not isinstance(code, str) or not code.strip():
        return ToolResponse(
            request_id=request_id,
            tool="lean_check",
            status=ToolStatus.ERROR,
            lean_status=LeanStatus.NOT_RUN,
            diagnostics=[Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.UNKNOWN_LEAN_FAILURE, "Missing `lean_code`.", source="tool_api")],
        ).to_dict()

    runner = LeanRunner(
        command=None,  # deployment-owned via SHADOWPROOF_LEAN_CMD; never request-controlled
        timeout_seconds=policy.timeout_seconds,
        security_policy=SecurityPolicy(
            level=policy.security_level if isinstance(policy.security_level, SecurityLevel) else SecurityLevel(policy.security_level),
            allow_sorry=target.allow_sorry,
        ),
    )
    result = runner.check_code(code)

    status = ToolStatus.OK if result.ok else (
        ToolStatus.UNCHECKED if result.lean_status == LeanStatus.NOT_AVAILABLE else ToolStatus.REJECTED
    )

    return ToolResponse(
        request_id=request_id,
        tool="lean_check",
        status=status,
        lean_status=result.lean_status,
        diagnostics=result.diagnostics,
        final_lean_code=code if policy.return_code else None,
        raw_lean_stdout=result.stdout,
        raw_lean_stderr=result.stderr,
    ).to_dict()


def shadowproof_translate(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_translate"))
    target = parse_target(payload.get("target", {}))
    problem = parse_problem(payload.get("nl_problem", {}))

    draft = LLMBridgeTranslator().translate(problem, target, request_id=request_id)

    return ToolResponse(
        request_id=request_id,
        tool="shadowproof_translate",
        status=ToolStatus.OK if draft.fingerprint.theorem_family != "unsupported" else ToolStatus.NEEDS_REPAIR,
        lean_status=LeanStatus.NOT_RUN,
        diagnostics=[] if draft.fingerprint.theorem_family != "unsupported" else [
            Diagnostic(DiagnosticSeverity.WARNING, ObstructionKind.UNSUPPORTED_NL, "No deterministic translation matched.", source="translator")
        ],
        theorem_fingerprint=draft.fingerprint,
        proof_graph=draft.proof_graph,
        final_lean_code=draft.code,
    ).to_dict()


def shadowproof_repair(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_repair"))
    return ToolResponse(
        request_id=request_id,
        tool="shadowproof_repair",
        status=ToolStatus.NEEDS_REPAIR,
        lean_status=LeanStatus.NOT_RUN,
        diagnostics=[Diagnostic(
            DiagnosticSeverity.WARNING,
            ObstructionKind.UNSUPPORTED_NL,
            "Use `shadowproof_validate` or `shadowproof_validate_draft` for stateful repair in v3.",
            source="tool_api",
        )],
    ).to_dict()


def _shadowproof_validate_core(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_validate"))
    target = parse_target(payload.get("target", {}))
    policy = parse_policy(payload.get("policy", {}))
    problem = parse_problem(payload.get("nl_problem", {}))
    direct_code = payload.get("lean_code")

    bridge = ShadowProofBridge()
    response = bridge.validate(
        request_id=request_id,
        problem=problem,
        target=target,
        policy=policy,
        direct_lean_code=direct_code if isinstance(direct_code, str) and direct_code.strip() else None,
    )
    return response.to_dict()


def shadowproof_check_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Check only the DraftProposal shape, declared trust, theorem-lock, and security preflight.
    Does not run Lean.
    """
    request_id = str(payload.get("request_id", "shadowproof_check_draft"))
    target = parse_target(payload.get("target", {}))
    policy = parse_policy(payload.get("policy", {}))

    proposal, diagnostics = proposal_from_payload(payload)
    if proposal is None:
        return ToolResponse(
            request_id=request_id,
            tool="shadowproof_check_draft",
            status=ToolStatus.ERROR,
            lean_status=LeanStatus.NOT_RUN,
            diagnostics=diagnostics,
        ).to_dict()

    sec = SecurityPolicy(
        level=policy.security_level if isinstance(policy.security_level, SecurityLevel) else SecurityLevel(policy.security_level),
        allow_sorry=target.allow_sorry,
    ).preflight(proposal.lean_code)

    all_diagnostics = diagnostics + sec
    status = ToolStatus.OK if not any(d.severity == DiagnosticSeverity.ERROR for d in all_diagnostics) else ToolStatus.REJECTED

    return ToolResponse(
        request_id=request_id,
        tool="shadowproof_check_draft",
        status=status,
        lean_status=LeanStatus.NOT_RUN,
        diagnostics=all_diagnostics + [Diagnostic(
            DiagnosticSeverity.INFO,
            ObstructionKind.NONE,
            f"proposal_fingerprint_hash={proposal_fingerprint_hash(proposal)}",
            source="draft_schema",
        )],
        theorem_fingerprint=proposal.theorem_fingerprint,
        proof_graph=proposal.proof_graph if policy.return_proof_graph else [],
        final_lean_code=proposal.lean_code if policy.return_code else None,
    ).to_dict()


def _shadowproof_validate_draft_core(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate an LLM DraftProposal:
      1. parse proposal
      2. static theorem-lock + declared-trust checks
      3. security preflight
      4. Lean check
      5. guarded repair attempts where deterministic repair exists
    """
    request_id = str(payload.get("request_id", "shadowproof_validate_draft"))
    target = parse_target(payload.get("target", {}))
    policy = parse_policy(payload.get("policy", {}))

    proposal, diagnostics = proposal_from_payload(payload)
    if proposal is None:
        return ToolResponse(
            request_id=request_id,
            tool="shadowproof_validate_draft",
            status=ToolStatus.ERROR,
            lean_status=LeanStatus.NOT_RUN,
            diagnostics=diagnostics,
        ).to_dict()

    if diagnostics and any(d.severity == DiagnosticSeverity.ERROR for d in diagnostics) and not policy.allow_theorem_mutation:
        return ToolResponse(
            request_id=request_id,
            tool="shadowproof_validate_draft",
            status=ToolStatus.REJECTED,
            lean_status=LeanStatus.NOT_RUN,
            diagnostics=diagnostics,
            theorem_fingerprint=proposal.theorem_fingerprint,
            proof_graph=proposal.proof_graph if policy.return_proof_graph else [],
            final_lean_code=proposal.lean_code if policy.return_code else None,
        ).to_dict()

    runner = LeanRunner(
        command=None,  # deployment-owned via SHADOWPROOF_LEAN_CMD; never request-controlled
        timeout_seconds=policy.timeout_seconds,
        security_policy=SecurityPolicy(
            level=policy.security_level if isinstance(policy.security_level, SecurityLevel) else SecurityLevel(policy.security_level),
            allow_sorry=target.allow_sorry,
        ),
    )
    repair = ShadowHoTTRepairEngine()

    current = draft_to_lean_draft(proposal)
    patches = []

    for iteration in range(policy.max_iterations + 1):
        result = runner.check_code(current.code)

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
                notes=[
                    "Lean accepted the DraftProposal theorem.",
                    f"proposal_fingerprint_hash={proposal_fingerprint_hash(proposal)}",
                ],
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
                tool="shadowproof_validate_draft",
                status=ToolStatus.HUMAN_REVIEW if cert_label == BOTH_L else ToolStatus.OK,
                lean_status=result.lean_status,
                diagnostics=diagnostics + result.diagnostics,
                theorem_fingerprint=current.fingerprint,
                proof_graph=current.proof_graph if policy.return_proof_graph else [],
                patches=patches,
                certificate=cert,
                final_lean_code=current.code if policy.return_code else None,
                raw_lean_stdout=result.stdout,
                raw_lean_stderr=result.stderr,
            ).to_dict()

        if result.lean_status in {LeanStatus.NOT_AVAILABLE, LeanStatus.TIMEOUT, LeanStatus.NOT_RUN}:
            return ToolResponse(
                request_id=request_id,
                tool="shadowproof_validate_draft",
                status=ToolStatus.UNCHECKED if result.lean_status == LeanStatus.NOT_AVAILABLE else ToolStatus.ERROR,
                lean_status=result.lean_status,
                diagnostics=diagnostics + result.diagnostics,
                theorem_fingerprint=current.fingerprint,
                proof_graph=current.proof_graph if policy.return_proof_graph else [],
                patches=patches,
                final_lean_code=current.code if policy.return_code else None,
                raw_lean_stdout=result.stdout,
                raw_lean_stderr=result.stderr,
            ).to_dict()

        if iteration >= policy.max_iterations:
            return ToolResponse(
                request_id=request_id,
                tool="shadowproof_validate_draft",
                status=ToolStatus.NEEDS_REPAIR,
                lean_status=result.lean_status,
                diagnostics=diagnostics + result.diagnostics,
                theorem_fingerprint=current.fingerprint,
                proof_graph=current.proof_graph if policy.return_proof_graph else [],
                patches=patches,
                final_lean_code=current.code if policy.return_code else None,
                raw_lean_stdout=result.stdout,
                raw_lean_stderr=result.stderr,
            ).to_dict()

        candidates = repair.candidate_patches(current, result, iteration, policy.allow_theorem_mutation)
        patch, _candidate_assessments = choose_patch_by_bilattice(current, result, candidates)
        patches.append(patch)
        if not patch.new_code:
            return ToolResponse(
                request_id=request_id,
                tool="shadowproof_validate_draft",
                status=ToolStatus.NEEDS_REPAIR,
                lean_status=result.lean_status,
                diagnostics=diagnostics + result.diagnostics + patch.diagnostics,
                theorem_fingerprint=current.fingerprint,
                proof_graph=current.proof_graph if policy.return_proof_graph else [],
                patches=patches,
                final_lean_code=current.code if policy.return_code else None,
                raw_lean_stdout=result.stdout,
                raw_lean_stderr=result.stderr,
            ).to_dict()

        current.code = patch.new_code

    raise AssertionError("unreachable")


def shadowproof_draft_schema(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from pathlib import Path
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "draft_proposal.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))



def shadowproof_record_outcome(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Record a rejection/repair/acceptance outcome into local memory.

    By default this stores hashes and diagnostic fingerprints, not raw theorem text.
    """
    request_id = str(payload.get("request_id", "shadowproof_record_outcome"))
    config = LearningConfig(
        memory_path=payload.get("memory_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        enabled=bool(payload.get("learning_enabled", True)),
        tenant_id=str(payload["tenant_id"]) if payload.get("tenant_id") else None,
    )
    record = make_rejection_record(payload, config)
    memory = RejectionMemory(config)
    memory.append(record)

    return ToolResponse(
        request_id=request_id,
        tool="shadowproof_record_outcome",
        status=ToolStatus.OK,
        lean_status=LeanStatus.NOT_RUN,
        diagnostics=[Diagnostic(
            DiagnosticSeverity.INFO,
            ObstructionKind.NONE,
            f"Recorded outcome in local memory at {memory.path}. privacy_mode={config.privacy_mode}",
            source="learning",
        )],
    ).to_dict()


def shadowproof_suggest_repair(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_suggest_repair"))
    config = LearningConfig(
        memory_path=payload.get("memory_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        enabled=bool(payload.get("learning_enabled", True)),
        tenant_id=str(payload["tenant_id"]) if payload.get("tenant_id") else None,
    )
    theorem_family = payload.get("theorem_family")
    if not theorem_family:
        theorem_family = (payload.get("theorem_fingerprint") or {}).get("theorem_family", "unknown")

    diagnostics = payload.get("diagnostics", [])
    from .learning import normalize_diagnostic_kinds
    kinds = normalize_diagnostic_kinds(diagnostics)

    suggestions = RejectionMemory(config).suggest(str(theorem_family), kinds, limit=int(payload.get("limit", 5)))
    return {
        "request_id": request_id,
        "tool": "shadowproof_suggest_repair",
        "status": "ok",
        "theorem_family": theorem_family,
        "diagnostic_kinds": kinds,
        "suggestions": [s.__dict__ for s in suggestions],
        "memory_stats": RejectionMemory(config).stats(),
    }


def shadowproof_compile_repair_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_compile_repair_prompt"))
    compiled = compile_repair_prompt(payload)
    compiled["request_id"] = request_id
    compiled["tool"] = "shadowproof_compile_repair_prompt"
    return compiled


def shadowproof_memory_stats(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_memory_stats"))
    config = LearningConfig(
        memory_path=payload.get("memory_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        enabled=bool(payload.get("learning_enabled", True)),
        tenant_id=str(payload["tenant_id"]) if payload.get("tenant_id") else None,
    )
    return {
        "request_id": request_id,
        "tool": "shadowproof_memory_stats",
        "status": "ok",
        **RejectionMemory(config).stats(),
    }


def shadowproof_env_info(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_env_info"))
    target = parse_target(payload.get("target", {}))
    timeout = strict_int(payload.get("timeout_seconds"), 10, field="timeout_seconds", min_value=1, max_value=60)
    cwd = resolve_under_allowed_root(payload.get("cwd"), kind="cwd") if payload.get("cwd") else None
    env = certificate_environment_payload(None, cwd, timeout_seconds=timeout)
    return {
        "request_id": request_id,
        "tool": "shadowproof_env_info",
        "status": "ok" if env.get("available") else "unchecked",
        "environment": env,
    }


def shadowproof_eval(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_eval"))
    result = run_eval_suite(payload, tool_caller=call_tool)
    result["request_id"] = request_id
    result["tool"] = "shadowproof_eval"
    return result


def shadowproof_optimize_suggest(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_optimize_suggest"))
    config = OptimizationConfig(
        events_path=payload.get("events_path"),
        policy_path=payload.get("policy_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        learning_enabled=bool(payload.get("learning_enabled", True)),
        exploration_rate=float(payload.get("exploration_rate", 0.0)),
        min_evidence=int(payload.get("min_evidence", 3)),
    )
    from .optimization import context_from_payload
    ctx = context_from_payload(payload)
    suggestion = OptimizationPolicyEngine(config).suggest(ctx)
    return {
        "request_id": request_id,
        "tool": "shadowproof_optimize_suggest",
        "status": "ok",
        "context": dataclass_to_jsonable(ctx),
        "suggestion": dataclass_to_jsonable(suggestion),
    }


def shadowproof_optimize_record(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_optimize_record"))
    config = OptimizationConfig(
        events_path=payload.get("events_path"),
        policy_path=payload.get("policy_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        learning_enabled=bool(payload.get("learning_enabled", True)),
    )
    event = event_from_payload(payload, config)
    store = OptimizationStore(config)
    store.append_event(event)
    return {
        "request_id": request_id,
        "tool": "shadowproof_optimize_record",
        "status": "ok",
        "event_id": event.event_id,
        "feature_key": event.feature_key,
        "action_key": event.action_key,
        "reward": event.reward,
        "events_path": str(store.events_path),
    }


def shadowproof_optimize_train(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_optimize_train"))
    config = OptimizationConfig(
        events_path=payload.get("events_path"),
        policy_path=payload.get("policy_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
        learning_enabled=True,
        min_evidence=int(payload.get("min_evidence", 3)),
    )
    store = OptimizationStore(config)
    policy = store.train_policy()
    return {
        "request_id": request_id,
        "tool": "shadowproof_optimize_train",
        "status": "ok",
        "policy_path": str(store.policy_path),
        "policy": policy,
    }


def shadowproof_optimize_stats(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_optimize_stats"))
    config = OptimizationConfig(
        events_path=payload.get("events_path"),
        policy_path=payload.get("policy_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
    )
    return {
        "request_id": request_id,
        "tool": "shadowproof_optimize_stats",
        "status": "ok",
        **OptimizationStore(config).stats(),
    }


def shadowproof_optimize_export_policy(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_optimize_export_policy"))
    config = OptimizationConfig(
        events_path=payload.get("events_path"),
        policy_path=payload.get("policy_path"),
        privacy_mode=str(payload.get("privacy_mode", "hash_only")),
    )
    store = OptimizationStore(config)
    policy = store.load_policy()
    return {
        "request_id": request_id,
        "tool": "shadowproof_optimize_export_policy",
        "status": "ok",
        "policy_path": str(store.policy_path),
        "policy": policy,
    }


def shadowproof_training_capacity_plan(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    plan = make_capacity_plan(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_training_capacity_plan")),
        "tool": "shadowproof_training_capacity_plan",
        "status": "ok",
        "capacity_plan": plan.to_dict(),
    }


def shadowproof_demorgan_symmetry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_demorgan_symmetry")),
        "tool": "shadowproof_demorgan_symmetry",
        "status": "ok",
        "symmetry": demorgan_order_two_report(),
        "lean_formalization": "lean_project_template/ShadowProof/DemorganSymmetry.lean",
        "lean_governance_formalizations": [
            "lean_project_template/ShadowProof/BilatticeCore.lean",
            "lean_project_template/ShadowProof/Routing.lean",
            "lean_project_template/ShadowProof/PatchMorphism.lean",
            "lean_project_template/ShadowProof/NoGluttyJ.lean",
        ],
        "formalization_scope": "finite ShadowHoTT governance core: bilattice laws, routing invariants, fingerprint-preserving patch morphisms, and No-Glutty-J safety; not a full HoTT implementation",
    }


def shadowproof_list_domains(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_list_domains"))
    domain_dirs = list(payload.get("domain_dirs", ["domains"]))
    packs = list_domain_packs(domain_dirs)
    return {
        "request_id": request_id,
        "tool": "shadowproof_list_domains",
        "status": "ok",
        "domain_count": len(packs),
        "domains": [
            {
                "domain": p.domain,
                "aliases": p.aliases,
                "subfields": p.subfields,
                "imports": p.imports,
                "theorem_count": len(p.common_theorems),
                "metadata_keys": sorted(str(k) for k in p.metadata.keys()),
            }
            for p in packs
        ],
    }


def shadowproof_get_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_get_domain_pack"))
    domain = str(payload.get("domain", ""))
    domain_dirs = list(payload.get("domain_dirs", ["domains"]))
    pack = get_domain_pack(domain, domain_dirs)
    if pack is None:
        return {
            "request_id": request_id,
            "tool": "shadowproof_get_domain_pack",
            "status": "not_found",
            "domain": domain,
        }
    return {
        "request_id": request_id,
        "tool": "shadowproof_get_domain_pack",
        "status": "ok",
        "domain_pack": retrieval_jsonable(pack),
    }


def shadowproof_retrieve_mathlib(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_retrieve_mathlib"))
    result = retrieve_mathlib_context(payload)
    return {
        "request_id": request_id,
        "tool": "shadowproof_retrieve_mathlib",
        "status": "ok",
        "retrieval": retrieval_jsonable(result),
    }


def shadowproof_compile_formalization_context(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_compile_formalization_context"))
    payload = dict(payload)
    payload["include_prompt_context"] = True
    result = retrieve_mathlib_context(payload)
    return {
        "request_id": request_id,
        "tool": "shadowproof_compile_formalization_context",
        "status": "ok",
        "detected_domains": result.detected_domains,
        "imports": result.imports,
        "candidate_count": len(result.candidates),
        "prompt_context": result.prompt_context,
        "retrieval": retrieval_jsonable(result),
    }


def shadowproof_index_mathlib(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_index_mathlib"))
    result = index_mathlib_sources(payload)
    result["request_id"] = request_id
    result["tool"] = "shadowproof_index_mathlib"
    return result


def shadowproof_retrieve_for_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_retrieve_for_diagnostics"))
    result = retrieve_for_diagnostics(payload)
    return {
        "request_id": request_id,
        "tool": "shadowproof_retrieve_for_diagnostics",
        "status": "ok",
        **result,
    }


def shadowproof_compile_repair_context(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_compile_repair_context"))
    result = compile_retrieval_augmented_repair_context(payload)
    return {
        "request_id": request_id,
        "tool": "shadowproof_compile_repair_context",
        "status": "ok",
        **result,
    }


def shadowproof_shadowhott_state(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_shadowhott_state"))
    state = build_shadowhott_state(payload).to_dict()
    return {
        "request_id": request_id,
        "tool": "shadowproof_shadowhott_state",
        "status": "ok",
        "shadowhott_state": state,
    }


def shadowproof_shadowhott_audit(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_shadowhott_audit"))
    audit = audit_shadowhott_state(payload)
    audit["request_id"] = request_id
    audit["tool"] = "shadowproof_shadowhott_audit"
    return audit


def augment_response_for_shadowhott(response: ToolResponse, policy: PolicySpec | None = None, payload: dict[str, Any] | None = None) -> ToolResponse:
    policy = policy or PolicySpec()
    payload = payload or {}
    if getattr(policy, "return_shadowhott_state", True):
        state_payload = response.to_dict()
        # Preserve original request payload hints such as domain dirs / retrieval policy.
        for key in ["domain_dirs", "index_paths", "retrieval_limit", "domains", "auto_retrieve", "max_prompt_chars", "max_prompt_tokens"]:
            if key in payload and key not in state_payload:
                state_payload[key] = payload[key]
        try:
            response.shadowhott_state = build_shadowhott_state(state_payload).to_dict()
        except Exception as e:
            response.shadowhott_state = {"error": f"failed_to_build_shadowhott_state: {e}"}

    if getattr(policy, "auto_repair_context", False) and response.status in {ToolStatus.NEEDS_REPAIR, ToolStatus.REJECTED, ToolStatus.ERROR, ToolStatus.UNCHECKED}:
        ctx_payload = response.to_dict()
        ctx_payload.update({k: v for k, v in payload.items() if k in {
            "domain_dirs", "index_paths", "retrieval_limit", "domains", "max_prompt_chars", "max_prompt_tokens", "auto_retrieve"
        }})
        ctx_payload["auto_retrieve"] = getattr(policy, "auto_retrieve", True)
        try:
            response.repair_context = compile_retrieval_augmented_repair_context(ctx_payload)
        except Exception as e:
            response.repair_context = {"error": f"failed_to_compile_repair_context: {e}"}
        try:
            prompt_payload = dict(ctx_payload)
            prompt_payload["auto_retrieve"] = getattr(policy, "auto_retrieve", True)
            response.compiled_repair_prompt = compile_repair_prompt(prompt_payload)
        except Exception as e:
            response.compiled_repair_prompt = {"error": f"failed_to_compile_repair_prompt: {e}"}
    return response


def shadowproof_validate_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """
    v9 wrapper: run the v8 validation core, then attach explicit ShadowHoTT state.
    If policy.auto_repair_context is true, attach retrieval-augmented repair context
    and a compiled repair prompt to non-accepted responses.
    """
    raw = _shadowproof_validate_draft_core(payload)
    try:
        policy = parse_policy(payload.get("policy", {}))
        response = ToolResponse(
            request_id=str(raw.get("request_id", payload.get("request_id", "shadowproof_validate_draft"))),
            tool=str(raw.get("tool", "shadowproof_validate_draft")),
            status=ToolStatus(raw.get("status", "error")),
            lean_status=LeanStatus(raw.get("lean_status", "not_run")),
            diagnostics=[Diagnostic(
                severity=DiagnosticSeverity(d.get("severity", "error")),
                kind=ObstructionKind(d.get("kind", "unknown_lean_failure")),
                message=str(d.get("message", "")),
                line=d.get("line"),
                column=d.get("column"),
                source=str(d.get("source", "shadowproof")),
            ) for d in raw.get("diagnostics", []) if isinstance(d, dict)],
            theorem_fingerprint=raw.get("theorem_fingerprint"),
            proof_graph=raw.get("proof_graph", []),
            patches=raw.get("patches", []),
            certificate=raw.get("certificate"),
            final_lean_code=raw.get("final_lean_code"),
            raw_lean_stdout=raw.get("raw_lean_stdout"),
            raw_lean_stderr=raw.get("raw_lean_stderr"),
        )
        augmented = augment_response_for_shadowhott(response, policy=policy, payload=payload).to_dict()
        # Preserve fields not represented by ToolResponse dataclass.
        for k, v in raw.items():
            augmented.setdefault(k, v)
        return augmented
    except Exception as e:
        raw["shadowhott_state"] = {"error": f"v9 augmentation failed: {e}"}
        return raw


def shadowproof_validate(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _shadowproof_validate_core(payload)
    try:
        policy = parse_policy(payload.get("policy", {}))
        response = ToolResponse(
            request_id=str(raw.get("request_id", payload.get("request_id", "shadowproof_validate"))),
            tool=str(raw.get("tool", "shadowproof_validate")),
            status=ToolStatus(raw.get("status", "error")),
            lean_status=LeanStatus(raw.get("lean_status", "not_run")),
            diagnostics=[Diagnostic(
                severity=DiagnosticSeverity(d.get("severity", "error")),
                kind=ObstructionKind(d.get("kind", "unknown_lean_failure")),
                message=str(d.get("message", "")),
                line=d.get("line"),
                column=d.get("column"),
                source=str(d.get("source", "shadowproof")),
            ) for d in raw.get("diagnostics", []) if isinstance(d, dict)],
            theorem_fingerprint=raw.get("theorem_fingerprint"),
            proof_graph=raw.get("proof_graph", []),
            patches=raw.get("patches", []),
            certificate=raw.get("certificate"),
            final_lean_code=raw.get("final_lean_code"),
            raw_lean_stdout=raw.get("raw_lean_stdout"),
            raw_lean_stderr=raw.get("raw_lean_stderr"),
        )
        augmented = augment_response_for_shadowhott(response, policy=policy, payload=payload).to_dict()
        for k, v in raw.items():
            augmented.setdefault(k, v)
        return augmented
    except Exception as e:
        raw["shadowhott_state"] = {"error": f"v9 augmentation failed: {e}"}
        return raw


def shadowproof_shadowhott_eval(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_shadowhott_eval"))
    result = run_shadowhott_eval_suite(payload)
    result["request_id"] = request_id
    result["tool"] = "shadowproof_shadowhott_eval"
    return result


def shadowproof_regression_suite(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = str(payload.get("request_id", "shadowproof_regression_suite"))
    result = run_bridge_regression_suite(payload, tool_caller=call_tool)
    result["request_id"] = request_id
    result["tool"] = "shadowproof_regression_suite"
    return result


def shadowproof_local_behavior_simulation(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    request_id = str(payload.get("request_id", "shadowproof_local_behavior_simulation"))
    result = run_local_behavior_simulation(payload, tool_caller=call_tool)
    result["request_id"] = request_id
    result["tool"] = "shadowproof_local_behavior_simulation"
    return result


def shadowproof_config_check(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    cfg.ensure_dirs()
    return {
        "request_id": str(payload.get("request_id", "shadowproof_config_check")),
        "tool": "shadowproof_config_check",
        "status": "ok",
        "config": cfg.to_dict(),
        "sandbox": sandbox_check(cfg),
    }


def shadowproof_product_readiness(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_product_readiness")),
        "tool": "shadowproof_product_readiness",
        **product_readiness_report(cfg),
    }


def shadowproof_metrics_report(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_metrics_report")),
        "tool": "shadowproof_metrics_report",
        "status": "ok",
        "metrics": metrics_report(cfg, limit=int(payload.get("limit", 10000))),
    }


def shadowproof_prometheus_metrics(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_prometheus_metrics")),
        "tool": "shadowproof_prometheus_metrics",
        "status": "ok",
        "content_type": "text/plain; version=0.0.4",
        "text": prometheus_text(cfg),
    }


def shadowproof_retention_sweep(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_retention_sweep")),
        "tool": "shadowproof_retention_sweep",
        **retention_sweep(cfg),
    }


def shadowproof_create_review_packet(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_create_review_packet")),
        "tool": "shadowproof_create_review_packet",
        **create_review_packet(payload, cfg),
    }


def shadowproof_lean_worker_check(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(payload)
    code = str(payload.get("code") or payload.get("lean_code") or "")
    result = run_lean_worker(code, cfg, request_id=str(payload.get("request_id", "lean-worker-check")))
    return {
        "request_id": str(payload.get("request_id", "shadowproof_lean_worker_check")),
        "tool": "shadowproof_lean_worker_check",
        **result.__dict__,
    }


def shadowproof_adapter_catalog(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_adapter_catalog")),
        "tool": "shadowproof_adapter_catalog",
        "status": "ok",
        "catalog": adapter_catalog(),
    }


def shadowproof_model_provider_call(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_model_provider_call")),
        "tool": "shadowproof_model_provider_call",
        **call_model_provider(payload, cfg),
    }


def shadowproof_cost_estimate(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_cost_estimate")),
        "tool": "shadowproof_cost_estimate",
        "status": "ok",
        "cost": estimate_cost(payload),
    }


def shadowproof_admin_tenant_report(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_admin_tenant_report")),
        "tool": "shadowproof_admin_tenant_report",
        **tenant_report(payload, cfg),
    }


def shadowproof_admin_delete_tenant_data(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_admin_delete_tenant_data")),
        "tool": "shadowproof_admin_delete_tenant_data",
        **delete_tenant_data(payload, cfg),
    }


def shadowproof_openapi_spec(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_openapi_spec")),
        "tool": "shadowproof_openapi_spec",
        "status": "ok",
        "openapi": build_openapi_spec(),
    }


def shadowproof_security_threat_model(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_security_threat_model")),
        "tool": "shadowproof_security_threat_model",
        **threat_model_report(payload),
    }


def shadowproof_license_scan(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_license_scan")),
        "tool": "shadowproof_license_scan",
        **license_scan(payload),
    }


def shadowproof_release_gate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    cfg = load_config(payload)
    return {
        "request_id": str(payload.get("request_id", "shadowproof_release_gate")),
        "tool": "shadowproof_release_gate",
        **release_gate(payload, cfg),
    }


def shadowproof_pilot_plan(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_pilot_plan")),
        "tool": "shadowproof_pilot_plan",
        **generate_pilot_plan(payload),
    }


def shadowproof_integration_checklist(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_integration_checklist")),
        "tool": "shadowproof_integration_checklist",
        **integration_checklist(payload),
    }


def shadowproof_acceptance_criteria(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_acceptance_criteria")),
        "tool": "shadowproof_acceptance_criteria",
        **acceptance_criteria(payload),
    }


def shadowproof_onboarding_packet(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_onboarding_packet")),
        "tool": "shadowproof_onboarding_packet",
        **generate_onboarding_packet(payload),
    }


def shadowproof_adapter_conformance_plan(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_adapter_conformance_plan")),
        "tool": "shadowproof_adapter_conformance_plan",
        **adapter_conformance_plan(payload),
    }


def shadowproof_domain_pack_schema(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_schema")),
        "tool": "shadowproof_domain_pack_schema",
        **domain_pack_schema(payload),
    }


def shadowproof_create_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_create_domain_pack")),
        "tool": "shadowproof_create_domain_pack",
        **create_domain_pack(payload),
    }


def shadowproof_validate_domain_pack(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_validate_domain_pack")),
        "tool": "shadowproof_validate_domain_pack",
        **validate_domain_pack(payload),
    }


def shadowproof_domain_pack_eval_stub(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_eval_stub")),
        "tool": "shadowproof_domain_pack_eval_stub",
        **domain_pack_eval_stub(payload),
    }


def shadowproof_domain_pack_authoring_guide(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_authoring_guide")),
        "tool": "shadowproof_domain_pack_authoring_guide",
        **domain_pack_authoring_guide(payload),
    }


def shadowproof_domain_pack_submit(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_submit")),
        "tool": "shadowproof_domain_pack_submit",
        **submit_domain_pack(payload),
    }


def shadowproof_domain_pack_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_status")),
        "tool": "shadowproof_domain_pack_status",
        **domain_pack_status(payload),
    }


def shadowproof_domain_pack_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_registry")),
        "tool": "shadowproof_domain_pack_registry",
        **domain_pack_registry(payload),
    }


def shadowproof_domain_pack_promote(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_promote")),
        "tool": "shadowproof_domain_pack_promote",
        **promote_domain_pack(payload),
    }


def shadowproof_domain_pack_review(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_review")),
        "tool": "shadowproof_domain_pack_review",
        **record_domain_pack_review(payload),
    }


def shadowproof_domain_pack_attach_eval(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_attach_eval")),
        "tool": "shadowproof_domain_pack_attach_eval",
        **attach_domain_pack_eval(payload),
    }


def shadowproof_domain_pack_rollback(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_domain_pack_rollback")),
        "tool": "shadowproof_domain_pack_rollback",
        **rollback_domain_pack(payload),
    }


def shadowproof_proof_artifact_submit(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_submit")),
        "tool": "shadowproof_proof_artifact_submit",
        **submit_proof_artifact(payload),
    }


def shadowproof_proof_artifact_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_status")),
        "tool": "shadowproof_proof_artifact_status",
        **proof_artifact_status(payload),
    }


def shadowproof_proof_artifact_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_registry")),
        "tool": "shadowproof_proof_artifact_registry",
        **proof_artifact_registry(payload),
    }


def shadowproof_proof_artifact_attach_validation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_attach_validation")),
        "tool": "shadowproof_proof_artifact_attach_validation",
        **attach_proof_validation(payload),
    }


def shadowproof_proof_artifact_promote(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_promote")),
        "tool": "shadowproof_proof_artifact_promote",
        **promote_proof_artifact(payload),
    }


def shadowproof_proof_artifact_review(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_review")),
        "tool": "shadowproof_proof_artifact_review",
        **record_proof_review(payload),
    }


def shadowproof_proof_artifact_review_packet(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_review_packet")),
        "tool": "shadowproof_proof_artifact_review_packet",
        **create_proof_review_packet(payload),
    }


def shadowproof_proof_artifact_export(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_proof_artifact_export")),
        "tool": "shadowproof_proof_artifact_export",
        **proof_artifact_export(payload),
    }


def shadowproof_release_report(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(payload.get("request_id", "shadowproof_release_report")),
        "tool": "shadowproof_release_report",
        **generate_release_report(payload, tool_caller=call_tool),
    }


def shadowproof_release_checklist(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_release_checklist")),
        "tool": "shadowproof_release_checklist",
        **release_checklist(payload),
    }


def shadowproof_liveness(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_liveness")),
        "tool": "shadowproof_liveness",
        **liveness(payload),
    }


def shadowproof_readiness(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_readiness")),
        "tool": "shadowproof_readiness",
        **readiness(payload),
    }


def shadowproof_service_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_service_status")),
        "tool": "shadowproof_service_status",
        **service_status(payload),
    }


def shadowproof_error_taxonomy(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_error_taxonomy")),
        "tool": "shadowproof_error_taxonomy",
        **error_taxonomy(payload),
    }


def shadowproof_trace_envelope(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_trace_envelope")),
        "tool": "shadowproof_trace_envelope",
        "status": "ok",
        "trace": make_trace(payload),
        "proof_lifecycle": make_proof_lifecycle_trace(payload, response),
    }


def shadowproof_investor_deck(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_investor_deck")),
        "tool": "shadowproof_investor_deck",
        **investor_deck_index(payload),
    }


def shadowproof_acquisition_packet(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_acquisition_packet")),
        "tool": "shadowproof_acquisition_packet",
        **acquisition_packet(payload),
    }


def shadowproof_claims_boundary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_claims_boundary")),
        "tool": "shadowproof_claims_boundary",
        **acquisition_claims_boundary(payload),
    }


def shadowproof_due_diligence_checklist(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "request_id": str(payload.get("request_id", "shadowproof_due_diligence_checklist")),
        "tool": "shadowproof_due_diligence_checklist",
        **due_diligence_checklist(payload),
    }

def parse_target(raw: dict[str, Any]) -> TargetSpec:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValueError("target must be an object")
    if "lean_command" in raw:
        # Never honor per-request Lean command overrides. The runner command is
        # deployment-owned through SHADOWPROOF_LEAN_CMD only.
        raise ValueError("target.lean_command is not accepted; configure SHADOWPROOF_LEAN_CMD on the server")
    imports = raw.get("imports", ["Mathlib"])
    if not isinstance(imports, list) or not all(isinstance(x, str) for x in imports):
        raise ValueError("target.imports must be a list of strings")
    system = str(raw.get("system", "lean4"))
    if system != "lean4":
        raise ValueError("target.system must be 'lean4'")
    theorem_name = raw.get("theorem_name")
    if theorem_name is not None and not isinstance(theorem_name, str):
        raise ValueError("target.theorem_name must be a string")
    return TargetSpec(
        system=system,
        imports=imports,
        lean_command=None,
        allow_sorry=strict_bool(raw.get("allow_sorry"), False, field="target.allow_sorry"),
        theorem_name=theorem_name,
    )


def parse_policy(raw: dict[str, Any]) -> PolicySpec:
    raw = raw or {}
    if not isinstance(raw, dict):
        raise ValueError("policy must be an object")
    level = raw.get("security_level", "conservative")
    try:
        level_enum = SecurityLevel(level)
    except Exception:
        level_enum = SecurityLevel.CONSERVATIVE

    return PolicySpec(
        max_iterations=strict_int(raw.get("max_iterations"), 4, field="policy.max_iterations", min_value=0, max_value=20),
        timeout_seconds=strict_int(raw.get("timeout_seconds"), 30, field="policy.timeout_seconds", min_value=1, max_value=300),
        allow_theorem_mutation=strict_bool(raw.get("allow_theorem_mutation"), False, field="policy.allow_theorem_mutation"),
        security_level=level_enum,
        return_code=strict_bool(raw.get("return_code"), True, field="policy.return_code"),
        return_proof_graph=strict_bool(raw.get("return_proof_graph"), True, field="policy.return_proof_graph"),
        return_shadowhott_state=strict_bool(raw.get("return_shadowhott_state"), True, field="policy.return_shadowhott_state"),
        auto_repair_context=strict_bool(raw.get("auto_repair_context"), False, field="policy.auto_repair_context"),
        auto_retrieve=strict_bool(raw.get("auto_retrieve"), True, field="policy.auto_retrieve"),
    )


def parse_problem(raw: dict[str, Any]) -> NLProblem:
    raw = raw or {}
    return NLProblem(
        theorem=str(raw.get("theorem", "")),
        proof=str(raw.get("proof", "")),
        context=str(raw.get("context", "")),
    )


TOOL_REGISTRY = {
    "lean_check": lean_check,
    "shadowproof_translate": shadowproof_translate,
    "shadowproof_repair": shadowproof_repair,
    "shadowproof_validate": shadowproof_validate,
    "shadowproof_check_draft": shadowproof_check_draft,
    "shadowproof_validate_draft": shadowproof_validate_draft,
    "shadowproof_draft_schema": shadowproof_draft_schema,
    "shadowproof_record_outcome": shadowproof_record_outcome,
    "shadowproof_suggest_repair": shadowproof_suggest_repair,
    "shadowproof_compile_repair_prompt": shadowproof_compile_repair_prompt,
    "shadowproof_memory_stats": shadowproof_memory_stats,
    "shadowproof_env_info": shadowproof_env_info,
    "shadowproof_eval": shadowproof_eval,
    "shadowproof_optimize_suggest": shadowproof_optimize_suggest,
    "shadowproof_optimize_record": shadowproof_optimize_record,
    "shadowproof_optimize_train": shadowproof_optimize_train,
    "shadowproof_optimize_stats": shadowproof_optimize_stats,
    "shadowproof_optimize_export_policy": shadowproof_optimize_export_policy,
    "shadowproof_training_capacity_plan": shadowproof_training_capacity_plan,
    "shadowproof_demorgan_symmetry": shadowproof_demorgan_symmetry,
    "shadowproof_list_domains": shadowproof_list_domains,
    "shadowproof_get_domain_pack": shadowproof_get_domain_pack,
    "shadowproof_retrieve_mathlib": shadowproof_retrieve_mathlib,
    "shadowproof_compile_formalization_context": shadowproof_compile_formalization_context,
    "shadowproof_index_mathlib": shadowproof_index_mathlib,
    "shadowproof_retrieve_for_diagnostics": shadowproof_retrieve_for_diagnostics,
    "shadowproof_compile_repair_context": shadowproof_compile_repair_context,
    "shadowproof_shadowhott_state": shadowproof_shadowhott_state,
    "shadowproof_shadowhott_audit": shadowproof_shadowhott_audit,
    "shadowproof_shadowhott_eval": shadowproof_shadowhott_eval,
    "shadowproof_regression_suite": shadowproof_regression_suite,
    "shadowproof_local_behavior_simulation": shadowproof_local_behavior_simulation,
    "shadowproof_config_check": shadowproof_config_check,
    "shadowproof_product_readiness": shadowproof_product_readiness,
    "shadowproof_metrics_report": shadowproof_metrics_report,
    "shadowproof_prometheus_metrics": shadowproof_prometheus_metrics,
    "shadowproof_retention_sweep": shadowproof_retention_sweep,
    "shadowproof_create_review_packet": shadowproof_create_review_packet,
    "shadowproof_lean_worker_check": shadowproof_lean_worker_check,
    "shadowproof_adapter_catalog": shadowproof_adapter_catalog,
    "shadowproof_model_provider_call": shadowproof_model_provider_call,
    "shadowproof_cost_estimate": shadowproof_cost_estimate,
    "shadowproof_admin_tenant_report": shadowproof_admin_tenant_report,
    "shadowproof_admin_delete_tenant_data": shadowproof_admin_delete_tenant_data,
    "shadowproof_openapi_spec": shadowproof_openapi_spec,
    "shadowproof_security_threat_model": shadowproof_security_threat_model,
    "shadowproof_license_scan": shadowproof_license_scan,
    "shadowproof_release_gate": shadowproof_release_gate,
    "shadowproof_pilot_plan": shadowproof_pilot_plan,
    "shadowproof_integration_checklist": shadowproof_integration_checklist,
    "shadowproof_acceptance_criteria": shadowproof_acceptance_criteria,
    "shadowproof_onboarding_packet": shadowproof_onboarding_packet,
    "shadowproof_adapter_conformance_plan": shadowproof_adapter_conformance_plan,
    "shadowproof_domain_pack_schema": shadowproof_domain_pack_schema,
    "shadowproof_create_domain_pack": shadowproof_create_domain_pack,
    "shadowproof_validate_domain_pack": shadowproof_validate_domain_pack,
    "shadowproof_domain_pack_eval_stub": shadowproof_domain_pack_eval_stub,
    "shadowproof_domain_pack_authoring_guide": shadowproof_domain_pack_authoring_guide,
    "shadowproof_domain_pack_submit": shadowproof_domain_pack_submit,
    "shadowproof_domain_pack_status": shadowproof_domain_pack_status,
    "shadowproof_domain_pack_registry": shadowproof_domain_pack_registry,
    "shadowproof_domain_pack_promote": shadowproof_domain_pack_promote,
    "shadowproof_domain_pack_review": shadowproof_domain_pack_review,
    "shadowproof_domain_pack_attach_eval": shadowproof_domain_pack_attach_eval,
    "shadowproof_domain_pack_rollback": shadowproof_domain_pack_rollback,
    "shadowproof_proof_artifact_submit": shadowproof_proof_artifact_submit,
    "shadowproof_proof_artifact_status": shadowproof_proof_artifact_status,
    "shadowproof_proof_artifact_registry": shadowproof_proof_artifact_registry,
    "shadowproof_proof_artifact_attach_validation": shadowproof_proof_artifact_attach_validation,
    "shadowproof_proof_artifact_promote": shadowproof_proof_artifact_promote,
    "shadowproof_proof_artifact_review": shadowproof_proof_artifact_review,
    "shadowproof_proof_artifact_review_packet": shadowproof_proof_artifact_review_packet,
    "shadowproof_proof_artifact_export": shadowproof_proof_artifact_export,
    "shadowproof_release_report": shadowproof_release_report,
    "shadowproof_release_checklist": shadowproof_release_checklist,
    "shadowproof_liveness": shadowproof_liveness,
    "shadowproof_readiness": shadowproof_readiness,
    "shadowproof_service_status": shadowproof_service_status,
    "shadowproof_error_taxonomy": shadowproof_error_taxonomy,
    "shadowproof_trace_envelope": shadowproof_trace_envelope,
    "shadowproof_investor_deck": shadowproof_investor_deck,
    "shadowproof_acquisition_packet": shadowproof_acquisition_packet,
    "shadowproof_claims_boundary": shadowproof_claims_boundary,
    "shadowproof_due_diligence_checklist": shadowproof_due_diligence_checklist,
}


def call_tool(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if name not in TOOL_REGISTRY:
        return ToolResponse(
            request_id=str(payload.get("request_id", "unknown")),
            tool=name,
            status=ToolStatus.ERROR,
            diagnostics=[Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.UNKNOWN_LEAN_FAILURE, f"Unknown tool: {name}", source="tool_api")],
        ).to_dict()
    try:
        return TOOL_REGISTRY[name](payload)
    except ValueError as e:
        return ToolResponse(
            request_id=str(payload.get("request_id", name)),
            tool=name,
            status=ToolStatus.ERROR,
            lean_status=LeanStatus.NOT_RUN,
            diagnostics=[Diagnostic(DiagnosticSeverity.ERROR, ObstructionKind.SECURITY_REJECTION, str(e), source="tool_api")],
        ).to_dict()


def dumps_response(response: dict[str, Any]) -> str:
    return json.dumps(response, indent=2, ensure_ascii=False)
