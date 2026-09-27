"""Phase 5 SolverBot: charts, replay, legality, determinism, and privacy."""
import inspect

import numpy as np
import pytest

from simulation.bots import BOT_TYPES
from simulation.duplicate_evaluation import DuplicateConfig, run_duplicate_pairs
from simulation.engine import HandEngine
from solver import bot as solver_bot
from solver.bot import SolverBot, replay_hand
from solver.preflop import CHART_BB, load_charts


def test_charts_load_and_are_valid_distributions():
    charts = load_charts()
    assert charts.depths == tuple(sorted(charts.depths))
    for depth in charts.depths:
        info = charts.metadata["depths"][str(depth)]
        assert info["exploitability_mbb_per_hand"] < 5.0
        for node in charts.trees[depth].nodes:
            if node.kind == "decision":
                strategy = charts.strategy(depth, node.index)
                assert strategy.shape == (len(node.actions), 1326)
                assert np.allclose(strategy.sum(axis=0), 1.0, atol=1e-4)
    assert charts.nearest_depth(100) == 100 and charts.nearest_depth(180) == 200


def test_registered_and_constructible():
    assert isinstance(BOT_TYPES["solver"](seed=1, equity_iterations=10), SolverBot)


class RecordingSolver(SolverBot):
    """Checks every replay against the engine's own view of the hand."""
    def decide_decision(self, observation):
        replay = replay_hand(observation.decision_state)
        assert replay.street == observation.decision_state.street
        return super().decide_decision(observation)


@pytest.mark.parametrize("opponent", ["random", "aggressive", "tight", "equity", "expert"])
def test_plays_legally_without_fallbacks(opponent):
    config = DuplicateConfig(pairs=6, equity_iterations=50)
    pairs = run_duplicate_pairs(config, "solver", opponent)
    assert sum(pair.illegal_actions for pair in pairs) == 0
    assert sum(pair.fallback_actions for pair in pairs) == 0
    assert all(pair.deal_verified for pair in pairs)


def test_replay_matches_engine_and_no_strategy_fallbacks():
    bots = []
    for seed in range(8):
        solver = RecordingSolver(seed=seed)
        bots.append(solver)
        engine = HandEngine(solver, BOT_TYPES["aggressive"](seed=seed), starting_stacks={"a": 10_000, "b": 10_000}, bb=100, seed=900 + seed, button="a" if seed % 2 else "b")
        result = engine.play()
        assert result["illegal_actions"] == 0
    assert sum(b.fallback_count for b in bots) == 0
    assert sum(b.decision_count for b in bots) > 0


def test_deterministic_for_equal_seeds():
    config = DuplicateConfig(pairs=4, equity_iterations=50)
    assert run_duplicate_pairs(config, "solver", "equity") == run_duplicate_pairs(config, "solver", "equity")


def test_uses_only_decision_state():
    source = inspect.getsource(solver_bot)
    for forbidden in ("engine.holes", ".deck", "self.engine", "history.events", "bot_hole_cards"):
        assert forbidden not in source
    assert SolverBot.uses_range_equity is False


def test_short_stacks_and_deep_stacks_stay_legal():
    for stack in (1_200, 3_000, 20_000):
        solver = SolverBot(seed=stack)
        engine = HandEngine(solver, BOT_TYPES["aggressive"](seed=3), starting_stacks={"a": stack, "b": stack}, bb=100, seed=stack, button="a")
        assert engine.play()["illegal_actions"] == 0
        assert solver.fallback_count == 0


def test_explanation_reports_strategy():
    solver = SolverBot(seed=4)
    HandEngine(solver, BOT_TYPES["tight"](seed=4), starting_stacks={"a": 10_000, "b": 10_000}, bb=100, seed=77, button="a").play()
    explanation = solver.last_explanation
    assert explanation["source"] in {"preflop_chart", "postflop_solve"}
    assert sum(explanation["probabilities"]) == pytest.approx(1.0, abs=1e-3)
    assert explanation["chosen"] in explanation["labels"]
