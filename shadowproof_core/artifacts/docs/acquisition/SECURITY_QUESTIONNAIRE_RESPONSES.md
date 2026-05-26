# Security Questionnaire Starter

- Auth: bearer/OIDC scaffold; disabled auth fails closed outside development.
- Admin: admin HTTP routes disabled by default and require a separate admin token when enabled.
- Paths: caller-controlled file paths are constrained to configured allowed roots.
- Request validation: JSON schema validation runs before tool dispatch for shipped schemas.
- Sandbox: demo worker is not a production sandbox; production requires isolated no-network execution.
