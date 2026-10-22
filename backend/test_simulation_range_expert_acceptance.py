import json
import pytest

from simulation.range_expert_acceptance import aggregate, matrix, stress, timing


def test_tiny_stress_has_required_zero_correctness_metrics():
    row = stress("random", 8100, 1, 3, 1)
    assert row["matches"] == 1 and row["range_expert_decisions"] > 0
    assert all(row[key] == 0 for key in ("illegal_actions", "fallbacks", "exceptions", "duplicate_equity_calculations", "range_invariant_failures"))


@pytest.mark.parametrize("kwargs", [{"seeds": 0}, {"max_hands": 0}])
def test_stress_rejects_invalid_counts(kwargs):
    values = {"opponent": "random", "base_seed": 1, "seeds": 1, "max_hands": 1, "equity_iterations": 1}; values.update(kwargs)
    with pytest.raises(ValueError): stress(**values)


def test_aggregate_deduplicates_chunk_identity(tmp_path):
    row = stress("tight", 8200, 1, 2, 1)
    for name in ("one.json", "two.json"): (tmp_path / name).write_text(json.dumps(row), encoding="utf-8")
    result = aggregate(str(tmp_path))
    assert result["completed_chunks"] == 1 and result["matches"] == row["matches"]


def test_tiny_matrix_and_timing_are_json_safe():
    report = matrix("random", 1, 8300, 10, 1)
    assert report["diagnostic_only"] and report["sample_warning"] and "delta" in report
    measured = timing("random", 8400, 5, 1)
    assert measured["expert"]["decision_count"] == measured["range_expert"]["decision_count"] == 5
    assert measured["duplicate_equity_calculations"] == 0
