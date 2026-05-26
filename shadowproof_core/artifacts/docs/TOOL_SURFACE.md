# Tool Surface Matrix

This file documents which tools are exposed on which surface in v0.25.4.

- Python registry: 84 tools.
- HTTP/ASGI routes: 84 routes, all registry-aligned.
- Admin-scoped HTTP routes: 25 routes, disabled by default unless `SHADOWPROOF_ENABLE_ADMIN_HTTP=true` and a separate admin token is supplied.
- TypeScript MCP server: 4 deliberately minimal tools.
- OpenAI descriptor file: 35 curated descriptors, not the full registry.
- HTTP/ASGI input-schema coverage: all 84 routes via exact schema files, OpenAI/MCP inline descriptors, shared family schemas, or generic envelope schemas.

## TypeScript MCP minimal surface

- `lean_check`
- `shadowproof_check_draft`
- `shadowproof_validate`
- `shadowproof_validate_draft`

## Admin-scoped HTTP routes

- `/shadowproof_admin_delete_tenant_data` -> `shadowproof_admin_delete_tenant_data`
- `/shadowproof_admin_tenant_report` -> `shadowproof_admin_tenant_report`
- `/shadowproof_create_domain_pack` -> `shadowproof_create_domain_pack`
- `/shadowproof_create_review_packet` -> `shadowproof_create_review_packet`
- `/shadowproof_domain_pack_attach_eval` -> `shadowproof_domain_pack_attach_eval`
- `/shadowproof_domain_pack_eval_stub` -> `shadowproof_domain_pack_eval_stub`
- `/shadowproof_domain_pack_promote` -> `shadowproof_domain_pack_promote`
- `/shadowproof_domain_pack_registry` -> `shadowproof_domain_pack_registry`
- `/shadowproof_domain_pack_review` -> `shadowproof_domain_pack_review`
- `/shadowproof_domain_pack_rollback` -> `shadowproof_domain_pack_rollback`
- `/shadowproof_domain_pack_status` -> `shadowproof_domain_pack_status`
- `/shadowproof_domain_pack_submit` -> `shadowproof_domain_pack_submit`
- `/shadowproof_index_mathlib` -> `shadowproof_index_mathlib`
- `/shadowproof_onboarding_packet` -> `shadowproof_onboarding_packet`
- `/shadowproof_optimize_export_policy` -> `shadowproof_optimize_export_policy`
- `/shadowproof_proof_artifact_attach_validation` -> `shadowproof_proof_artifact_attach_validation`
- `/shadowproof_proof_artifact_export` -> `shadowproof_proof_artifact_export`
- `/shadowproof_proof_artifact_promote` -> `shadowproof_proof_artifact_promote`
- `/shadowproof_proof_artifact_registry` -> `shadowproof_proof_artifact_registry`
- `/shadowproof_proof_artifact_review` -> `shadowproof_proof_artifact_review`
- `/shadowproof_proof_artifact_review_packet` -> `shadowproof_proof_artifact_review_packet`
- `/shadowproof_proof_artifact_status` -> `shadowproof_proof_artifact_status`
- `/shadowproof_proof_artifact_submit` -> `shadowproof_proof_artifact_submit`
- `/shadowproof_release_report` -> `shadowproof_release_report`
- `/shadowproof_retention_sweep` -> `shadowproof_retention_sweep`

## Curated OpenAI descriptor names

- `lean_check`
- `shadowproof_check_draft`
- `shadowproof_compile_formalization_context`
- `shadowproof_compile_repair_context`
- `shadowproof_compile_repair_prompt`
- `shadowproof_config_check`
- `shadowproof_create_review_packet`
- `shadowproof_demorgan_symmetry`
- `shadowproof_draft_schema`
- `shadowproof_env_info`
- `shadowproof_eval`
- `shadowproof_get_domain_pack`
- `shadowproof_index_mathlib`
- `shadowproof_lean_worker_check`
- `shadowproof_list_domains`
- `shadowproof_memory_stats`
- `shadowproof_metrics_report`
- `shadowproof_optimize_export_policy`
- `shadowproof_optimize_record`
- `shadowproof_optimize_stats`
- `shadowproof_optimize_suggest`
- `shadowproof_optimize_train`
- `shadowproof_product_readiness`
- `shadowproof_prometheus_metrics`
- `shadowproof_record_outcome`
- `shadowproof_regression_suite`
- `shadowproof_retention_sweep`
- `shadowproof_retrieve_for_diagnostics`
- `shadowproof_retrieve_mathlib`
- `shadowproof_shadowhott_audit`
- `shadowproof_shadowhott_state`
- `shadowproof_suggest_repair`
- `shadowproof_training_capacity_plan`
- `shadowproof_validate`
- `shadowproof_validate_draft`
