import numpy as np
import pytest

from research.holdem.phase_4k import STYLES
from research.holdem.phase_4o import action_row, audit_losses, recover_prior, reference_likelihood
from research.holdem.river_bayes_reference import posterior
from solver.bot import Step
from solver.tree import StreetState


def test_support_recovery_uses_only_compatible_retained_donors():
    row = action_row(
        np.array([9., 1., 3., .01, 0.]), np.array([0, 1, 2]),
        np.array([1., .2, .6]), np.array([True, False, False, False, False]),
        np.array([1, 2, 3, 4]),
    )
    assert row == pytest.approx([.2, .6, .5, .5])
    reach = recover_prior(np.array([1., 3., .01, 0.]), [row, np.array([0., 1., .5, .8])])
    assert reach == pytest.approx(np.array([0., 1.8, .0025, 0.]) / 1.8025)
    assert np.array_equal(reach, recover_prior(np.array([1., 3., .01, 0.]), [row, [0., 1., .5, .8]]))


def test_loss_attribution_distinguishes_pruning_and_action_zeros():
    combos = [("As", "Ad"), ("Ts", "Td"), ("Ks", "Kd"), ("2s", "2d")]
    stages = [
        ("chart", 1, np.array([2., .01, 1., 0.])),
        ("flop_prune", 1, np.array([2., 0., 1., 0.])),
        ("flop_check", 2, np.array([1., 0., 0., 0.])),
    ]
    rows = [np.array([.2, .3, .4, .1]), np.array([.5, .5, .25, 1.]), np.ones(4)]
    prior = np.array([.1, .15, .1, .1]) / .45
    audit, removed = audit_losses(stages, rows, prior, prior, combos)
    assert removed == [None, "flop_prune", "flop_check", "chart"]
    assert [a["newly_absent"] for a in audit.values()] == [1, 1, 1]
    assert audit["flop_prune"]["prior_mass"] == pytest.approx(1 / 3)
    assert audit["flop_prune"]["prefix_missing"] == pytest.approx(.4)


def test_independent_pre_action_reference_for_paid_call_then_check_and_call():
    style = STYLES["tight_passive"]
    pre = StreetState("preflop", 0, (50, 100), (1450, 1400), (0, 0), 100)
    check = StreetState("flop", 0, (0, 0), (1300, 1300), (200, 200), 100)
    call = StreetState("turn", 0, (0, 200), (1300, 1100), (200, 200), 200)
    history = (Step("preflop", pre, 0, "call", None), Step("flop", check, 0, "check", None),
               Step("turn", call, 0, "call", None))
    hero, board = ("9s", "3c"), ("As", "Ks", "Qs", "Js", "2d")
    aces, unpaired = ("Ac", "Ad"), ("8d", "7h")

    def mass(pair):
        if set(pair) == set(aces):
            ranks = (None, 4000, 4000)  # one pair
        elif set(pair) == set(unpaired):
            ranks = (None, 7000, 7000)  # high card
        else:
            return 0
        return np.prod([reference_likelihood(step, style, pair, rank)
                        for step, rank in zip(history, ranks, strict=True)])

    expected = .85 * .92 * .78
    other = .09 * .98 * .12
    result = posterior(hero, board, mass, lambda _: 1)
    assert len(result) == 990
    assert sum(result.values()) == pytest.approx(1)
    assert max(result.values()) == pytest.approx(expected / (expected + other))
    assert min(v for v in result.values() if v) == pytest.approx(other / (expected + other))
    assert not any(set(pair) & set(hero + board) for pair in result)
