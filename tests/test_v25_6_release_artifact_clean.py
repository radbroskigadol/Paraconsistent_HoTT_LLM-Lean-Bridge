from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.lean_runner import LeanRunner
from shadowproof_core.model_providers import _read_bounded_response, _validate_provider_url
from shadowproof_core.path_guard import PathPolicyError, allowed_roots
from shadowproof_core.schema_validation import schema_for_tool, validate_tool_payload


def test_packaged_schema_directory_is_authoritative():
    # This catches wheel/source-tree drift: schemas must exist inside the package,
    # not only as a repository sibling directory.
    import shadowproof_core.schema_validation as sv
    assert sv.PACKAGE_SCHEMA_DIR.exists()
    assert (sv.PACKAGE_SCHEMA_DIR / "lean_check.input.schema.json").exists()
    assert schema_for_tool("lean_check") is not None
    assert schema_for_tool("shadowproof_model_provider_call") is not None


def test_wheel_install_preserves_runtime_schemas(tmp_path):
    if os.environ.get("RUN_WHEEL_TEST") not in {"1", "true", "yes", "on"}:
        pytest.skip("wheel smoke is run as a dedicated CI/release step to keep unit tests hermetic")
    wheel_dir = tmp_path / "wheelhouse"
    target = tmp_path / "site"
    wheel_dir.mkdir()
    target.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", ".", "-w", str(wheel_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wheels = list(wheel_dir.glob("shadowproof_bridge-0.25.*-*.whl"))
    assert wheels, list(wheel_dir.iterdir())
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheels[0])],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    code = "from shadowproof_core.schema_validation import schema_for_tool; assert schema_for_tool('lean_check'); assert schema_for_tool('shadowproof_model_provider_call')"
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env={"PYTHONPATH": str(target)}, check=True)


def test_cli_schema_validation_rejects_deprecated_egress_fields(tmp_path):
    req = tmp_path / "bad_provider.json"
    req.write_text(json.dumps({
        "provider": "frontier_http",
        "model_id": "x",
        "prompt": "hello",
        "provider_url": "https://example.com/model",
    }), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "shadowproof_core.cli", "model-provider-call", str(req)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.returncode != 0
    assert "schema validation" in proc.stderr or "schema validation" in proc.stdout


def test_model_provider_dns_guard_rejects_private_resolution(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert "forbidden" in (_validate_provider_url("https://frontier.example/v1") or "")


def test_model_provider_dns_guard_allows_public_resolution(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert _validate_provider_url("https://frontier.example/v1") is None


class _FakeResponse:
    def __init__(self, data: bytes):
        self.data = data
    def read(self, n: int = -1) -> bytes:
        return self.data if n < 0 else self.data[:n]


def test_model_provider_response_read_is_bounded():
    with pytest.raises(ValueError):
        _read_bounded_response(_FakeResponse(b"x" * 20), max_bytes=10)
    assert _read_bounded_response(_FakeResponse(b"{}"), max_bytes=10) == b"{}"


def test_production_allowed_roots_fail_closed(monkeypatch):
    monkeypatch.delenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", raising=False)
    monkeypatch.setenv("SHADOWPROOF_ENVIRONMENT", "production")
    with pytest.raises(PathPolicyError):
        allowed_roots()


def test_lean_runner_caps_stdout(tmp_path):
    script = tmp_path / "noisy.py"
    script.write_text("import sys\nprint('x' * 50000)\n", encoding="utf-8")
    runner = LeanRunner(command=f"{sys.executable} {script}", timeout_seconds=5, max_output_bytes=8192)
    result = runner.check_file(tmp_path / "dummy.lean")
    assert len(result.stdout.encode("utf-8")) < 9000
    assert "output truncated" in result.stdout


def test_string_return_raw_rejected_by_schema():
    errors = validate_tool_payload("shadowproof_model_provider_call", {
        "provider": "frontier_http",
        "model_id": "x",
        "prompt": "hello",
        "return_raw": "false",
    })
    assert errors
