"""Unopened small-blind strength and production Coach regression controls."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from coach.service import Spot, SpotAction, advise
from simulation.opponent_model import OpponentModel, StatEstimate
from solver.bot import AdaptiveSolverBot
from solver.exploit import tree_locks
from solver.preflop import load_charts
from test_solver_exploit import profile


DEPTHS = (15, 30, 60, 100, 200)
CORRELATIONS = (
    ({"aggressive": 0.89, "call": 0.19}, 0.89, 0.54),
    ({"aggressive": 0.20, "call": 0.80}, 0.20, 0.50),
)


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("correlation,opening_strength,response_strength", CORRELATIONS)
def test_opening_and_response_coefficients(depth, correlation, opening_strength, response_strength):
    tree = load_charts().trees[depth]
    root = tree.nodes[tree.root]
    after_limp = root.children[root.labels.index("call")]
    locks_by_seat = [tree_locks(tree, seat, "preflop", profile(), correlation) for seat in (0, 1)]

    # Only these two decisions precede any voluntary raise. All other decisions
    # in the chart follow a raise or shove.
    opening_nodes = {root.index, after_limp}
    for seat, locks in enumerate(locks_by_seat):
        decisions = {node.index for node in tree.nodes if node.kind == "decision" and node.player == seat}
        assert locks.keys() == decisions
        for index, (weight, groups, strength) in locks.items():
            expected = opening_strength if index in opening_nodes else response_strength
            assert strength == pytest.approx(expected, abs=1e-12, rel=0)
            assert weight == 0.75
            assert sum(mass for _, mass in groups) == pytest.approx(1, abs=1e-12, rel=0)
        assert tree_locks(tree, seat, "preflop", profile("very_low"), correlation) == {}


@pytest.mark.parametrize("depth", DEPTHS)
def test_unlocked_chart_policy_is_served_verbatim(depth):
    bot = AdaptiveSolverBot(seed=917)
    tree = bot.charts.trees[depth]
    for opponent in (0, 1):
        policy = bot._preflop_policy(depth, opponent, {})
        for node in tree.nodes:
            if node.kind == "decision":
                probabilities = policy(node.index)
                np.testing.assert_array_equal(probabilities, bot.charts.strategy(depth, node.index))
                assert np.isfinite(probabilities).all() and (probabilities >= 0).all()
                np.testing.assert_allclose(probabilities.sum(axis=0), 1, atol=1e-6, rtol=0)


@pytest.mark.parametrize("depth", DEPTHS)
def test_coach_preflop_advice_is_legal_normalized_and_reproducible(depth, monkeypatch):
    correlation = {"aggressive": 0.89, "call": 0.19}
    reads = profile()
    snapshot = OpponentModel("b").snapshot()
    statistics = {
        name: StatEstimate(80, round(80 * read.smoothed_frequency), read.smoothed_frequency,
                           read.smoothed_frequency, read.confidence)
        for name, read in reads.statistics.items()
    }
    reads = replace(snapshot, hands_observed=reads.hands_observed, classification=reads.classification,
                    statistics={**snapshot.statistics, **statistics})
    model = SimpleNamespace(hands_observed=reads.hands_observed, snapshot=lambda: reads)
    monkeypatch.setattr("coach.service.profile_for", lambda *args: model)
    monkeypatch.setattr(AdaptiveSolverBot, "_strength_correlation", lambda self: correlation)
    button = Spot(hero_cards=["Jc", "9d"], hero_stack=100 * depth, villain_stack=100 * depth)
    big_blind = replace(button, hero_position="big_blind", actions=[SpotAction("villain", "raise", 250)])
    for spot in (button, big_blind):
        for exploit in (False, True):
            first, repeat = (advise(spot, opponent="fixture", exploit=exploit, seed=917) for _ in range(2))
            assert first["status"] == "hero_to_act"
            assert first["explanation"]["source"] == ("preflop_exploit" if exploit else "preflop_chart")
            assert first["explanation"]["depth_bb"] == depth
            assert first["advice"] == repeat["advice"]
            probabilities = first["explanation"]["probabilities"]
            assert probabilities == repeat["explanation"]["probabilities"]
            assert all(0 <= p <= 1 for p in probabilities)
            assert sum(probabilities) == pytest.approx(1, abs=0.0003, rel=0)
            advice, state = first["advice"], first["state"]
            assert advice["action"] in state["legal_actions"]
            if advice["action"] == "raise":
                assert state["minimum_target"] <= advice["amount"] <= state["maximum_target"]
