from __future__ import annotations

import argparse
import json
from pathlib import Path

from .server import serve
from .tool_api import call_tool, dumps_response
from .schema_validation import validate_tool_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="ShadowProof Bridge v25.8 Pre-Commercial Package")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_json_cmd(name: str, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("json_file", type=Path)
        p.add_argument("--no-schema-validation", action="store_true", help="Disable CLI JSON Schema validation for local debugging only.")
        return p

    commands = {
        "check": ("lean_check", "Run lean_check on a JSON request."),
        "translate": ("shadowproof_translate", "Run shadowproof_translate on a JSON request."),
        "validate": ("shadowproof_validate", "Run shadowproof_validate on a JSON request."),
        "check-draft": ("shadowproof_check_draft", "Run static DraftProposal checks on a JSON request."),
        "validate-draft": ("shadowproof_validate_draft", "Run DraftProposal checks and Lean validation."),
        "record-outcome": ("shadowproof_record_outcome", "Record an outcome."),
        "suggest-repair": ("shadowproof_suggest_repair", "Suggest a repair strategy."),
        "compile-repair-prompt": ("shadowproof_compile_repair_prompt", "Compile LLM repair prompt."),
        "memory-stats": ("shadowproof_memory_stats", "Show rejection memory stats."),
        "env-info": ("shadowproof_env_info", "Capture Lean/Lake/Mathlib environment information."),
        "eval": ("shadowproof_eval", "Run a ShadowProof eval suite."),
        "optimize-suggest": ("shadowproof_optimize_suggest", "Suggest optimized policy action."),
        "optimize-record": ("shadowproof_optimize_record", "Record optimization event."),
        "optimize-train": ("shadowproof_optimize_train", "Train optimization policy."),
        "optimize-stats": ("shadowproof_optimize_stats", "Show optimization stats."),
        "optimize-export-policy": ("shadowproof_optimize_export_policy", "Export optimization policy."),
        "training-capacity-plan": ("shadowproof_training_capacity_plan", "Plan offline trainable-parameter capacity."),
        "demorgan-symmetry": ("shadowproof_demorgan_symmetry", "Report De Morgan order-two bilattice coordinate symmetry."),
        "list-domains": ("shadowproof_list_domains", "List domain packs."),
        "get-domain-pack": ("shadowproof_get_domain_pack", "Return a domain pack."),
        "retrieve-mathlib": ("shadowproof_retrieve_mathlib", "Retrieve Mathlib/domain candidates."),
        "compile-formalization-context": ("shadowproof_compile_formalization_context", "Compile formalization context."),
        "index-mathlib": ("shadowproof_index_mathlib", "Index local Lean sources."),
        "retrieve-for-diagnostics": ("shadowproof_retrieve_for_diagnostics", "Retrieve from diagnostics."),
        "compile-repair-context": ("shadowproof_compile_repair_context", "Compile retrieval-augmented repair context."),
        "shadowhott-state": ("shadowproof_shadowhott_state", "Construct ShadowHoTT state."),
        "shadowhott-audit": ("shadowproof_shadowhott_audit", "Audit ShadowHoTT state."),
        "shadowhott-eval": ("shadowproof_shadowhott_eval", "Run ShadowHoTT eval suite."),
        "regression": ("shadowproof_regression_suite", "Run full regression suite."),
        "local-sim": ("shadowproof_local_behavior_simulation", "Run local deterministic provider/Lean behavior simulation."),
        "config-check": ("shadowproof_config_check", "Show resolved commercial config."),
        "product-readiness": ("shadowproof_product_readiness", "Report product readiness."),
        "metrics-report": ("shadowproof_metrics_report", "Summarize metrics."),
        "prometheus-metrics": ("shadowproof_prometheus_metrics", "Export Prometheus text metrics."),
        "retention-sweep": ("shadowproof_retention_sweep", "Apply retention policy."),
        "create-review-packet": ("shadowproof_create_review_packet", "Create human review packet."),
        "lean-worker-check": ("shadowproof_lean_worker_check", "Check Lean through configured worker."),
        "adapter-catalog": ("shadowproof_adapter_catalog", "Show enterprise adapter catalog."),
        "model-provider-call": ("shadowproof_model_provider_call", "Call configured model-provider adapter."),
        "cost-estimate": ("shadowproof_cost_estimate", "Estimate proof/repair cost."),
        "admin-tenant-report": ("shadowproof_admin_tenant_report", "Report tenant storage/metrics."),
        "admin-delete-tenant-data": ("shadowproof_admin_delete_tenant_data", "Delete tenant data with confirmation."),
        "openapi-spec": ("shadowproof_openapi_spec", "Emit OpenAPI specification."),
        "security-threat-model": ("shadowproof_security_threat_model", "Emit security threat model."),
        "license-scan": ("shadowproof_license_scan", "Run lightweight license scan scaffold."),
        "release-gate": ("shadowproof_release_gate", "Run conservative enterprise release gate."),
        "pilot-plan": ("shadowproof_pilot_plan", "Generate a 3-week company pilot plan."),
        "integration-checklist": ("shadowproof_integration_checklist", "Generate company integration checklist."),
        "acceptance-criteria": ("shadowproof_acceptance_criteria", "Show pilot/GA acceptance criteria."),
        "onboarding-packet": ("shadowproof_onboarding_packet", "Generate onboarding packet files."),
        "adapter-conformance-plan": ("shadowproof_adapter_conformance_plan", "Show adapter conformance test plan."),
        "domain-pack-schema": ("shadowproof_domain_pack_schema", "Print domain-pack JSON schema."),
        "create-domain-pack": ("shadowproof_create_domain_pack", "Create a company domain-pack template."),
        "validate-domain-pack": ("shadowproof_validate_domain_pack", "Validate/lint a domain pack."),
        "domain-pack-eval-stub": ("shadowproof_domain_pack_eval_stub", "Generate retrieval eval stubs from a domain pack."),
        "domain-pack-authoring-guide": ("shadowproof_domain_pack_authoring_guide", "Show domain-pack authoring guide."),
        "domain-pack-submit": ("shadowproof_domain_pack_submit", "Submit a domain pack to promotion registry."),
        "domain-pack-status": ("shadowproof_domain_pack_status", "Show domain pack promotion status."),
        "domain-pack-registry": ("shadowproof_domain_pack_registry", "Show domain pack registry."),
        "domain-pack-promote": ("shadowproof_domain_pack_promote", "Promote a domain pack state."),
        "domain-pack-review": ("shadowproof_domain_pack_review", "Record domain pack review."),
        "domain-pack-attach-eval": ("shadowproof_domain_pack_attach_eval", "Attach eval report to domain pack."),
        "domain-pack-rollback": ("shadowproof_domain_pack_rollback", "Rollback active domain pack if backup exists."),
        "proof-artifact-submit": ("shadowproof_proof_artifact_submit", "Submit a proof artifact to registry."),
        "proof-artifact-status": ("shadowproof_proof_artifact_status", "Show proof artifact status."),
        "proof-artifact-registry": ("shadowproof_proof_artifact_registry", "Show proof artifact registry."),
        "proof-artifact-attach-validation": ("shadowproof_proof_artifact_attach_validation", "Attach validation report to proof artifact."),
        "proof-artifact-promote": ("shadowproof_proof_artifact_promote", "Promote proof artifact state."),
        "proof-artifact-review": ("shadowproof_proof_artifact_review", "Record proof artifact review."),
        "proof-artifact-review-packet": ("shadowproof_proof_artifact_review_packet", "Create proof artifact review packet."),
        "proof-artifact-export": ("shadowproof_proof_artifact_export", "Export approved/archived proof artifact."),
        "release-report": ("shadowproof_release_report", "Generate a unified auditable release report."),
        "release-checklist": ("shadowproof_release_checklist", "Show release checklist."),
        "liveness": ("shadowproof_liveness", "Run liveness probe."),
        "readiness": ("shadowproof_readiness", "Run readiness probe."),
        "service-status": ("shadowproof_service_status", "Show hosted service status."),
        "error-taxonomy": ("shadowproof_error_taxonomy", "Show structured error taxonomy."),
        "trace-envelope": ("shadowproof_trace_envelope", "Generate request trace envelope."),
        "investor-deck": ("shadowproof_investor_deck", "Show buyer deck and valuation memo index."),
        "acquisition-packet": ("shadowproof_acquisition_packet", "Show acquisition packet index and demo order."),
        "claims-boundary": ("shadowproof_claims_boundary", "Show claims boundary for buyer diligence."),
        "due-diligence-checklist": ("shadowproof_due_diligence_checklist", "Show buyer due-diligence checklist."),
    }

    for name, (_, help_text) in commands.items():
        add_json_cmd(name, help_text)

    sub.add_parser("draft-schema", help="Print DraftProposal JSON schema.")

    p_serve = sub.add_parser("serve", help="Start JSON HTTP server.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    p_asgi = sub.add_parser("serve-asgi", help="Start ASGI pilot server with uvicorn if installed.")
    p_asgi.add_argument("--host", default="127.0.0.1")
    p_asgi.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()

    if args.cmd == "serve":
        serve(args.host, args.port)
        return

    if args.cmd == "serve-asgi":
        try:
            import uvicorn  # type: ignore
        except Exception as e:
            raise SystemExit("uvicorn is required; install shadowproof-bridge[prod]") from e
        uvicorn.run("shadowproof_core.asgi:app", host=args.host, port=args.port)
        return

    if args.cmd == "draft-schema":
        print(dumps_response(call_tool("shadowproof_draft_schema", {})))
        return

    tool_name = commands[args.cmd][0]
    payload = json.loads(args.json_file.read_text(encoding="utf-8"))
    if not getattr(args, "no_schema_validation", False):
        errors = validate_tool_payload(tool_name, payload)
        if errors:
            joined = "\n".join(f"- {e}" for e in errors)
            raise SystemExit(f"Payload failed schema validation for {tool_name}:\n{joined}")
    if tool_name in {"shadowproof_eval", "shadowproof_shadowhott_eval", "shadowproof_regression_suite"}:
        payload["_suite_base_dir"] = str(args.json_file.parent)
    print(dumps_response(call_tool(tool_name, payload)))


if __name__ == "__main__":
    main()
