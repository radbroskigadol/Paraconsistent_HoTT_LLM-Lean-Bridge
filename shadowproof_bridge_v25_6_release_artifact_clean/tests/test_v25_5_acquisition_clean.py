from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.domain_authoring import create_domain_pack, validate_domain_pack
from shadowproof_core.model_providers import call_model_provider
from shadowproof_core.path_guard import PathPolicyError
from shadowproof_core.retrieval import get_domain_pack, list_domain_packs, retrieve_mathlib_context
from shadowproof_core.schema_validation import schema_for_tool, validate_tool_payload


def test_domain_listing_and_get_are_root_guarded(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    external = tmp_path / "external"
    allowed.mkdir()
    external.mkdir()
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(allowed))

    with pytest.raises(PathPolicyError):
        list_domain_packs([str(external)])
    with pytest.raises(PathPolicyError):
        get_domain_pack("secret", [str(external)])


def test_domain_pack_authoring_is_retrievable_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    pack_path = tmp_path / "domains" / "company" / "monoids.json"
    created = create_domain_pack({
        "domain": "monoids",
        "display_name": "Monoids",
        "imports": ["Mathlib.Algebra.Group.Defs"],
        "theorems": [{
            "name": "mul_assoc",
            "statement": "(a * b) * c = a * (b * c)",
            "use_when": "prove associativity in a monoid",
            "example": "simpa [mul_assoc]",
            "tags": ["monoid", "associativity"],
        }],
        "output_path": str(pack_path),
    })
    assert created["status"] == "ok"
    assert validate_domain_pack({"path": str(pack_path)})["status"] == "ok"

    result = retrieve_mathlib_context({
        "query": "prove associativity in a monoid using mul_assoc",
        "domains": ["monoids"],
        "domain_dirs": [str(tmp_path / "domains")],
        "limit": 5,
    })
    assert result.detected_domains == ["monoids"]
    assert any(c.name == "mul_assoc" and c.statement == "(a * b) * c = a * (b * c)" for c in result.candidates)


def test_model_provider_forbids_caller_supplied_egress_fields():
    out = call_model_provider({
        "provider": "frontier_http",
        "model_id": "x",
        "prompt": "hello",
        "provider_url": "https://example.com/model",
        "provider_headers": {"X-Leak": "1"},
        "provider_bearer_token": "caller-token",
    }, ShadowProofConfig(model_provider_url="https://example.com/model"))
    assert out["status"] == "rejected"
    assert "caller-supplied" in out["error"]


def test_model_provider_schema_rejects_deprecated_egress_fields():
    errors = validate_tool_payload("shadowproof_model_provider_call", {
        "provider": "frontier_http",
        "model_id": "x",
        "prompt": "hello",
        "provider_url": "https://example.com/model",
    })
    assert errors
    assert any("provider_url" in e or "Additional properties" in e for e in errors)


def test_model_provider_blocks_private_configured_url(monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_MODEL_PROVIDER_URL", "https://127.0.0.1/v1")
    out = call_model_provider({
        "provider": "frontier_http",
        "model_id": "x",
        "prompt": "hello",
    }, ShadowProofConfig.from_env())
    assert out["status"] == "rejected"
    assert "private" in out["error"] or "loopback" in out["error"]


def test_high_risk_schemas_are_strict():
    for tool in [
        "shadowproof_model_provider_call",
        "shadowproof_list_domains",
        "shadowproof_get_domain_pack",
        "shadowproof_retrieve_mathlib",
        "shadowproof_index_mathlib",
        "shadowproof_create_domain_pack",
        "shadowproof_validate_domain_pack",
        "shadowproof_domain_pack_eval_stub",
    ]:
        schema = schema_for_tool(tool)
        assert schema is not None, tool
        assert schema.get("additionalProperties") is False, tool


def test_api_dockerfile_copies_runtime_artifacts():
    text = Path("deploy/api.Dockerfile").read_text(encoding="utf-8")
    for artifact in ["schemas", "docs", "examples", "scripts", "lean_project_template"]:
        assert f"COPY {artifact} ./{artifact}" in text


def test_docker_copy_layout_preserves_schema_loader(tmp_path):
    root = Path.cwd()
    app = tmp_path / "app"
    for item in ["pyproject.toml", "shadowproof_core", "schemas", "docs", "examples", "scripts", "lean_project_template"]:
        src = root / item
        dst = app / item
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    code = "from shadowproof_core.schema_validation import schema_for_tool; assert schema_for_tool('lean_check') is not None; assert schema_for_tool('shadowproof_model_provider_call') is not None"
    subprocess.run([sys.executable, "-c", code], cwd=app, env={"PYTHONPATH": str(app)}, check=True)
