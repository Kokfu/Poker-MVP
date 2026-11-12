"""Deviation-gated locking (proposal A): off-by-default equivalence, gate unit tests, instrumentation."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from simulation.bots import BOT_TYPES
from simulation.slumbot import SlumbotClient, run_slumbot_session
from solver.bot import AdaptiveSolverBot, GatedAdaptiveSolverBot, SolverBot
from solver.cfr import RangeSolver
from solver.exploit import (GATE_LEVEL, GATE_MARGIN, GATE_SCALE, beta_cdf, beta_interval, gate_decision, gate_locks,
                            node_aggregates, node_lock, tree_locks)
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree

GOLDEN = Path(__file__).parent / "test_data" / "equiv_learning_main_fa3b538.json"


def est(n, k, smoothed):
    return SimpleNamespace(opportunities=n, occurrences=k, smoothed_frequency=smoothed, confidence="high")


# ------------------------------------------------------------ equivalence
def test_default_bots_are_not_gated():
    assert AdaptiveSolverBot.gated_locks is False and SolverBot.gated_locks is False
    assert AdaptiveSolverBot(seed=1).gated_locks is False
    assert AdaptiveSolverBot(seed=1, gated_locks=True).gated_locks is True
    assert BOT_TYPES["solver_adaptive_gated"](seed=1).gated_locks is True
    assert isinstance(BOT_TYPES["solver_adaptive_gated"](seed=1), GatedAdaptiveSolverBot)
    assert BOT_TYPES["solver_adaptive"](seed=1).gated_locks is False


def test_off_learning_session_is_bit_identical_to_main():
    """40-hand deterministic learning session (fake referee): every probability vector at full
    float precision, every action, every hand result equals the golden file recorded from
    ``main`` (fa3b538) before any gate code existed."""
    from equiv_learning import fingerprint
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(fingerprint(expected["hands"])))
    assert actual["decisions"] == expected["decisions"] and actual["decisions"] > 80
    assert actual["probabilities"] == expected["probabilities"]
    assert actual["actions"] == expected["actions"]
    assert actual["winnings"] == expected["winnings"]
    assert actual == expected
    sources = {source for source, _ in expected["locked_nodes"]}
    assert "preflop_exploit" in sources and "postflop_solve" in sources  # locks were exercised


# ------------------------------------------------------------------- math
def test_beta_helpers():
    assert beta_cdf(0.5, 2, 2) == pytest.approx(0.5)
    assert beta_cdf(0.25, 1, 1) == pytest.approx(0.25)
    assert beta_cdf(0.3, 3, 7) == pytest.approx(0.5372, abs=1e-3)  # = P(Binomial(9, 0.3) >= 3)
    low, high = beta_interval(0, 0)
    assert (low, high) == (pytest.approx(0.05, abs=1e-6), pytest.approx(0.95, abs=1e-6))
    low, high = beta_interval(80, 100)
    assert 0.72 < low < 0.74 and 0.85 < high < 0.87
    assert beta_cdf(low, 81, 21) == pytest.approx(0.05, abs=1e-6) and beta_cdf(high, 81, 21) == pytest.approx(0.95, abs=1e-6)
    assert (GATE_LEVEL, GATE_MARGIN, GATE_SCALE) == (0.90, 0.08, 0.10)


# ------------------------------------------------------------------- gate
AGG = np.array([0.5, 0.3, 0.2])


def test_read_equal_to_equilibrium_gives_no_lock():
    assert gate_decision([((0,), est(500, 250, 0.5))], AGG) == 0.0


def test_clearly_deviating_read_locks_at_full_weight():
    assert gate_decision([((0,), est(100, 80, 0.79))], AGG) == 1.0


def test_distance_scales_the_weight():
    low, _ = beta_interval(80, 100)
    unlocked = low - 0.05
    factor = gate_decision([((0,), est(100, 80, 0.79))], np.array([unlocked, 1 - unlocked]))
    assert factor == pytest.approx(0.5, abs=1e-6)


def test_margin_edge_blocks_a_small_but_significant_difference():
    # 0.07 away with a tight interval (n=1000): significant, but under the 0.08 margin.
    assert gate_decision([((0,), est(1000, 570, 0.57))], np.array([0.50, 0.50])) == 0.0
    assert gate_decision([((0,), est(1000, 590, 0.59))], np.array([0.50, 0.50])) > 0.0


def test_interval_edge_blocks_a_large_but_uncertain_difference():
    # 0.15 away but only 10 observations: the 90% interval still contains the unlocked value.
    low, high = beta_interval(8, 10)
    assert low < 0.60 < high
    assert gate_decision([((0,), est(10, 8, 0.75))], np.array([0.60, 0.40])) == 0.0


def test_groups_use_summed_unlocked_frequency_and_best_group_wins():
    reads = [((0, 1), est(200, 40, 0.2)), ((2,), est(200, 100, 0.5))]
    # group (0, 1) unlocked 0.8 vs read 0.2: far outside the interval -> weight 1
    assert gate_decision(reads, AGG) == 1.0
    assert gate_decision([((0,), None)], AGG) == 0.0
    assert gate_decision([((0,), est(0, 0, 0.9))], AGG) == 0.0  # no opportunities, no evidence


def test_gate_locks_scales_and_drops():
    locks = {1: (0.75, "g1", 1.0), 2: (0.55, "g2", 0.5), 3: (0.3, "g3", 1.0)}
    reads = {1: [((0,), est(100, 80, 0.79))], 2: [((0,), est(500, 250, 0.5))], 3: [((0,), est(100, 80, 0.79))]}
    aggregates = {1: np.array([0.5, 0.5]), 2: np.array([0.5, 0.5]), 3: np.array([0.5, 0.5])}
    gated = gate_locks(locks, reads, aggregates)
    assert set(gated) == {1, 3}
    assert gated[1] == (0.75, "g1", 1.0) and gated[3] == (0.3, "g3", 1.0)  # distance >= 0.10: weight unchanged
    assert gate_locks({4: (0.75, "g", 1.0)}, {4: reads[1]}, {}) == {}  # no unlocked aggregate: no lock


def test_node_reads_do_not_change_the_lock_and_aggregates_sum_to_one():
    tree = StreetTree(StreetState("flop", 1, (0, 0), (9_000, 9_000), (500, 500), 100), POSTFLOP_MENU)
    stats = {name: SimpleNamespace(opportunities=60, occurrences=30, smoothed_frequency=0.5, confidence="high", raw_frequency=0.5)
             for name in ("fold_to_bet", "call_vs_bet", "raise_vs_bet", "bet")}
    profile = SimpleNamespace(statistics={}, street_statistics={"flop": stats}, hands_observed=60, classification="x")
    plain = tree_locks(tree, 0, "flop", profile)
    reads = {}
    with_reads = tree_locks(tree, 0, "flop", profile, reads_out=reads)
    assert plain == with_reads and set(reads) == set(plain) and plain
    rng = np.random.default_rng(0)
    n = 6
    d = rng.uniform(-1, 1, (n, n))
    compat = np.ones((n, n))
    solver = RangeSolver(tree, (np.ones(n), np.ones(n)), d, compat)
    average = solver.solve(20).average
    aggregates = node_aggregates(tree, 0, np.ones(n), average)
    assert aggregates and all(v.sum() == pytest.approx(1.0) for v in aggregates.values())
    assert all(tree.nodes[i].player == 0 for i in aggregates)


# ------------------------------------------------------------- end to end
def _session(bot_class, hands):
    from test_simulation_slumbot import FakeSlumbot
    bots = []

    def factory(index):
        bot = bot_class(seed=0, equity_iterations=50)
        bots.append(bot)
        return bot

    results, summary = run_slumbot_session(factory, hands, SlumbotClient(FakeSlumbot(seed=5), token="tok"), learn=True)
    assert summary["desyncs"] == 0 and summary["settlement_mismatches"] == 0
    return bots[0]


def test_instrumentation_fields_present_and_gated_never_adds_locks():
    base, gated = _session(AdaptiveSolverBot, 30), _session(GatedAdaptiveSolverBot, 30)
    keys = {"street", "gated", "candidate_locks", "locks_applied", "cache_hit", "unlocked_action_differs"}
    for bot, flag in ((base, False), (gated, True)):
        traced = [t for t in bot.decision_trace if t["source"] != "fallback"]
        assert traced
        for entry in traced:
            info = entry["instrumentation"]
            assert set(info) == keys and info["gated"] is flag
            assert info["street"] == entry["street"]
            assert 0 <= info["locks_applied"] <= info["candidate_locks"]
            assert info["unlocked_action_differs"] in (None, True, False)
        assert any(t["instrumentation"]["candidate_locks"] > 0 for t in traced)
    # Base and gated see the same candidates on the first decision that has any; the gate only removes.
    assert sum(t["instrumentation"]["locks_applied"] for t in gated.decision_trace if "instrumentation" in t) <= \
        sum(t["instrumentation"]["candidate_locks"] for t in gated.decision_trace if "instrumentation" in t)
    assert any(t["instrumentation"]["unlocked_action_differs"] is not None for t in gated.decision_trace if "instrumentation" in t)
    assert any(t["instrumentation"]["cache_hit"] is not None for t in base.decision_trace if "instrumentation" in t)
