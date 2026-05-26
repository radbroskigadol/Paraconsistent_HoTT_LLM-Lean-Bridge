"""Sandbox diagnostic-classifier tests.

The pre-fix code matched the bare substring `"goals"` as evidence of an
unsolved goal, which falsely flagged the benign "no goals" and "goals
accomplished" outputs.  These tests pin the corrected classification.
"""
from shadowproof_core.sandbox import parse_basic_lean_diagnostics


def test_unsolved_goals_classified_correctly():
    diags = parse_basic_lean_diagnostics("error: unsolved goals\n  a : Nat\n  ⊢ a = a\n")
    assert any(d["kind"] == "unsolved_goal" for d in diags)


def test_no_goals_is_not_classified_as_unsolved_goal():
    # "no goals" appears in successful tactic output; must NOT misroute.
    diags = parse_basic_lean_diagnostics("info: no goals\n")
    assert not any(d["kind"] == "unsolved_goal" for d in diags)


def test_goals_accomplished_is_not_classified_as_unsolved_goal():
    diags = parse_basic_lean_diagnostics("goals accomplished\n")
    assert not any(d["kind"] == "unsolved_goal" for d in diags)


def test_substring_goals_alone_is_not_classified_as_unsolved_goal():
    # e.g. "subgoals", a substring that the pre-fix `"goals" in low` check
    # would have falsely matched.
    diags = parse_basic_lean_diagnostics("info: showing subgoals\n")
    assert not any(d["kind"] == "unsolved_goal" for d in diags)


def test_unknown_identifier_still_classified():
    diags = parse_basic_lean_diagnostics("error: unknown identifier 'foo'\n")
    assert any(d["kind"] == "unknown_identifier" for d in diags)


def test_type_mismatch_still_classified():
    diags = parse_basic_lean_diagnostics("error: type mismatch\n  have type X but expected Y\n")
    assert any(d["kind"] == "type_mismatch" for d in diags)


def test_failed_to_synthesize_still_classified():
    diags = parse_basic_lean_diagnostics("error: failed to synthesize instance\n")
    assert any(d["kind"] == "missing_typeclass_instance" for d in diags)
