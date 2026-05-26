"""Regression tests for the security defects discovered during the v0.25.x
audit and fixed in this release.  Each test corresponds to a published
defect id documented in SECURITY.md and CHANGELOG.md.
"""
import os
import pathlib

import pytest

from shadowproof_core.auth import _validate_tenant_id, build_request_context
from shadowproof_core.config import ShadowProofConfig, load_config
from shadowproof_core.storage import _safe_tenant_segment, tenant_dir
from shadowproof_core.tool_api import (
    shadowproof_lean_worker_check,
    shadowproof_retention_sweep,
)


# ---------------------------------------------------------------------------
# CRIT-1: user-supplied payload.config no longer overrides server config
# ---------------------------------------------------------------------------


def test_crit1_load_config_ignores_payload_config_block(monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE", raising=False)
    monkeypatch.setenv("SHADOWPROOF_LEAN_CMD", "lake env lean")
    cfg = load_config({"config": {"lean_command": "/bin/evil",
                                   "data_dir": "/etc",
                                   "retention_days": 0}})
    # None of the dangerous fields should be honored.
    assert cfg.lean_command == "lake env lean"
    assert cfg.data_dir != "/etc"
    assert cfg.retention_days != 0


def test_crit1_lean_worker_does_not_execute_payload_lean_command(tmp_path, monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE", raising=False)
    monkeypatch.setenv("SHADOWPROOF_LEAN_CMD", "lake env lean")
    canary = tmp_path / "SHOULD_NOT_EXIST"
    assert not canary.exists()
    out = shadowproof_lean_worker_check({
        "request_id": "exploit-attempt",
        "code": "import Mathlib\n",
        "config": {
            "lean_command": f"/usr/bin/touch {canary}",
            "lean_worker_mode": "local",
        },
    })
    assert not canary.exists(), "lean_command override must NOT execute"
    # The legit lake binary is not installed in CI, so we expect a benign
    # not_available outcome rather than RCE.
    assert out["lean_status"] in {"not_available", "timeout", "unknown"}


def test_crit1_safe_override_allowlist_works_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE", "1")
    cfg = load_config({"config": {
        "lean_command": "/bin/evil",     # NOT in allowlist
        "data_dir": "/etc",              # NOT in allowlist
        "retention_days": 7,             # IN allowlist
        "requests_per_minute": 999,      # IN allowlist
    }})
    # Dangerous fields are still rejected even with the opt-in env knob.
    assert cfg.lean_command != "/bin/evil"
    assert cfg.data_dir != "/etc"
    # Safe fields are honored.
    assert cfg.retention_days == 7
    assert cfg.requests_per_minute == 999


# ---------------------------------------------------------------------------
# CRIT-2: retention sweep no longer obeys a payload-supplied data_dir
# ---------------------------------------------------------------------------


def test_crit2_retention_sweep_cannot_be_pointed_at_arbitrary_path(tmp_path, monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_ALLOW_PAYLOAD_CONFIG_OVERRIDE", raising=False)
    victim_root = tmp_path / "victim"
    victim_root.mkdir()
    victim = victim_root / "innocent.jsonl"
    victim.write_text("{}\n", encoding="utf-8")
    # Backdate so retention_days=0 would otherwise sweep it.
    os.utime(victim, (0, 0))

    out = shadowproof_retention_sweep({
        "request_id": "rs",
        "config": {"data_dir": str(victim_root), "retention_days": 0},
    })
    assert victim.exists(), "retention sweep must not be redirected via payload.config"
    # The sweep should have run against the env-configured data_dir, which
    # does not contain the victim file.  We don't assert removed==0 strictly
    # because the env-configured data_dir may legitimately contain other
    # .jsonls; we only assert that the victim survived.
    assert "status" in out


# ---------------------------------------------------------------------------
# CRIT-3a: tenant impersonation in multi_tenant mode is blocked
# ---------------------------------------------------------------------------


@pytest.fixture
def bearer_cfg(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_AUTH_MODE", "bearer")
    monkeypatch.setenv("SHADOWPROOF_TENANT_MODE", "multi_tenant")
    monkeypatch.setenv("SHADOWPROOF_BEARER_TOKENS", "tokA:tenantA,tokB:tenantB")
    return load_config({})


def test_crit3a_payload_tenant_matching_token_tenant_is_accepted(bearer_cfg):
    ctx = build_request_context({"bearer_token": "tokA", "tenant_id": "tenantA"}, bearer_cfg)
    assert ctx.authenticated is True
    assert ctx.tenant_id == "tenantA"


def test_crit3a_payload_tenant_mismatch_fails_auth(bearer_cfg):
    ctx = build_request_context({"bearer_token": "tokA", "tenant_id": "tenantB"}, bearer_cfg)
    assert ctx.authenticated is False
    assert "tenant_id" in ctx.reason.lower()


def test_crit3a_omitting_tenant_id_uses_token_tenant(bearer_cfg):
    ctx = build_request_context({"bearer_token": "tokA"}, bearer_cfg)
    assert ctx.authenticated is True
    assert ctx.tenant_id == "tenantA"


def test_crit3a_single_tenant_mode_also_binds_to_token(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_AUTH_MODE", "bearer")
    monkeypatch.setenv("SHADOWPROOF_TENANT_MODE", "single_tenant")
    monkeypatch.setenv("SHADOWPROOF_BEARER_TOKENS", "tokA:tenantA")
    cfg = load_config({})
    # Even though the legacy single_tenant path also bound to the token,
    # we now confirm it explicitly so a future refactor cannot regress it.
    ctx = build_request_context({"bearer_token": "tokA", "tenant_id": "tenantB"}, cfg)
    assert ctx.authenticated is False


# ---------------------------------------------------------------------------
# CRIT-3b: tenant_dir refuses values that escape the tenants/ root
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tid", ["", ".", "..", "...", "....", " ", "/", "...."])
def test_crit3b_safe_tenant_segment_rejects_illegal(tid):
    with pytest.raises(ValueError):
        _safe_tenant_segment(tid)


def test_crit3b_safe_tenant_segment_accepts_legitimate():
    assert _safe_tenant_segment("acme") == "acme"
    assert _safe_tenant_segment("tenant-1") == "tenant-1"
    assert _safe_tenant_segment("Acme_2024.q1") == "Acme_2024.q1"


def test_crit3b_tenant_dir_traversal_is_rejected(tmp_path):
    cfg = ShadowProofConfig(data_dir=str(tmp_path))
    with pytest.raises(ValueError):
        tenant_dir(cfg, "..")
    with pytest.raises(ValueError):
        tenant_dir(cfg, ".")
    # Verify a legit tenant still resolves under tenants/.
    p = tenant_dir(cfg, "acme")
    expected_root = (tmp_path / "tenants").resolve()
    assert p.resolve().is_relative_to(expected_root)


def test_crit3b_traversal_attempts_through_slashes_get_filtered(tmp_path):
    cfg = ShadowProofConfig(data_dir=str(tmp_path))
    # `../foo` -> `_foo` after stripping leading dots; stays under tenants/.
    p = tenant_dir(cfg, "../foo")
    expected_root = (tmp_path / "tenants").resolve()
    assert p.resolve().is_relative_to(expected_root)


def test_validate_tenant_id_helper():
    ok, _ = _validate_tenant_id("acme")
    assert ok is True
    for bad in ["", ".", "..", "....", " "]:
        ok, why = _validate_tenant_id(bad)
        assert ok is False
        assert why  # non-empty reason
