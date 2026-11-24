"""Independent examples for river wager semantics, probabilities and payoffs."""
from math import fsum

import numpy as np
import pytest

from research.holdem.phase_4k import RANKER, STYLES
from research.holdem.phase_4q import cases
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV, RiverState
from research.holdem.river_wager_calibration import CLOSE, Opening, calibrate, empty_counts, hand_group
from research.holdem.river_wager_reference import counts, law
from simulation.actions import Action
from solver.tree import POSTFLOP_MENU, StreetState, legal_abstract_actions


def test_reference_distribution_and_cap_merges():
    aggressor = STYLES["loose_aggressive"]
    assert law(Opening(600, 1200, 1200, 100, False), 0, aggressor) == pytest.approx(
        [.66, .1598, .102, .0782]
    )
    assert law(Opening(600, 400, 400, 100, False), 0, aggressor) == pytest.approx(
        [.66, .1598, 0, .1802]
    )
    assert law(Opening(600, 50, 150, 100, False), 0, aggressor) == pytest.approx(
        [.66, 0, 0, .34]
    )
    assert law(Opening(600, 1200, 1200, 100, True), 4, aggressor) == pytest.approx(
        [.02, .2254, .294, .4606]
    )


@pytest.mark.parametrize("stack,other,wager,exhausts,closes", [
    (1800, 2100, 1800, True, True),
    (2100, 1800, 1800, False, True),
    (2100, 1800, 2100, True, True),
    (2100, 50, 2100, True, True),
    (2100, 1800, 700, False, False),
])
def test_actual_closure_and_legal_reply(stack, other, wager, exhausts, closes):
    opening = Opening(700, stack, other, 100, True)
    action, spent_stack, no_raise = opening.action(wager)
    assert (spent_stack, no_raise) == (exhausts, closes)
    assert (action == CLOSE) == closes
    state = StreetState("river", 1, (wager, 0), (stack-wager, other),
                        (350, 350), wager, (True, False), 1)
    kinds = {kind for _, kind, _ in legal_abstract_actions(state, POSTFLOP_MENU)}
    assert kinds == {"fold", "call"} if closes else "all_in" in kinds


def test_two_holding_reference_posterior_and_chip_payoff():
    hero, board = ("Jh", "Jd"), ("2s", "5h", "8c", "9d", "Ks")
    weak, strong = ("6d", "3d"), ("Kh", "9h")
    assert [hand_group(p, board, RANKER.score(list(p), list(board))) for p in (weak, strong)] == [0, 4]
    prior = {frozenset(weak): .8, frozenset(strong): .2}
    opening = Opening(600, 1200, 1200, 100, False)
    chances = {frozenset(p): law(opening, g, STYLES["loose_aggressive"])[CLOSE]
               for p, g in ((weak, 0), (strong, 4))}
    manual_equity = (.8 * .0782) / (.8 * .0782 + .2 * .423)
    bayes = posterior(hero, board, lambda p: prior.get(frozenset(p), 0), lambda p: chances.get(frozenset(p), 0))
    assert next(weight for pair, weight in bayes.items() if set(pair) == set(weak)) == pytest.approx(manual_equity)
    exact = ExactRiverEV(hero, board, lambda p, _: prior.get(frozenset(p), 0) * chances.get(frozenset(p), 0))
    state = RiverState(1800, 0, 1200, 1200, 0, 1200)
    assert exact.action_ev(state, Action("all_in")) == pytest.approx(3000 * manual_equity - 1200)
    assert exact.action_ev(state, Action("fold")) == 0
    with pytest.raises(ValueError):
        exact.action_ev(state, Action("raise", 2400))


def test_public_prefixes_and_sparse_shrinkage():
    style = STYLES["tight_passive"]
    rows = counts(style, 145, (0, 3, 30, 100))
    assert not rows[0].any()
    assert np.array_equal(rows[30], counts(style, 145, (30,))[30])
    assert (rows[100] >= rows[30]).all()
    opening = Opening(600, 400, 400, 100, False)
    base = np.array([[.8, .3], [.1, .1], [0., 0.], [.1, .6]])
    groups = np.array([0, 4])
    blank = empty_counts()
    assert np.allclose(calibrate(base, opening, groups, blank, blank), base)
    target = blank.copy()
    target[(*opening.cell, 0, CLOSE)] = 2
    fit = calibrate(base, opening, groups, blank, target)
    assert np.allclose(fit[:, 0], [.64, .08, 0, .28])
    assert np.allclose(fit[:, 1], base[:, 1])


def test_panel_targets_and_legal_reference_columns():
    for orientation in range(3):
        for case in cases(1, 12, orientation):
            opening = Opening(case.pot, case.behind, case.behind, 100, case.line[1] != "check")
            assert opening.action(case.bet)[2] == case.shove
            assert case.bet in opening.targets
            for group in range(6):
                for style in STYLES.values():
                    probs = law(opening, group, style)
                    assert fsum(probs) == pytest.approx(1)
                    assert all(0 <= p <= 1 for p in probs)
                    assert all(target is not None or p == 0 for p, target in zip(probs, opening.targets))
