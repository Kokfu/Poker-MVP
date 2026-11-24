from fractions import Fraction
from math import fsum

import numpy as np
import pytest

from research.holdem.river_bayes_reference import facing_actions, opening_actions, posterior
from research.holdem.river_bet_range import bet_update
from research.holdem.river_ev import ExactRiverEV


HERO = ("9s", "3c")
BOARD = ("As", "Ks", "Qs", "Js", "2d")


def test_reference_counts_unordered_combos_and_removes_hero_and_board():
    # Of 990 legal holdings, exactly 44 contain Ts. Their bet frequency
    # is 1/2, vs 1/4 for the other 946. Both groups use unit prior per combo.
    result = posterior(HERO, BOARD, lambda _: 1, lambda pair: .5 if "Ts" in pair else .25)
    assert len(result) == 990
    assert len({frozenset(pair) for pair in result}) == 990
    assert all(set(pair).isdisjoint((*HERO, *BOARD)) for pair in result)
    assert fsum(prob for pair, prob in result.items() if "Ts" in pair) == pytest.approx(44 * 2 / 1034)
    assert fsum(result.values()) == pytest.approx(1)
    exact = ExactRiverEV(HERO, BOARD, lambda pair, _: result[pair])
    # On this four-spade board Hero has a flush: all non-Ts holdings lose,
    # except higher spade kickers are impossible (A/K/Q/J are on board).
    assert exact.equity == pytest.approx(946 / 1034)


@pytest.mark.parametrize(("action", "first", "second", "expected"), [
    (("check", None), .5, .75, Fraction(2, 3)),
    (("bet", 50), .25, .10, Fraction(15, 17)),
    (("all_in", 75), .25, .15, Fraction(5, 6)),
    (("fold", None), .75, .50, Fraction(9, 11)),
])
def test_reference_weighted_manual_action_updates(action, first, second, expected):
    # Two compatible combos with different priors; a blocked combo's large
    # prior must never even be read by the likelihood function.
    combos = (frozenset(("Ts", "4c")), frozenset(("4s", "5c")))
    prior = {combos[0]: 3, combos[1]: 1, frozenset(("As", "4c")): 100}
    chances = {combos[0]: {action: first}, combos[1]: {action: second}}
    result = posterior(HERO, BOARD, lambda pair: prior.get(frozenset(pair), 0),
                       lambda pair: chances.get(frozenset(pair), {}).get(action, 0))
    assert next(prob for pair, prob in result.items() if frozenset(pair) == combos[0]) == pytest.approx(float(expected))
    assert sum(prob > 0 for prob in result.values()) == 2


def test_reference_merges_censored_wagers_and_treats_all_in_calls_as_passive():
    # With high card at 75 behind, .80P, 1.35P and shove all offer 75.
    opening = opening_actions(100, 20, 75, .5, 0)
    assert opening == pytest.approx({("check", None): .5, ("bet", 50): .1, ("all_in", 75): .4})
    assert facing_actions(90, 75, .5) == {("fold", None): .5, ("all_in", 75): .5}
    assert facing_actions(75, 75, .5) == {("fold", None): .5, ("all_in", 75): .5}
    assert facing_actions(50, 75, .5) == {("fold", None): .5, ("call", None): .5}


def test_reference_rejects_impossible_observation_and_handles_tiny_mass():
    with pytest.raises(ValueError, match="zero compatible"):
        posterior(HERO, BOARD, lambda _: 1, lambda _: 0)
    result = posterior(HERO, BOARD, lambda _: 1e-300, lambda _: 1e-300)
    assert list(result.values()) == pytest.approx([1 / 990] * 990)
    with pytest.raises(ValueError, match="invalid prior"):
        posterior(HERO, BOARD, lambda _: 1, lambda _: 1.01)


def test_candidate_log_interpolation_and_sparse_shrinkage():
    args = [np.array([2, 1, 0]), [100, 400], [[.8, 0, 1], [0, .4, 0]], 200]
    sparse, _, w = bet_update(*args, 0)
    assert w == 0
    assert sparse == pytest.approx([.05 * 2 / 3 + .95 * .8, .05 / 3 + .95 * .2, 0])
    # Geometric midpoint and equal size weight: that interpolation happens
    # to give the pooled posterior here, but a change to the exact upper size does.
    midpoint, _, w = bet_update(*args, 20)
    assert w == .5
    assert midpoint == pytest.approx(sparse)
    upper, _, _ = bet_update(*args[:-1], 400, 20)
    assert upper == pytest.approx([.05 * 2 / 3 + .475 * .8, .05 / 3 + .475 * .2 + .475, 0])
    point, _, _ = bet_update(*args[:-1], 100, 20)
    assert point[0] > midpoint[0] > upper[0]


def test_candidate_zero_evidence_and_zero_local_mass_do_not_collapse():
    flat, _, w = bet_update([2, 1, 0], [50, 100], [[0, 0, 1], [0, 0, 0]], 50, 300)
    assert flat == pytest.approx([2 / 3, 1 / 3, 0])
    assert w == 0
    empty_local, _, w = bet_update([2, 1], [50, 100], [[.8, 0], [0, 0]], 100, 300)
    assert empty_local == pytest.approx([.95 + .05 * 2 / 3, .05 / 3])
    assert w == 0
    with pytest.raises(ValueError):
        bet_update([1, 1], [50, 100], [[.8, 0], [.3, 0]], 100, 300)
