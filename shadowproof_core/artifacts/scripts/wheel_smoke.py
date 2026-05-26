#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="shadowproof_wheel_smoke_") as td:
    td_path = Path(td)
    wheelhouse = td_path / "wheelhouse"
    install_dir = td_path / "install"
    run_dir = td_path / "run"
    wheelhouse.mkdir()
    install_dir.mkdir()
    run_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", ".", "-w", str(wheelhouse)],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    wheels = sorted(wheelhouse.glob("shadowproof_bridge-*.whl"))
    if not wheels:
        raise SystemExit("no shadowproof_bridge wheel built")
    with zipfile.ZipFile(wheels[-1]) as zf:
        zf.extractall(install_dir)

    code = r'''
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, os.environ["SP_INSTALL_DIR"])
from shadowproof_core.schema_validation import schema_for_tool, validate_tool_payload
assert schema_for_tool("lean_check") is not None
assert schema_for_tool("shadowproof_model_provider_call") is not None
assert validate_tool_payload("shadowproof_list_domains", {"request_id":"x", "roots":["."], "unexpected": True})
req = Path(tempfile.mkdtemp()) / "req.json"
req.write_text(json.dumps({"request_id":"x", "roots":["."], "unexpected": True}), encoding="utf-8")
proc = subprocess.run(
    [sys.executable, "-m", "shadowproof_core.cli", "list-domains", str(req)],
    cwd=os.environ["SP_RUN_DIR"],
    env={**os.environ, "PYTHONPATH": os.environ["SP_INSTALL_DIR"]},
    text=True,
    capture_output=True,
    timeout=30,
)
assert proc.returncode == 2, proc.stdout + proc.stderr
assert "schema_validation_failed" in proc.stdout
'''
    full_env = {
        **os.environ,
        "SP_INSTALL_DIR": str(install_dir),
        "SP_RUN_DIR": str(run_dir),
        "PYTHONPATH": str(install_dir),
    }
    subprocess.run([sys.executable, "-c", code], cwd=run_dir, env=full_env, check=True, timeout=60)
print("Wheel smoke test passed: package-internal schemas and CLI validation work outside the source tree.")
