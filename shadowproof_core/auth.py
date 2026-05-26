from __future__ import annotations

import hmac
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Protocol

from .config import ShadowProofConfig


@dataclass
class RequestContext:
    tenant_id: str
    user_id: str | None
    auth_subject: str | None
    authenticated: bool
    quota_allowed: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RateLimiter(Protocol):
    name: str
    def allow(self, key: str, per_minute: int) -> bool: ...
    def health_check(self) -> dict[str, Any]: ...


class MemoryRateLimiter:
    name = "memory"

    def __init__(self):
        self.buckets: dict[str, list[float]] = {}

    def allow(self, key: str, per_minute: int) -> bool:
        now = time.time()
        window_start = now - 60.0
        bucket = [t for t in self.buckets.get(key, []) if t >= window_start]
        if len(bucket) >= per_minute:
            self.buckets[key] = bucket
            return False
        bucket.append(now)
        self.buckets[key] = bucket
        return True

    def health_check(self) -> dict[str, Any]:
        return {"name": "quota", "backend": self.name, "status": "ok", "detail": "in-process limiter"}


class RedisRateLimiter:
    name = "redis"

    def __init__(self, redis_url: str | None):
        self.redis_url = redis_url
        self._client_cache = None

    def _client(self):
        if not self.redis_url:
            raise RuntimeError("SHADOWPROOF_REDIS_URL is required for redis quota mode")
        if self._client_cache is not None:
            return self._client_cache
        try:
            import redis  # type: ignore
        except Exception as e:  # pragma: no cover - optional prod dependency
            raise RuntimeError("redis package is not installed; install shadowproof-bridge[prod]") from e
        # redis-py manages a connection pool internally per-client; we just
        # need to avoid building a fresh client (and its pool) on every call.
        self._client_cache = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client_cache

    def allow(self, key: str, per_minute: int) -> bool:
        r = self._client()
        now_bucket = int(time.time() // 60)
        redis_key = f"shadowproof:quota:{key}:{now_bucket}"
        count = int(r.incr(redis_key))
        if count == 1:
            r.expire(redis_key, 70)
        return count <= per_minute

    def health_check(self) -> dict[str, Any]:
        try:
            self._client().ping()
            return {"name": "quota", "backend": self.name, "status": "ok", "detail": "redis ping ok"}
        except Exception as e:
            return {"name": "quota", "backend": self.name, "status": "fail", "detail": str(e)}


_GLOBAL_LIMITER = MemoryRateLimiter()
_REDIS_LIMITERS: dict[str | None, RedisRateLimiter] = {}


def get_rate_limiter(cfg: ShadowProofConfig) -> RateLimiter:
    if str(cfg.quota_mode).lower() == "redis":
        key = cfg.redis_url
        if key not in _REDIS_LIMITERS:
            _REDIS_LIMITERS[key] = RedisRateLimiter(cfg.redis_url)
        return _REDIS_LIMITERS[key]
    return _GLOBAL_LIMITER


def quota_health_check(cfg: ShadowProofConfig) -> dict[str, Any]:
    if str(cfg.quota_mode).lower() == "external":
        return {"name": "quota", "backend": "external", "status": "warn", "detail": "external quota service configured; active probe belongs to deployment"}
    return get_rate_limiter(cfg).health_check()


def parse_bearer_tokens(cfg: ShadowProofConfig) -> dict[str, str]:
    raw = os.environ.get(cfg.bearer_tokens_env, "")
    out: dict[str, str] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        if ":" in part:
            token, tenant = part.split(":", 1)
        else:
            token, tenant = part, cfg.default_tenant_id
        out[token.strip()] = tenant.strip()
    return out


def _extract_token(payload: dict[str, Any]) -> str | None:
    token = payload.get("bearer_token") or payload.get("authorization")
    if isinstance(token, str) and token.lower().startswith("bearer "):
        return token[7:].strip()
    return str(token) if token else None


def _validate_oidc_token(token: str | None, cfg: ShadowProofConfig) -> tuple[bool, dict[str, Any] | None, str]:
    """Validate an OIDC/JWT bearer token when optional PyJWT is installed.

    This is an enterprise-auth scaffold, not a fake verifier: without PyJWT and
    a JWKS/issuer/audience configuration, it fails closed.
    """
    if not token:
        return False, None, "missing bearer token"
    if not (cfg.oidc_issuer and cfg.oidc_audience and cfg.oidc_jwks_url):
        return False, None, "OIDC issuer, audience, and JWKS URL must be configured"
    try:
        import jwt  # type: ignore
        from jwt import PyJWKClient  # type: ignore
    except Exception as e:  # pragma: no cover - optional prod dependency
        return False, None, f"PyJWT is not installed: {e}"
    try:
        signing_key = PyJWKClient(cfg.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=cfg.oidc_audience,
            issuer=cfg.oidc_issuer,
        )
        return True, dict(claims), ""
    except Exception as e:
        return False, None, f"OIDC validation failed: {e}"


_ILLEGAL_TENANT_IDS = frozenset({"", ".", "..", "/"})


def _validate_tenant_id(tenant_id: str) -> tuple[bool, str]:
    """Reject tenant_ids that would escape the tenants/ directory.

    The storage layer maps tenant_id through a `re.sub(r"[^A-Za-z0-9_.-]+",
    "_", ...)` filter that lets ``.`` through; the resulting path ``..`` then
    resolves to the parent directory.  We also reject empty strings and any
    value that, after the safety filter, only contains dots and dashes.
    """
    if not isinstance(tenant_id, str):
        return False, "tenant_id must be a string"
    if tenant_id in _ILLEGAL_TENANT_IDS:
        return False, f"tenant_id {tenant_id!r} is reserved and not allowed"
    stripped = tenant_id.strip()
    if not stripped:
        return False, "tenant_id may not be blank"
    # Disallow values whose entire content is dots (.., ..., ....).
    if set(stripped) <= {"."}:
        return False, f"tenant_id {tenant_id!r} would resolve outside the tenants directory"
    return True, ""


def build_request_context(payload: dict[str, Any], cfg: ShadowProofConfig) -> RequestContext:
    requested_tenant = payload.get("tenant_id")
    tenant_id = str(requested_tenant or cfg.default_tenant_id)
    user_id = payload.get("user_id")
    token = _extract_token(payload)

    mode = str(cfg.auth_mode).lower()
    environment = str(cfg.environment).lower()
    authenticated = mode == "disabled" and environment in {"development", "dev", "local", "test"}
    subject = None
    reason = ""

    if mode == "disabled" and not authenticated:
        reason = "auth_mode=disabled is only allowed in development/local/test environments"

    if mode == "bearer":
        tokens = parse_bearer_tokens(cfg)
        authenticated = False
        matched_tenant: str | None = None
        for known, tenant in tokens.items():
            if token and hmac.compare_digest(str(token), known):
                authenticated = True
                matched_tenant = tenant
                subject = f"bearer:{tenant}"
                break
        if not authenticated:
            reason = "invalid or missing bearer token"
        else:
            # The token binds the caller to its declared tenant in BOTH
            # single_tenant and multi_tenant modes.  Previously multi_tenant
            # mode allowed a caller with a valid tenant-A token to claim to
            # be tenant B by sending `{"tenant_id":"B"}`.  We now require
            # any caller-supplied tenant_id to match the token's tenant.
            if requested_tenant is not None and str(requested_tenant) != str(matched_tenant):
                authenticated = False
                reason = "tenant_id does not match bearer token's tenant"
            else:
                tenant_id = str(matched_tenant)

    elif mode == "oidc":
        authenticated, claims, reason = _validate_oidc_token(token, cfg)
        if authenticated and claims is not None:
            subject = f"oidc:{claims.get(cfg.oidc_user_claim) or claims.get('sub')}"
            user_id = user_id or claims.get(cfg.oidc_user_claim) or claims.get("sub")
            claim_tenant = claims.get(cfg.oidc_tenant_claim)
            if claim_tenant:
                # The tenant claim from the verified JWT is authoritative.
                # Any payload-supplied tenant_id must match it.
                if requested_tenant is not None and str(requested_tenant) != str(claim_tenant):
                    authenticated = False
                    reason = "tenant_id does not match OIDC tenant claim"
                else:
                    tenant_id = str(claim_tenant)

    if authenticated:
        ok, why = _validate_tenant_id(tenant_id)
        if not ok:
            authenticated = False
            reason = why

    quota_allowed = True
    quota_mode = str(cfg.quota_mode).lower()
    if authenticated and quota_mode in {"memory", "redis"}:
        quota_key = f"{tenant_id}:{user_id or 'anonymous'}"
        try:
            quota_allowed = get_rate_limiter(cfg).allow(quota_key, cfg.requests_per_minute)
        except Exception as e:
            quota_allowed = False
            reason = f"quota backend unavailable: {e}"
        if not quota_allowed and not reason:
            reason = "rate limit exceeded"

    return RequestContext(
        tenant_id=tenant_id,
        user_id=str(user_id) if user_id is not None else None,
        auth_subject=subject,
        authenticated=authenticated,
        quota_allowed=quota_allowed,
        reason=reason,
    )


def require_request_allowed(payload: dict[str, Any], cfg: ShadowProofConfig) -> tuple[bool, RequestContext, dict[str, Any] | None]:
    ctx = build_request_context(payload, cfg)
    if not ctx.authenticated:
        return False, ctx, {"status": "unauthorized", "error": ctx.reason, "request_context": ctx.to_dict()}
    if not ctx.quota_allowed:
        return False, ctx, {"status": "rate_limited", "error": ctx.reason, "request_context": ctx.to_dict()}
    return True, ctx, None
