from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
from dataclasses import dataclass, asdict
from typing import Any
from urllib import request as urlrequest
from urllib.parse import urlparse

from .config import ShadowProofConfig
from .io_limits import capped_read_bytes


@dataclass
class ModelProviderRequest:
    model_id: str
    prompt: str
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    response_format: str = "json"
    privacy_mode: str = "hash_only"


@dataclass
class ModelProviderResponse:
    status: str
    model_id: str
    text: str
    raw: dict[str, Any] | None = None
    error: str | None = None
    estimated_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    attempts: int = 1


def call_model_provider(payload: dict[str, Any], cfg: ShadowProofConfig) -> dict[str, Any]:
    provider = payload.get("provider", "mock")
    req = ModelProviderRequest(
        model_id=str(payload.get("model_id", "unknown_model")),
        prompt=str(payload.get("prompt", "")),
        system=payload.get("system"),
        max_tokens=payload.get("max_tokens"),
        temperature=payload.get("temperature"),
        response_format=str(payload.get("response_format", "json")),
        privacy_mode=str(payload.get("privacy_mode", getattr(cfg, "privacy_mode", "hash_only"))),
    )

    if provider in {"local_deterministic", "local_trace"}:
        return call_local_deterministic(payload, cfg, req)

    if provider == "mock":
        return asdict(ModelProviderResponse(
            status="ok",
            model_id=req.model_id,
            text=json.dumps({"mock": True, "message": "Replace mock provider with company model provider."}),
            estimated_input_tokens=estimate_tokens((req.system or "") + "\n" + req.prompt),
            estimated_output_tokens=20,
        ))

    if provider == "frontier_http":
        return call_frontier_http(payload, cfg, req)

    return asdict(ModelProviderResponse(
        status="external_required",
        model_id=req.model_id,
        text="",
        error=f"Provider {provider} is not implemented. Use `mock`, `frontier_http`, or plug in a company adapter.",
    ))



def call_local_deterministic(payload: dict[str, Any], cfg: ShadowProofConfig, req: ModelProviderRequest) -> dict[str, Any]:
    """Deterministic local stand-in for frontier provider contract tests.

    This provider is deliberately boring: it returns stable JSON fixtures that
    let the bridge exercise provider parsing, prompt plumbing, trace recording,
    and downstream DraftProposal validation without depending on network access
    or a real model.  It does not model semantic quality.
    """
    from .local_simulation import make_identity_draft

    scenario = str(payload.get("scenario", "valid_identity_draft"))
    if scenario == "valid_identity_draft":
        body: dict[str, Any] = {
            "local_simulation": True,
            "message": "local simulation DraftProposal generated deterministically; replace with a frontier provider for quality tests",
            "draft": make_identity_draft(),
        }
    elif scenario == "unknown_identifier_draft":
        body = {
            "local_simulation": True,
            "message": "local simulation DraftProposal with Lean-like unknown identifier failure",
            "draft": make_identity_draft(marker="SHADOWPROOF_MOCK_LEAN_UNKNOWN_IDENTIFIER"),
        }
    elif scenario == "theorem_drift_draft":
        body = {
            "local_simulation": True,
            "message": "local simulation theorem-drift fixture",
            "draft": make_identity_draft(drift=True),
        }
    else:
        body = {
            "local_simulation": True,
            "message": f"unknown local scenario {scenario}; returned echo fixture",
            "echo": {"prompt": req.prompt[:500], "system": (req.system or "")[:500]},
        }

    text = json.dumps(body, sort_keys=True)
    raw = {"status": "ok", "provider": "local_deterministic", "scenario": scenario, "text": text}
    return asdict(ModelProviderResponse(
        status="ok",
        model_id=req.model_id,
        text=text,
        raw=raw if bool(payload.get("return_raw", False)) else None,
        estimated_input_tokens=estimate_tokens((req.system or "") + "\n" + req.prompt),
        estimated_output_tokens=estimate_tokens(text),
    ))


