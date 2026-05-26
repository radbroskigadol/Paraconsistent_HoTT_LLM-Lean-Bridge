"""SecurityPolicy preflight tests.

The preflight is the first of three defenses against `sorry`, `axiom`
declarations, unsafe blocks, and out-of-allowlist imports.  These tests
pin the expected behaviour so a future refactor cannot regress it.
"""
from shadowproof_core.models import DiagnosticSeverity, SecurityLevel
from shadowproof_core.security import SecurityPolicy


def _kinds(diags):
    return {d.kind.value if hasattr(d.kind, "value") else str(d.kind) for d in diags
            if d.severity == DiagnosticSeverity.ERROR}


def test_sorry_blocked_by_default():
    diags = SecurityPolicy().preflight("theorem t : True := by sorry\n")
    assert "security_rejection" in _kinds(diags)


def test_admit_blocked_by_default():
    diags = SecurityPolicy().preflight("theorem t : True := by admit\n")
    assert "security_rejection" in _kinds(diags)


def test_axiom_declarations_blocked():
    diags = SecurityPolicy().preflight("axiom myAxiom : True\n")
    assert "security_rejection" in _kinds(diags)


def test_unsafe_blocked_by_default():
    diags = SecurityPolicy().preflight("unsafe def x := 0\n")
    assert "security_rejection" in _kinds(diags)


def test_eval_directive_blocked_by_default():
    diags = SecurityPolicy().preflight("#eval IO.println \"hi\"\n")
    assert "security_rejection" in _kinds(diags)


def test_import_outside_allowlist_blocked():
    diags = SecurityPolicy(level=SecurityLevel.CONSERVATIVE).preflight(
        "import Untrusted.Module\n\ntheorem t : True := trivial\n"
    )
    assert "security_rejection" in _kinds(diags)


def test_mathlib_import_allowed():
    diags = SecurityPolicy(level=SecurityLevel.CONSERVATIVE).preflight(
        "import Mathlib\n\ntheorem t : True := trivial\n"
    )
    assert "security_rejection" not in _kinds(diags)


def test_sorry_inside_comment_does_not_trigger():
    diags = SecurityPolicy().preflight(
        "-- TODO: replace this sorry placeholder later\ntheorem t : True := trivial\n"
    )
    assert "security_rejection" not in _kinds(diags)


def test_sorry_inside_block_comment_does_not_trigger():
    diags = SecurityPolicy().preflight(
        "/- I plan to sorry this -/\ntheorem t : True := trivial\n"
    )
    assert "security_rejection" not in _kinds(diags)


def test_allow_sorry_opt_in():
    diags = SecurityPolicy(allow_sorry=True).preflight(
        "theorem t : True := by sorry\n"
    )
    # sorry-line rejection should be gone; nothing else here triggers either.
    assert "security_rejection" not in _kinds(diags)
