# Evaluation harness

The package includes three local, no-network evaluation layers:

1. `shadowproof_eval` runs case-based bridge checks against a selected tool.
2. `shadowproof_shadowhott_eval` checks ShadowHoTT lane/verdict/bilattice expectations.
3. `shadowproof_regression_suite` combines ShadowHoTT, retrieval, prompt-efficiency, bridge, and optional Lean-validation sections.

All file-backed suite inputs are resolved through `SHADOWPROOF_ALLOWED_FILE_ROOTS` before being read. Relative paths resolve under the current working directory by default. Set `SHADOWPROOF_ALLOWED_FILE_ROOTS=/path/to/project,/path/to/evals` when running suites stored outside the service working directory.

Typical local runs:

```bash
python -m shadowproof_core.cli shadowhott-eval examples/evals/shadowhott_eval.json
python -m shadowproof_core.cli regression examples/evals/regression_suite.json
python -m shadowproof_core.cli eval examples/evals/bridge_eval.json
```

The shipped example corpora are smoke-test sized. Production or acquisition diligence should add large domain-specific positive, negative, theorem-drift, retrieval-miss, and hostile-input cases.
