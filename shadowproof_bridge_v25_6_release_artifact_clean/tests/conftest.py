"""Pytest configuration for the ShadowProof Bridge test suite.

These tests are designed to run with no third-party dependencies beyond
pytest itself.  They exercise:

  - the bilattice algebra and its self-check report
  - the verdict assignment policy
  - the security boundaries against the regressions we shipped fixes for
    in this release (config-override RCE, retention-sweep abuse, tenant
    impersonation, tenant_dir path traversal, sandbox 'goals' false
    positive)
"""
import os
import pathlib
import sys

# Ensure the package is importable when running `python -m pytest` from the
# project root without an editable install.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Clean the test environment of any caller-supplied SHADOWPROOF_* variables
# so tests are deterministic.
for k in list(os.environ):
    if k.startswith("SHADOWPROOF_"):
        del os.environ[k]