def _extract_text(raw: Any) -> str:
    """Best-effort extraction of generated text from a provider response.

    The previous implementation only checked top-level ``text``/``output_text``/
    ``content`` string keys, which doesn't match any major frontier provider:

    - Anthropic Messages: ``content`` is a list of blocks like
      ``[{"type": "text", "text": "..."}, ...]``.
    - OpenAI Responses: ``output`` is a list of messages, each with
      ``content[*].text`` blocks; sometimes ``output_text`` is also present.
    - OpenAI Chat Completions: ``choices[0].message.content`` is a string.
    - Google Gemini: ``candidates[0].content.parts[*].text``.

    We try them in order and fall back to a JSON dump so the caller at least
    sees what came back.
    """
    if not isinstance(raw, dict):
        return str(raw or "")
    # 1. Simple string fields used by hand-rolled adapters.
    for key in ("text", "output_text", "completion"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            return v
    # 2. Anthropic Messages-style content block list.
    content = raw.get("content")
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content
                 if isinstance(block, dict) and block.get("type") in {None, "text"}]
        joined = "".join(p for p in parts if isinstance(p, str))
        if joined:
            return joined
    if isinstance(content, str) and content:
        return content
    # 3. OpenAI Responses output.
    output = raw.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for msg in output:
            if not isinstance(msg, dict):
                continue
            for block in (msg.get("content") or []):
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        if parts:
            return "".join(parts)
    # 4. OpenAI Chat Completions choices.
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message") or {}
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    # 5. Google Gemini candidates.
    cands = raw.get("candidates")
    if isinstance(cands, list) and cands:
        first = cands[0]
        if isinstance(first, dict):
            inner = (first.get("content") or {}).get("parts") or []
            parts = [p.get("text", "") for p in inner if isinstance(p, dict)]
            joined = "".join(p for p in parts if isinstance(p, str))
            if joined:
                return joined
    return ""


def _forbidden_provider_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_host_public_only(host: str, port: int | None) -> str | None:
    """Fail closed unless every resolved address is public-routable.

    Literal IPs are checked directly.  DNS names are resolved with
    ``socket.getaddrinfo`` and all returned addresses must be non-private,
    non-loopback, non-link-local, non-reserved, non-multicast, and specified.
    NXDOMAIN, resolver failures, or an empty result are treated as policy
    failures because the bridge cannot prove the configured provider target is
    safe.
    """
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:
        if _forbidden_provider_ip(ip):
            return "model-provider URL must not target private, loopback, link-local, reserved, multicast, or unspecified IP ranges"
        return None

    try:
        infos = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return f"model-provider DNS resolution failed closed for host {host!r}: {e}"
    except OSError as e:
        return f"model-provider DNS resolution failed closed for host {host!r}: {e}"
    addresses: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addresses.add(str(sockaddr[0]))
    if not addresses:
        return f"model-provider DNS resolution returned no addresses for host {host!r}"
    for addr in sorted(addresses):
        try:
            resolved_ip = ipaddress.ip_address(addr.strip("[]"))
        except ValueError:
            return f"model-provider DNS resolution returned an unparsable address for host {host!r}: {addr!r}"
        if _forbidden_provider_ip(resolved_ip):
            return f"model-provider host {host!r} resolves to a forbidden IP address: {addr}"
    return None


FORBIDDEN_CALLER_EGRESS_FIELDS = frozenset({"provider_url", "provider_headers", "provider_bearer_token"})


def _parse_provider_url_map(raw: str | None) -> dict[str, str]:
    """Parse ``id=url`` comma-separated provider configuration.

    Example: ``SHADOWPROOF_MODEL_PROVIDER_URLS=openai=https://...,acme=https://...``.
    Caller payloads select a configured provider by ``provider_id``; they do
    not get to provide arbitrary egress URLs or headers.
    """
    out: dict[str, str] = {}
    if not raw:
        return out
    for item in raw.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


