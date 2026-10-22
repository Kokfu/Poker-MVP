"""Phase 5 solver performance: a fixed-size run must keep reproducing the
saved fixture. This is a regression guard for future changes, not a
from-scratch equivalence proof; see DEVELOPMENT.md's "Solver performance"
section for the pre-optimization baseline comparison this fixture followed."""
import json
from pathlib import Path

import numpy as np

from solver.benchmark import compare, run_benchmark

FIXTURE = Path(__file__).parent / "solver" / "data" / "benchmark_baseline_fast.json"
CONFIG = dict(spot_count=6, hands_per_opponent=2, profile_warmup=6, profile_sample=3, fixed_hand_count=8)


def test_fixed_size_run_matches_saved_fixture():
    baseline = json.loads(FIXTURE.read_text())
    assert baseline["config"] == CONFIG
    report = run_benchmark(**CONFIG)
    problems = compare(report, baseline, atol=1e-5)
    assert not problems, "\n".join(problems)


def test_benchmark_reports_zero_fallbacks_and_illegal_actions():
    report = run_benchmark(**CONFIG)
    assert all(hand["fallback_count"] == 0 for hand in report["fixed_hands"])
    assert len(report["spots"]) == CONFIG["spot_count"]
    for spot in report["spots"]:
        assert np.isclose(sum(spot["probabilities"]), 1.0, atol=1e-3)
