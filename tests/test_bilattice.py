"""Algebraic self-checks on the bilattice L = Bool x Bool.

These mirror the runtime assertions in `bilattice_axiom_report()` and the
Lean witnesses in `lean_project_template/ShadowProof/DemorganSymmetry.lean`,
so a regression in any one of the three layers is caught immediately.
"""
from shadowproof_core.bilattice import (
    BilatticeValue,
    BOTH_L,
    BOTTOM_L,
    L_VALUES,
    NEITHER_L,
    TOP_L,
    aut_L,
    demorgan_order_two_report,
)
from shadowproof_core.shadowhott import bilattice_axiom_report


def test_L_has_exactly_four_values():
    assert len(L_VALUES) == 4
    assert len({v for v in L_VALUES}) == 4


def test_involution_is_order_two():
    for v in L_VALUES:
        assert v.involution().involution() == v


def test_involution_fixed_points_are_both_and_neither():
    fixed = sorted(v.label for v in L_VALUES if v.involution() == v)
    assert fixed == ["both", "neither"]


def test_involution_swaps_top_and_bottom():
    assert TOP_L.involution() == BOTTOM_L
    assert BOTTOM_L.involution() == TOP_L


def test_meet_is_commutative_associative_idempotent():
    for a in L_VALUES:
        assert a.meet(a) == a
        for b in L_VALUES:
            assert a.meet(b) == b.meet(a)
            for c in L_VALUES:
                assert a.meet(b).meet(c) == a.meet(b.meet(c))


def test_top_is_meet_identity():
    for v in L_VALUES:
        assert TOP_L.meet(v) == v
        assert v.meet(TOP_L) == v


def test_designation_is_truth_coordinate():
    for v in L_VALUES:
        assert v.designated is v.truth
        assert isinstance(v.designated, bool)


def test_glutty_is_designated_but_nonreal():
    assert BOTH_L.designated is True
    assert BOTH_L.nonreal is True
    assert BOTH_L.classical is False


def test_neither_is_neither_designated_nor_classical():
    assert NEITHER_L.designated is False
    assert NEITHER_L.classical is False
    assert NEITHER_L.nonreal is True


def test_top_and_bottom_are_classical():
    assert TOP_L.classical is True
    assert BOTTOM_L.classical is True


def test_aut_L_is_Z2():
    table = aut_L()["composition_table"]
    assert table["identity\u2218identity"] == "identity"
    assert table["identity\u2218involution"] == "involution"
    assert table["involution\u2218identity"] == "involution"
    assert table["involution\u2218involution"] == "identity"


def test_demorgan_swap_is_not_designation_preserving():
    rep = demorgan_order_two_report()
    assert rep["designation_preserving"] is False
    assert rep["order_two"] is True
    assert rep["swapped_pair"] == ["top", "bottom"]
    assert sorted(rep["fixed_points"]) == ["both", "neither"]


def test_runtime_axiom_report_passes():
    rep = bilattice_axiom_report()
    assert rep["all_passed"] is True
    assert rep["involution_order_two"] is True
    assert rep["composition_meet_associative"] is True
    assert rep["refl_label_top"] is True
    assert rep["designation_binary"] is True
    assert sorted(rep["involution_fixed_points"]) == ["both", "neither"]


def test_from_label_handles_string_dict_and_value():
    assert BilatticeValue.from_label("top") == TOP_L
    assert BilatticeValue.from_label({"label": "bottom"}) == BOTTOM_L
    assert BilatticeValue.from_label({"truth_coordinate": True, "refutation_coordinate": True}) == BOTH_L
    assert BilatticeValue.from_label(NEITHER_L) is NEITHER_L
