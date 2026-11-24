from dataclasses import replace
from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest

from coach.service import _replay
from research.holdem.phase_4o import PriorTrace
from research.holdem.phase_4r import RangeSupportError, conditional_range, failed_case, replay_trace, train
from research.holdem.range_support import MAX_COLUMNS, ResearchReplay, closing_bounds, update_reach, working_set
from solver.combos import COMBO_COUNT, card_mask, combo_index


@pytest.mark.parametrize("action", ["check", "call", "bet", "raise", "all_in"])
def test_projected_observation_preserves_omitted_odds_and_exact_zeros(action):
    weights = np.zeros(COMBO_COUNT)
    weights[:5] = [4., 2., 1., .5, 0.]
    ids = np.array([0, 1])
    tree_node = SimpleNamespace(player=1, state=SimpleNamespace(street="turn"), actions=((action, None),))
    solved = SimpleNamespace(tree=SimpleNamespace(nodes=[tree_node]), combos=(ids, ids),
                             average={0: np.array([[.25, 0.], [.75, 1.]])})
    actual = ResearchReplay(True)._apply_strategy(weights, solved, 0, 0)
    assert actual[:5] == pytest.approx([1, 0, 1 / 6, 1 / 12, 0])
    assert np.array_equal(weights[:5], [4, 2, 1, .5, 0])
    assert conditional_range(actual, card_mask(()))[:5] == pytest.approx([.8, 0, 2 / 15, 1 / 15, 0])


def test_selection_is_bounded_stable_and_accounts_for_board_legal_mass():
    weights = np.ones(COMBO_COUNT)
    blocked = card_mask(("Qs", "Js", "Ts"))
    required = combo_index(("Ac", "Ad"))
    selected = working_set(weights, blocked, required)
    assert len(selected.ids) == MAX_COLUMNS
    expected = sorted([*np.flatnonzero(~blocked)[:MAX_COLUMNS - 1], required])
    assert selected.ids.tolist() == expected
    assert selected.positive == 1176
    assert selected.omitted == pytest.approx((1176 - MAX_COLUMNS) / 1176)
    assert selected.retained + selected.omitted == 1
    assert not blocked[selected.ids].any()


def test_blocked_heavy_combo_removed_and_compatible_donor_reserved():
    weights = np.zeros(COMBO_COUNT)
    heavy, survivor, next_hand = map(combo_index, [("6s", "7s"), ("2c", "2d"), ("4c", "4d")])
    weights[[heavy, survivor, next_hand]] = [1, .001, .0001]
    working = working_set(weights, card_mask(()), None, ~card_mask(("7s",)))
    assert working.ids.tolist() == sorted([heavy, survivor])
    updated = update_reach(weights, working.ids, np.array([.9, .9]))
    blocked = card_mask(("6s",))
    posterior = conditional_range(updated, blocked)
    assert posterior[[heavy, survivor, next_hand]] == pytest.approx([0, 10 / 11, 1 / 11])
    assert working_set(updated, blocked, None).positive == 2


@pytest.mark.parametrize("omitted,reason", [(True, "unsupported on omitted"), (False, "zero model reach")])
def test_contradiction_is_explicit_and_does_not_change_prior(omitted, reason):
    weights = np.zeros(COMBO_COUNT)
    weights[:2] = [1, float(omitted)]
    with pytest.raises(RangeSupportError, match=reason):
        update_reach(weights, np.array([0]), np.array([0.]))
    assert weights[0] == 1


def test_narrow_subnormal_reach_and_true_empty_range():
    weights = np.zeros(COMBO_COUNT)
    first, second = combo_index(("2c", "2d")), combo_index(("6s", "7s"))
    tiny = np.nextafter(0., 1.)
    weights[[first, second]] = [tiny, 3 * tiny]
    selected = working_set(weights, card_mask(()), None)
    updated = update_reach(weights, selected.ids, np.full(2, .25))
    assert np.isfinite(updated).all()
    assert conditional_range(updated, card_mask(()))[[first, second]] == pytest.approx([.25, .75])
    with pytest.raises(RangeSupportError, match="all positive holdings blocked"):
        working_set(updated, card_mask(("2c", "6s")), None)
    with pytest.raises(RangeSupportError, match="no Hero-compatible"):
        working_set(updated, card_mask(()), None, ~card_mask(("2c", "6s")))


@pytest.mark.parametrize("bad", [np.inf, np.nan, -1., 1.5])
def test_bad_observed_likelihood(bad):
    with pytest.raises(ValueError, match="invalid observed"):
        update_reach(np.ones(COMBO_COUNT), np.array([0]), np.array([bad]))


def test_odds_envelope_matches_exhaustive_vertices_and_can_approve_cover():
    weights = np.array([.1, .2, .7])
    payoff = np.array([-5, 2, 9])
    values = [(weights * multiplier) @ payoff / (weights * multiplier).sum()
              for multiplier in product((1, 2), repeat=3)]
    bounds = closing_bounds(weights, payoff)
    assert bounds == pytest.approx([min(values), max(values)])
    assert bounds[0] > 0


@pytest.fixture(scope="module")
def collapse():
    case = failed_case()
    profile = train("tight_aggressive", 131, (3,))[3]
    bot = ResearchReplay(True)
    return case, profile, replay_trace(PriorTrace(), case, profile), replay_trace(bot, case, profile), bot


def test_exact_4q_collapse_is_repaired_and_blocker_still_removes_singleton(collapse):
    _, _, incumbent, candidate, bot = collapse
    assert incumbent["explanation"]["reason"] == "ReplayError: empty range"
    assert candidate["explanation"]["source"] == "postflop_solve"
    turn = [e for e in incumbent["trace"] if e["seat"] == 1 and len(e["board"]) == 4]
    assert [e["board_compatible_positive"] for e in turn] == [1119, 1, 1]
    assert turn[-1]["remaining_legal_holdings"] == [("6s", "7s")]
    river = next(e for e in candidate["trace"] if e["seat"] == 1 and len(e["board"]) == 5)
    assert ("6s", "7s") in river["eliminated_holdings"]
    assert river["legal_positive"] > 1
    assert river["normalization_sum"] == pytest.approx(1.)
    assert bot.estimate[combo_index(("6s", "7s"))] == 0
    assert bot.probabilities.sum() == pytest.approx(1.)


def test_repeated_and_edited_coach_replay_on_same_advisor(collapse):
    case, profile, _, candidate, bot = collapse
    _, first, _ = _replay(case.spot(), bot, profile.snapshot)
    assert first["advice"] == candidate["advice"]
    changed_case = replace(case, depth=30)
    _, second, _ = _replay(changed_case.spot(), bot, profile.snapshot)
    independent = ResearchReplay(True)
    profile.attach(independent)
    _, expected, _ = _replay(changed_case.spot(), independent, profile.snapshot)
    assert second["advice"] == expected["advice"]
    assert second["explanation"]["probabilities"] == expected["explanation"]["probabilities"]
    assert second["advice"]["action"] in {"fold", "all_in"}


def test_preflop_advice_matches_incumbent_exactly():
    spot = replace(failed_case().spot(), board=[], actions=[])
    baseline = _replay(spot, ResearchReplay())[1]
    candidate = _replay(spot, ResearchReplay(True))[1]
    assert candidate == baseline
