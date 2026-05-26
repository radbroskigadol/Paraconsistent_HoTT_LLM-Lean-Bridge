"""ShadowHoTT verdict assignment regression tests.

The core safety property is: a request that has Lean acceptance plus any
hard refutation signal (drift, sorry leak, axiom leak, or path-level
refutation) must NOT receive an `accept` verdict.  We exercise the three
main verdict transitions.
"""
from shadowproof_core.bilattice import BOTH_L, BOTTOM_L, NEITHER_L, TOP_L
from shadowproof_core.shadowhott import audit_shadowhott_state, build_shadowhott_state


def _refl_node_only_top():
    return {
        "id": "n1",
        "obstruction": "none",
        "paths": [
            {"id": "refl_n1", "source": "n1", "target": "n1", "label": "top", "kind": "refl"},
            {"id": "tac_n1", "source": "n1", "target": "out", "label": "top", "kind": "lean_tactic"},
        ],
    }


def _refl_node_with_refutation():
    return {
        "id": "n1",
        "obstruction": "none",
        "paths": [
            {"id": "refl_n1", "source": "n1", "target": "n1", "label": "top", "kind": "refl"},
            {"id": "tac_n1", "source": "n1", "target": "out", "label": "top", "kind": "lean_tactic"},
            {"id": "ctr_n1", "source": "n1", "target": "ref", "label": "bottom", "kind": "counterpath"},
        ],
    }


def test_clean_lean_acceptance_produces_top_and_accept():
    state = build_shadowhott_state({
        "proof_graph": [_refl_node_only_top()],
        "lean_status": "accepted",
        "status": "ok",
        "certificate": {"theorem_name": "t"},
    })
    assert state.global_label == TOP_L
    assert state.verdict.value == "accept"


def test_lean_acceptance_plus_refutation_routes_to_human_review():
    state = build_shadowhott_state({
        "proof_graph": [_refl_node_with_refutation()],
        "lean_status": "accepted",
        "status": "ok",
        "certificate": {"theorem_name": "t"},
    })
    # The refutation path is present even though Lean accepted: this is the
    # glutty case that MUST NOT auto-accept.
    assert state.global_label == BOTH_L
    assert state.verdict.value == "human_review"


def test_sorry_in_code_blocks_acceptance_even_if_lean_says_ok():
    state = build_shadowhott_state({
        "proof_graph": [_refl_node_only_top()],
        "lean_status": "accepted",
        "status": "ok",
        "final_lean_code": "theorem t : True := by sorry\n",
        "theorem_fingerprint": {
            "theorem_family": "demo",
            "conclusion": "True",
            "forbidden_drift": ["sorry"],
        },
        "certificate": {"theorem_name": "t"},
    })
    # `sorry` is a hard refutation signal: glutty + human_review, NOT accept.
    assert state.global_label == BOTH_L
    assert state.verdict.value == "human_review"


def test_lean_rejection_with_blocking_unpatchable_drift_rejects():
    state = build_shadowhott_state({
        "proof_graph": [_refl_node_only_top()],
        "lean_status": "rejected",
        "status": "needs_repair",
        "diagnostics": [{"severity": "error", "kind": "theorem_drift",
                         "message": "drift", "source": "test"}],
    })
    assert state.global_label == BOTTOM_L
    assert state.verdict.value == "reject"


def test_lean_unavailable_with_no_drift_is_unchecked():
    state = build_shadowhott_state({
        "proof_graph": [_refl_node_only_top()],
        "lean_status": "not_available",
        "status": "unchecked",
        "diagnostics": [{"severity": "error", "kind": "lean_not_available",
                         "message": "lake missing", "source": "lean_runner"}],
    })
    assert state.global_label == NEITHER_L
    assert state.verdict.value == "unchecked"


def test_audit_catches_inconsistent_accept_verdict():
    # Manually construct a payload where labels would yield BOTH_L; the
    # audit should refuse to produce an `accept` verdict for it.  We rely
    # on `audit_shadowhott_state` to flag any inconsistency.
    result = audit_shadowhott_state({
        "proof_graph": [_refl_node_with_refutation()],
        "lean_status": "accepted",
        "status": "ok",
        "certificate": {"theorem_name": "t"},
    })
    assert result["status"] == "ok"
    state = result["shadowhott_state"]
    assert state["verdict"] == "human_review"
    assert state["global_label"]["label"] == "both"
