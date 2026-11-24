from math import isclose

import numpy as np
import pytest

from research.holdem.phase_4k import STYLES
from research.holdem.phase_4p import (
    ACTIONS, CONTEXTS, PANELS, cases, calibrated_row, reference_action_law, reference_weights, sample_counts,
)
from solver.combos import combo_index


def test_reference_manual_limp_then_call():
    style = STYLES["tight_passive"]
    pairs = (("As", "Ah"), ("7s", "2d"))
    first = ((.96 - .12 * .25) * (1 - .53 * .48), (.55 - .12) * (1 - .17 * .48))
    next_call = ((.89 - .12 * .25) * (1 - .17 * .48), (.47 - .12) * (1 - .05 * .48))
    history = (("sb_first", "call"), ("sb_limp_raise", "call"))
    premium_mass, weak_mass = first[0] * next_call[0], first[1] * next_call[1]
    assert reference_weights(pairs, history, 15, style) == pytest.approx(
        (premium_mass / (premium_mass + weak_mass), weak_mass / (premium_mass + weak_mass))
    )
    assert reference_weights(pairs, history[:1], 15, style)[0] == pytest.approx(first[0] / sum(first))
    assert reference_weights(pairs, history, 9, style)[0] != reference_weights(pairs, history, 30, style)[0]


def test_reference_check_and_reraise_normalization():
    style = STYLES["loose_aggressive"]
    for site in CONTEXTS:
        for depth in (9, 15, 30):
            for pair in (("As", "Ah"), ("2d", "8d"), ("Ks", "4h")):
                law = reference_action_law(pair, site, depth, style)
                assert min(law) >= 0 and max(law) <= 1 and isclose(sum(law), 1)
                assert (law[0] == 0) == (site == "bb_limp")
    premium, weak = ("As", "Ah"), ("2d", "8d")
    for site in ("sb_first", "bb_open", "sb_threebet"):
        updates = reference_weights((premium, weak), ((site, "raise"),), 15, style)
        assert updates[0] > updates[1]


def test_support_projection_shrinkage_and_size_split():
    chart = np.array([[.1, 0.], [.3, .3], [.4, .7], [.2, 0.]])
    menu = (("fold", None), ("call", None), ("raise", 200), ("all_in", 900))
    groups = np.array([0, 0])
    empty = np.zeros((1, len(ACTIONS)))
    counts = np.array([[3., 12., 9.]])
    assert np.allclose(np.array([calibrated_row(chart, groups, menu, i, empty, empty)
                                for i in range(len(menu))]), chart)
    fitted = np.array([calibrated_row(chart, groups, menu, i, counts, counts) for i in range(len(menu))])
    assert np.allclose(fitted.sum(axis=0), 1)
    assert np.array_equal(fitted > 0, chart > 0)
    assert fitted[2, 0] / fitted[3, 0] == pytest.approx(2)
    assert fitted[1, 0] > chart[1, 0]


def test_blockers_and_training_prefixes():
    from itertools import combinations

    from poker_analyzer import FULL_DECK
    from solver.combos import card_mask

    seed, count, _ = PANELS["development"]
    case = next(cases(seed, count, 0))
    preflop = [pair for pair in combinations(FULL_DECK, 2) if not set(pair).intersection(case.hero)]
    final = [pair for pair in preflop if not set(pair).intersection(case.board)]
    assert (len(preflop), len(final)) == (1225, 990)
    for blocked, pairs in ((case.hero, preflop), (case.hero + case.board, final)):
        mask = card_mask(blocked)
        assert not mask[[combo_index(pair) for pair in pairs]].any()
        assert (~mask).sum() == len(pairs)
    samples = sample_counts("loose_passive", 101)
    duplicate = sample_counts("loose_passive", 101)
    for n, count in ((3, 4), (30, 32), (100, 128)):
        assert np.array_equal(samples[n], duplicate[n])
        assert np.all(samples[n].sum(axis=(2, 3)) == count)
    assert np.all(samples[3] <= samples[30]) and np.all(samples[30] <= samples[100])
