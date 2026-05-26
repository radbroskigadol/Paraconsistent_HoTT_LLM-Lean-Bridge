# Technical Due Diligence Checklist

- Run `python -m pytest -q`.
- Run `python -m compileall -q shadowproof_core`.
- Exercise theorem-drift trap cases.
- Run a Lean-equipped CI build of `lean_project_template`.
- Replace the demo Lean-worker stub with a no-network isolated worker.
- Verify OIDC/bearer tenant binding and admin token separation.
- Verify allowed file roots for every deployment.
- Produce SBOM, image signatures, and vulnerability scan output in buyer CI.