def _configured_provider_url(payload: dict[str, Any], cfg: ShadowProofConfig) -> tuple[str | None, str | None]:
    forbidden = sorted(k for k in FORBIDDEN_CALLER_EGRESS_FIELDS if k in payload)
    if forbidden:
        return None, "caller-supplied model-provider egress fields are forbidden: " + ", ".join(forbidden)

    provider_id = str(payload.get("provider_id", "default")).strip() or "default"
    env_name = getattr(cfg, "model_provider_urls_env", "SHADOWPROOF_MODEL_PROVIDER_URLS")
    url_map = _parse_provider_url_map(os.environ.get(env_name))
    default_url = getattr(cfg, "model_provider_url", None) or os.environ.get("SHADOWPROOF_MODEL_PROVIDER_URL")
    if default_url:
        url_map.setdefault("default", default_url)
    url = url_map.get(provider_id)
    if not url:
        return None, f"missing configured provider URL for provider_id={provider_id!r}"
    err = _validate_provider_url(url)
    if err:
        return None, err
    return url, None


def _validate_provider_url(url: str) -> str | None:
    parsed = urlparse(str(url))
    if parsed.scheme not in {"https", "http"}:
        return "model-provider URL must use https; http is allowed only with SHADOWPROOF_ALLOW_INSECURE_PROVIDER_URLS=1"
    if parsed.scheme == "http" and os.environ.get("SHADOWPROOF_ALLOW_INSECURE_PROVIDER_URLS", "").lower() not in {"1", "true", "yes", "on"}:
        return "model-provider URL must use https; set SHADOWPROOF_ALLOW_INSECURE_PROVIDER_URLS=1 only for local testing"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "model-provider URL is missing a host"
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return "model-provider host must not be localhost or .local"
    return _resolve_host_public_only(host, parsed.port)


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        out = int(value)
    except Exception:
        out = default
    return max(minimum, min(maximum, out))


def call_frontier_http(payload: dict[str, Any], cfg: ShadowProofConfig, req: ModelProviderRequest) -> dict[str, Any]:
    url, policy_error = _configured_provider_url(payload, cfg)
    if policy_error:
        return asdict(ModelProviderResponse("rejected", req.model_id, "", error=policy_error))
    if not url:
        return asdict(ModelProviderResponse("external_required", req.model_id, "", error="missing configured provider URL"))

    headers = {"Content-Type": "application/json"}
    token_env = getattr(cfg, "model_provider_bearer_token_env", "SHADOWPROOF_MODEL_PROVIDER_BEARER_TOKEN")
    token = os.environ.get(token_env)
    provider_id = str(payload.get("provider_id", "default")).strip().upper().replace("-", "_")
    token = os.environ.get(f"SHADOWPROOF_MODEL_PROVIDER_TOKEN_{provider_id}", token)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(asdict(req)).encode("utf-8")
    timeout = _bounded_int(payload.get("timeout_seconds", 60), 60, minimum=1, maximum=120)
    retries = _bounded_int(payload.get("retries", 1), 1, minimum=0, maximum=3)
    return_raw = bool(payload.get("return_raw", False)) and os.environ.get("SHADOWPROOF_MODEL_PROVIDER_RETURN_RAW", "").lower() in {"1", "true", "yes", "on"}
    last_error = None
    for attempt in range(1, retries + 2):
        http_req = urlrequest.Request(str(url), data=body, headers=headers)
        try:
            max_response_bytes = _bounded_int(
                getattr(cfg, "model_provider_response_max_bytes", 2_000_000),
                2_000_000,
                minimum=1024,
                maximum=20_000_000,
            )
            with urlrequest.urlopen(http_req, timeout=timeout) as resp:
                body_bytes = capped_read_bytes(resp, max_response_bytes)
                raw = json.loads(body_bytes.decode("utf-8"))
            text = _extract_text(raw)
            return asdict(ModelProviderResponse(
                status=str(raw.get("status", "ok")) if isinstance(raw, dict) else "ok",
                model_id=req.model_id,
                text=text,
                raw=raw if return_raw else None,
                estimated_input_tokens=estimate_tokens((req.system or "") + "\n" + req.prompt),
                estimated_output_tokens=estimate_tokens(text),
                attempts=attempt,
            ))
        except Exception as e:
            last_error = str(e)
            if attempt <= retries:
                time.sleep(min(8.0, (2 ** (attempt - 1)) * 0.25))
    return asdict(ModelProviderResponse("error", req.model_id, "", error=last_error, attempts=retries + 1))


def estimate_tokens(text: str) -> int:
    return max(1, len(str(text)) // 4)
