"""Stage 0 oracle: the two-street solver must reduce to the production one-street solver when rivers allow no betting."""
import numpy as np
import pytest

from research.solver_oracle import TurnSpot, TwoStageSolver, analyse_spot
from solver.cfr import RangeSolver
from solver.combos import COMBO_COUNT, card_mask
from solver.tree import SizeMenu, StreetState

BOARD = ("7h", "8d", "2c", "Js")
NO_RIVER_BETTING = SizeMenu(by_depth=(), allow_all_in=False)


def narrow_ranges(seed: int, size: int = 45):
    rng = np.random.default_rng(seed)
    live = np.where(~card_mask(BOARD))[0]
    ranges = []
    for _ in range(2):
        weights = np.zeros(COMBO_COUNT)
        weights[rng.choice(live, size=size, replace=False)] = rng.uniform(0.3, 1.0, size)
        ranges.append(weights)
    return tuple(ranges)


def spot(stack: int = 9000, seed: int = 1) -> TurnSpot:
    return TurnSpot(BOARD, StreetState("turn", 1, (0, 0), (stack, stack), (1000, 1000), 100), narrow_ranges(seed))


def test_without_river_betting_the_leaf_values_equal_the_one_street_leaf_values():
    two_stage = TwoStageSolver(spot(), river_menu=NO_RIVER_BETTING, fresh=True)
    one_street = RangeSolver(two_stage.tree, two_stage.ranges, two_stage.turn_d, two_stage.turn_compat, combo_ids=two_stage.combos)
    assert two_stage.river_leaves  # the check-down leaves really are routed through river subgames
    strategies = two_stage.policy(two_stage.current)
    for traverser in (0, 1):
        own, opp = two_stage._reaches(traverser, lambda node: strategies[node.index])
        two_stage._refresh_rivers(*((own, opp) if traverser == 0 else (opp, own)))
        actual, expected = two_stage._terminal_values(traverser, opp), one_street._terminal_values(traverser, opp)
        assert np.allclose(actual, expected, rtol=1e-4, atol=1e-2 * 1e-2)
        assert np.abs(actual[[leaf.index for leaf in two_stage.river_leaves]]).max() > 100  # not trivially zero


def test_without_river_betting_both_solvers_reach_the_same_low_exploitability():
    # Exact policy equality is the wrong test: regret matching amplifies float noise near ties.
    two_stage = TwoStageSolver(spot(), river_menu=NO_RIVER_BETTING, fresh=True)
    one_street = RangeSolver(two_stage.tree, two_stage.ranges, two_stage.turn_d, two_stage.turn_compat, combo_ids=two_stage.combos)
    for _ in range(60):
        two_stage.iterate()
        one_street.iterate()
    actual, expected = two_stage.final_policy(), one_street.final_policy()
    two_stage.solve_rivers_for(actual, 1)
    gap_two_stage = two_stage.profile_exploitability(actual)
    gap_one_street = one_street.exploitability(lambda node: expected[node.index])
    assert gap_two_stage / two_stage.pot < 0.03 and gap_one_street / two_stage.pot < 0.03
    assert abs(gap_two_stage - gap_one_street) / two_stage.pot < 0.02
    # The profile evaluator agrees with the one-street evaluator when evaluating the same strategies.
    two_stage.solve_rivers_for(expected, 1)
    assert two_stage.profile_exploitability(expected) == pytest.approx(gap_one_street, abs=1e-3 * two_stage.pot)


def test_all_in_leaves_are_not_given_a_river_game():
    short = TwoStageSolver(spot(stack=150), river_menu=NO_RIVER_BETTING)
    deep = TwoStageSolver(spot(), river_menu=NO_RIVER_BETTING)
    assert len(short.river_leaves) < len(deep.river_leaves)
    assert all(0 not in leaf.state.stack for leaf in short.river_leaves)


def test_river_betting_oracle_converges_and_has_nonnegative_gap():
    solver = TwoStageSolver(spot(seed=3))
    for _ in range(4):
        solver.iterate()
    early = solver.profile_exploitability(solver.final_policy())
    for _ in range(36):
        solver.iterate()
    policy = solver.final_policy()
    late = solver.profile_exploitability(policy)
    assert early > 0 and -1e-6 <= late < early
    assert late / solver.pot < 0.05  # within a few percent of the pot after 40 iterations on a small range


def test_analyse_spot_reports_comparable_gaps():
    result = analyse_spot(spot(seed=5), oracle_iterations=30, production_iterations=30, river_iterations=30)
    assert result["river_subgames"] > 0 and result["production_gap"] >= -1e-6 and result["oracle_gap"] >= -1e-6
    assert result["root_labels"] and abs(sum(result["root_mix_oracle"]) - 1.0) < 1e-6
    assert 0.0 <= result["root_strategy_distance"] <= 1.0
