"""Phase 5 solver performance: a fixed-size run must keep reproducing the
saved fixture. This is a regression guard for future changes, not a
from-scratch equivalence proof; see DEVELOPMENT.md's "Solver performance"
section for the pre-optimization baseline comparison this fixture followed."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from solver.benchmark import compare

BACKEND = Path(__file__).parent
FIXTURE = BACKEND / "solver" / "data" / "benchmark_baseline_fast_single_thread.json"
CONFIG = dict(spot_count=6, hands_per_opponent=2, profile_warmup=6, profile_sample=3, fixed_hand_count=8)


@pytest.fixture(scope="module")
def solver_benchmark_report(tmp_path_factory):
    output = tmp_path_factory.mktemp("solver-benchmark") / "report.json"
    # Seed 9300006 samples a different action under the legacy BLAS layout.
    # Start NumPy with the same thread count as the comparison fixture.
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    subprocess.run(
        [
            sys.executable, "-m", "solver.benchmark",
            "--spots", str(CONFIG["spot_count"]),
            "--hands-per-opponent", str(CONFIG["hands_per_opponent"]),
            "--profile-warmup", str(CONFIG["profile_warmup"]),
            "--profile-sample", str(CONFIG["profile_sample"]),
            "--fixed-hands", str(CONFIG["fixed_hand_count"]),
            "--save", str(output),
            "--quiet",
        ],
        cwd=BACKEND, env=env, check=True, timeout=600,
    )
    return json.loads(output.read_text(encoding="utf-8"))


@pytest.mark.slow
def test_fixed_size_run_matches_saved_fixture(solver_benchmark_report):
    baseline = json.loads(FIXTURE.read_text())
    assert solver_benchmark_report["config"] == baseline["config"] == CONFIG
    problems = compare(solver_benchmark_report, baseline, atol=1e-5)
    assert not problems, "\n".join(problems)


@pytest.mark.slow
def test_benchmark_reports_zero_fallbacks_and_illegal_actions(solver_benchmark_report):
    report = solver_benchmark_report
    assert all(hand["fallback_count"] == 0 for hand in report["fixed_hands"])
    assert len(report["spots"]) == CONFIG["spot_count"]
    for spot in report["spots"]:
        assert np.isclose(sum(spot["probabilities"]), 1.0, atol=1e-3)


def test_compare_matches_repeated_spots_of_one_hand_and_street_by_occurrence():
    """A hand and street can hold an initial solve and a re-solve; each must be compared with its own counterpart."""
    def spot(chosen, probabilities):
        return {"hand_seed": 1, "hand_number": 2, "street": "river", "chosen": chosen, "probabilities": probabilities}

    first, second = spot("fold", [0.2, 0.3, 0.5]), spot("raise_1250", [0.1, 0.2, 0.3, 0.4])
    report = {"spots": [first, second], "fixed_hands": []}
    assert compare(report, {"spots": [first, second], "fixed_hands": []}) == []
    swapped = compare(report, {"spots": [second, first], "fixed_hands": []})
    assert len(swapped) == 4 and any("fold" in problem for problem in swapped)


def test_compare_requires_same_spots_and_fixed_hands():
    baseline = {"spots": [{"hand_seed": 1, "hand_number": 1, "street": "flop"}],
                "fixed_hands": [{"seed": 10}]}
    report = {"spots": [{"hand_seed": 2, "hand_number": 1, "street": "flop"}],
              "fixed_hands": [{"seed": 20}]}

    assert compare(report, baseline) == [
        "spot (1, 1, 'flop', 1): missing from report",
        "spot (2, 1, 'flop', 1): unexpected in report",
        "hand seed=10: missing from report",
        "hand seed=20: unexpected in report",
    ]
