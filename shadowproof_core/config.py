from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class ShadowProofConfig:
    environment: str = "development"
    service_name: str = "shadowproof"
    data_dir: str = ".shadowproof_data"
    tenant_mode: str = "single_tenant"  # single_tenant | multi_tenant
    default_tenant_id: str = "default"
    auth_mode: str = "disabled"  # disabled | bearer | oidc
    bearer_tokens_env: str = "SHADOWPROOF_BEARER_TOKENS"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_tenant_claim: str = "tenant_id"
    oidc_user_claim: str = "sub"
    quota_mode: str = "memory"  # memory | redis | external
    redis_url: str | None = None
    requests_per_minute: int = 120
    storage_backend: str = "jsonl"  # jsonl | postgres
    postgres_dsn: str | None = None
    enable_access_log_json: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "shadowproof-api"
    max_request_bytes: int = 1_000_000
    lean_worker_mode: str = "local"  # local | http | disabled
    lean_worker_url: str | None = None
    lean_command: str = "lake env lean"
    lean_timeout_seconds: int = 30
    lean_memory_mb: int = 2048
    sandbox_network_disabled: bool = True
    privacy_mode: str = "hash_only"  # hash_only | redacted | raw_local
    retention_days: int = 30
    metrics_enabled: bool = True
    metrics_path: str = ".shadowproof_data/metrics/events.jsonl"
    audit_log_path: str = ".shadowproof_data/audit/audit.jsonl"
    review_packet_dir: str = ".shadowproof_data/review_packets"
    retrieval_backend: str = "lexical"  # lexical | vector_http | custom
    vector_retrieval_url: str | None = None
    model_provider_url: str | None = None
    model_provider_urls_env: str = "SHADOWPROOF_MODEL_PROVIDER_URLS"
    model_provider_bearer_token_env: str = "SHADOWPROOF_MODEL_PROVIDER_BEARER_TOKEN"
    policy_path: str = ".shadowproof_opt/policies.json"
    domain_dirs: tuple[str, ...] = ("domains",)
    enable_admin_http: bool = False
    admin_bearer_tokens_env: str = "SHADOWPROOF_ADMIN_BEARER_TOKENS"

    @classmethod
    def from_env(cls) -> "ShadowProofConfig":
        def bool_env(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.lower() in {"1", "true", "yes", "on"}

        def int_env(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, str(default)))
            except Exception:
                return default

        domain_dirs = tuple(x.strip() for x in os.environ.get("SHADOWPROOF_DOMAIN_DIRS", "domains").split(",") if x.strip())

        return cls(
            environment=os.environ.get("SHADOWPROOF_ENVIRONMENT", "development"),
            service_name=os.environ.get("SHADOWPROOF_SERVICE_NAME", "shadowproof"),
            data_dir=os.environ.get("SHADOWPROOF_DATA_DIR", ".shadowproof_data"),
            tenant_mode=os.environ.get("SHADOWPROOF_TENANT_MODE", "single_tenant"),
            default_tenant_id=os.environ.get("SHADOWPROOF_DEFAULT_TENANT_ID", "default"),
            auth_mode=os.environ.get("SHADOWPROOF_AUTH_MODE", "disabled"),
            bearer_tokens_env=os.environ.get("SHADOWPROOF_BEARER_TOKENS_ENV", "SHADOWPROOF_BEARER_TOKENS"),
            oidc_issuer=os.environ.get("SHADOWPROOF_OIDC_ISSUER"),
            oidc_audience=os.environ.get("SHADOWPROOF_OIDC_AUDIENCE"),
            oidc_jwks_url=os.environ.get("SHADOWPROOF_OIDC_JWKS_URL"),
            oidc_tenant_claim=os.environ.get("SHADOWPROOF_OIDC_TENANT_CLAIM", "tenant_id"),
            oidc_user_claim=os.environ.get("SHADOWPROOF_OIDC_USER_CLAIM", "sub"),
            quota_mode=os.environ.get("SHADOWPROOF_QUOTA_MODE", "memory").strip().lower(),
            redis_url=os.environ.get("SHADOWPROOF_REDIS_URL"),
            storage_backend=os.environ.get("SHADOWPROOF_STORAGE_BACKEND", "jsonl"),
            postgres_dsn=os.environ.get("SHADOWPROOF_POSTGRES_DSN"),
            enable_access_log_json=bool_env("SHADOWPROOF_ACCESS_LOG_JSON", True),
            otel_enabled=bool_env("SHADOWPROOF_OTEL_ENABLED", False),
            otel_service_name=os.environ.get("SHADOWPROOF_OTEL_SERVICE_NAME", "shadowproof-api"),
            requests_per_minute=int_env("SHADOWPROOF_REQUESTS_PER_MINUTE", 120),
            max_request_bytes=int_env("SHADOWPROOF_MAX_REQUEST_BYTES", 1_000_000),
            lean_worker_mode=os.environ.get("SHADOWPROOF_LEAN_WORKER_MODE", "local"),
            lean_worker_url=os.environ.get("SHADOWPROOF_LEAN_WORKER_URL"),
            lean_command=os.environ.get("SHADOWPROOF_LEAN_CMD", "lake env lean"),
            lean_timeout_seconds=int_env("SHADOWPROOF_LEAN_TIMEOUT_SECONDS", 30),
            lean_memory_mb=int_env("SHADOWPROOF_LEAN_MEMORY_MB", 2048),
            sandbox_network_disabled=bool_env("SHADOWPROOF_SANDBOX_NETWORK_DISABLED", True),
            privacy_mode=os.environ.get("SHADOWPROOF_PRIVACY_MODE", "hash_only"),
            retention_days=int_env("SHADOWPROOF_RETENTION_DAYS", 30),
            metrics_enabled=bool_env("SHADOWPROOF_METRICS_ENABLED", True),
            metrics_path=os.environ.get("SHADOWPROOF_METRICS_PATH", ".shadowproof_data/metrics/events.jsonl"),
            audit_log_path=os.environ.get("SHADOWPROOF_AUDIT_LOG_PATH", ".shadowproof_data/audit/audit.jsonl"),
            review_packet_dir=os.environ.get("SHADOWPROOF_REVIEW_PACKET_DIR", ".shadowproof_data/review_packets"),
            retrieval_backend=os.environ.get("SHADOWPROOF_RETRIEVAL_BACKEND", "lexical"),
            vector_retrieval_url=os.environ.get("SHADOWPROOF_VECTOR_RETRIEVAL_URL"),
            model_provider_url=os.environ.get("SHADOWPROOF_MODEL_PROVIDER_URL"),
            model_provider_urls_env=os.environ.get("SHADOWPROOF_MODEL_PROVIDER_URLS_ENV", "SHADOWPROOF_MODEL_PROVIDER_URLS"),
            model_provider_bearer_token_env=os.environ.get("SHADOWPROOF_MODEL_PROVIDER_BEARER_TOKEN_ENV", "SHADOWPROOF_MODEL_PROVIDER_BEARER_TOKEN"),
            policy_path=os.environ.get("SHADOWPROOF_OPT_POLICY_PATH", ".shadowproof_opt/policies.json"),
            domain_dirs=domain_dirs or ("domains",),
            enable_admin_http=bool_env("SHADOWPROOF_ENABLE_ADMIN_HTTP", False),
            admin_bearer_tokens_env=os.environ.get("SHADOWPROOF_ADMIN_BEARER_TOKENS_ENV", "SHADOWPROOF_ADMIN_BEARER_TOKENS"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ensure_dirs(self) -> None:
        for p in [
            self.data_dir,
            Path(self.metrics_path).parent,
            Path(self.audit_log_path).parent,
            self.review_packet_dir,
        ]:
            Path(p).mkdir(parents=True, exist_ok=True)


def load_config(payload: dict[str, Any] | None = None) -> ShadowProofConfig:
    """Load the server configuration from environment variables only.

    The ``payload`` argument is accepted purely for backward compatibility with
    older call sites and is intentionally **not** consulted.  Allowing a
    request body to override server configuration is a privilege-escalation
    vector: under the old behaviour an authenticated caller could supply
    ``{"config": {"lean_command": "..."}}`` to ``shadowproof_lean_worker_check``
    and obtain remote code execution, or supply ``{"config": {"data_dir": ...,
    "retention_days": 0}}`` to ``shadowproof_retention_sweep`` to delete
    ``.jsonl`` files anywhere on disk the server process can reach.

    If a deployment genuinely needs per-request configuration variation, the
    operator can set ``SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE=1`` in the
    environment, which restores the old merge behaviour against an explicit
    allowlist of safe fields.  Do not enable this in production.
    """
    cfg = ShadowProofConfig.from_env()
    if os.environ.get("SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE", "").lower() not in {"1", "true", "yes", "on"}:
        return cfg

    payload = payload or {}
    raw = payload.get("config") or {}
    if not isinstance(raw, dict):
        return cfg

    # Even when explicitly opted in we restrict the overridable surface to
    # fields that cannot lead to RCE, arbitrary file deletion, or auth bypass.
    _SAFE_OVERRIDE_FIELDS = frozenset({
        "metrics_enabled",
        "enable_access_log_json",
        "otel_enabled",
        "otel_service_name",
        "service_name",
        "requests_per_minute",
        "max_request_bytes",
        "lean_timeout_seconds",
        "retention_days",
    })
    for k, v in raw.items():
        if k in _SAFE_OVERRIDE_FIELDS and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg
