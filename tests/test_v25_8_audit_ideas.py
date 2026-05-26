from pathlib import Path

from shadowproof_core.eval_harness import run_eval_suite
from shadowproof_core.observability import make_proof_lifecycle_trace, metric_event_from_lifecycle
from shadowproof_core.config import ShadowProofConfig
from shadowproof_core.retrieval import index_mathlib_sources, candidates_from_index


def test_v25_8_eval_metrics_track_human_review_escalation():
    def caller(tool, payload):
        assert tool == "shadowproof_shadowhott_state"
        return {
            "request_id": "case_hr",
            "tool": tool,
            "status": "human_review",
            "lean_status": "accepted",
            "shadowhott_state": {
                "verdict": "human_review",
                "global_valuation": {"truth": True, "refutation": True, "designated": True, "label": "both"},
            },
            "diagnostics": [],
        }

    suite = {
        "suite_id": "v25_8_hr",
        "cases": [
            {
                "case_id": "glutty",
                "kind": "no_glutty_j_trap",
                "tool": "shadowproof_shadowhott_state",
                "input": {"request_id": "case_hr"},
                "expect_status": "human_review",
                "expect_lean_status": "accepted",
                "expect_human_review": True,
            }
        ],
    }
    result = run_eval_suite(suite, caller)
    metrics = result["metrics"]
    assert metrics["human_review_count"] == 1
    assert metrics["expected_human_review_count"] == 1
    assert metrics["human_review_escalation_accuracy"] == 1.0
    assert metrics["missed_human_review_escalation_count"] == 0


def test_v25_8_proof_lifecycle_trace_exposes_bilattice_and_escalation():
    lifecycle = make_proof_lifecycle_trace(
        {"request_id": "trace_1"},
        {
            "request_id": "trace_1",
            "tool": "shadowproof_validate_draft",
            "status": "human_review",
            "lean_status": "accepted",
            "shadowhott_state": {"global_valuation": {"truth": True, "refutation": True, "designated": True, "label": "both"}},
        },
    )
    assert lifecycle["human_review_required"] is True
    assert lifecycle["bilattice"]["truth"] is True
    assert lifecycle["bilattice"]["refutation"] is True
    event = metric_event_from_lifecycle(ShadowProofConfig(), lifecycle, elapsed_ms=7)
    assert event.event_type == "proof_lifecycle"
    assert event.human_review_required is True
    assert event.bilattice_truth is True
    assert event.bilattice_refutation is True


def test_v25_8_index_mathlib_writes_dependency_and_lsh_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWPROOF_ALLOWED_FILE_ROOTS", str(tmp_path))
    src = tmp_path / "src"
    src.mkdir()
    lean = src / "Algebra.lean"
    lean.write_text(
        "import Mathlib.Algebra.Group.Basic\n\n"
        "theorem Foo.bar (G : Type) [Group G] (a : G) : a = a := by rfl\n"
        "lemma Foo.baz (G : Type) [Group G] (a : G) : a = a := by exact Foo.bar G a\n",
        encoding="utf-8",
    )
    out = tmp_path / "index.jsonl"
    result = index_mathlib_sources({
        "source_dirs": [str(src)],
        "output_path": str(out),
        "build_dependency_graph": True,
        "lsh_bucket_bits": 12,
    })
    assert result["status"] == "ok"
    assert result["declaration_count"] == 2
    assert result["dependency_edge_count"] >= 1
    text = out.read_text(encoding="utf-8")
    assert '"lsh_bucket"' in text
    assert '"structure_hash"' in text
    assert '"dependencies"' in text
    cands = candidates_from_index("Group Foo bar", out)
    assert cands
    assert cands[0].lsh_bucket
    assert cands[0].structure_hash
