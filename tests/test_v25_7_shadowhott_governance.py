from pathlib import Path

from shadowproof_core.shadowhott import build_shadowhott_state
from shadowproof_core.tool_api import shadowproof_demorgan_symmetry

ROOT = Path(__file__).resolve().parents[1]
LEAN_DIR = ROOT / "lean_project_template" / "ShadowProof"


def _read(name: str) -> str:
    return (LEAN_DIR / name).read_text(encoding="utf-8")


def test_v25_7_lean_governance_files_exist_and_are_imported():
    expected = [
        "BilatticeCore.lean",
        "Routing.lean",
        "PatchMorphism.lean",
        "NoGluttyJ.lean",
    ]
    for name in expected:
        assert (LEAN_DIR / name).exists(), name

    root = (ROOT / "lean_project_template" / "ShadowProof.lean").read_text(encoding="utf-8")
    for module in ["BilatticeCore", "Routing", "PatchMorphism", "NoGluttyJ"]:
        assert f"import ShadowProof.{module}" in root


def test_v25_7_bilattice_core_theorem_surface_is_present():
    text = _read("BilatticeCore.lean")
    for theorem in [
        "demorgan_order_two",
        "demorgan_not_designation_preserving",
        "meet_assoc",
        "meet_comm",
        "meet_idem",
        "join_assoc",
        "join_comm",
        "join_idem",
        "meet_join_absorb",
        "join_meet_absorb",
        "demorgan_meet_dual",
        "demorgan_join_dual",
        "truth_fragile_for_meet",
        "refutation_accumulates_for_meet",
    ]:
        assert f"theorem {theorem}" in text


def test_v25_7_no_glutty_j_theorem_surface_is_present():
    routing = _read("Routing.lean")
    noglutty = _read("NoGluttyJ.lean")
    patch = _read("PatchMorphism.lean")

    for theorem in [
        "no_glutty_j",
        "accepted_ok_both_never_accept",
        "accepted_ok_both_routes_human_review",
        "accept_requires_clean_top",
    ]:
        assert f"theorem {theorem}" in routing

    for theorem in [
        "no_glutty_j_accepted_ok",
        "no_glutty_j_accepted_ok_not_accept",
        "accepted_route_has_clean_top",
        "glutty_always_review_bound",
    ]:
        assert f"theorem {theorem}" in noglutty

    for theorem in [
        "identity_preserves",
        "compose_preserves",
        "changed_fingerprint_not_preserved",
    ]:
        assert f"theorem {theorem}" in patch


def test_v25_7_runtime_no_glutty_j_still_matches_lean_reference():
    payload = {
        "proof_graph": [
            {
                "id": "n1",
                "obstruction": "none",
                "paths": [
                    {"id": "refl_n1", "source": "n1", "target": "n1", "label": "top", "kind": "refl"},
                    {"id": "lean_path", "source": "n1", "target": "out", "label": "top", "kind": "lean_tactic"},
                    {"id": "refutation_path", "source": "n1", "target": "ref", "label": "bottom", "kind": "counterpath"},
                ],
            }
        ],
        "lean_status": "accepted",
        "status": "ok",
        "certificate": {"theorem_name": "t"},
    }
    state = build_shadowhott_state(payload)
    assert state.global_label.label == "both"
    assert state.verdict.value == "human_review"


def test_v25_7_demorgan_report_advertises_governance_formalization_scope():
    report = shadowproof_demorgan_symmetry({"request_id": "v25_7"})
    assert report["status"] == "ok"
    formalizations = report["lean_governance_formalizations"]
    for suffix in [
        "BilatticeCore.lean",
        "Routing.lean",
        "PatchMorphism.lean",
        "NoGluttyJ.lean",
    ]:
        assert any(item.endswith(suffix) for item in formalizations)
    assert "not a full HoTT implementation" in report["formalization_scope"]
