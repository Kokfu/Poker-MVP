from dataclasses import replace
from itertools import combinations
from types import SimpleNamespace

import numpy as np
import pytest

from coach.service import _replay
from poker_analyzer import FULL_DECK
from research.holdem.phase_4o import PriorTrace
from research.holdem.phase_4r import (
    RangeSupportError, SupportReplay, conditional_range, failed_case, replay_trace, train,
)
from solver.combos import COMBOS, COMBO_COUNT, card_mask, combo_index


@pytest.fixture(scope="module")
def collapse():
    case = failed_case()
    profile = train("tight_aggressive", 131, (3,))[3]
    return replay_trace(PriorTrace(), case, profile), replay_trace(SupportReplay(), case, profile)


@pytest.mark.machine_exact
def test_replay_cutoff_eliminates_the_turn_tail_before_check(collapse):
    baseline, candidate = collapse
    assert baseline["explanation"] == {"source": "fallback", "reason": "ReplayError: empty range"}
    turn = [e for e in baseline["trace"] if len(e["board"]) == 4 and e["seat"] == 1]
    assert [e["event"] for e in turn] == ["reveal", "solve_cutoff", "check"]
    assert [e["board_compatible_positive"] for e in turn] == [1119, 1, 1]
    assert turn[-1]["remaining_legal_holdings"] == [("6s", "7s")]
    assert turn[1]["removed_mass_fraction"] == pytest.approx(.340142, abs=1e-6)
    # Exact value .9999781124745216 holds only with single-thread BLAS (OPENBLAS_NUM_THREADS=1);
    # other thread layouts shift the retained check likelihood by ~2e-5, so assert it stays near 1.
    assert turn[2]["raw_mass"] / turn[1]["raw_mass"] == pytest.approx(.99998, abs=1e-4)
    river = next(e for e in baseline["trace"] if len(e["board"]) == 5 and e["seat"] == 1)
    assert river["eliminated_holdings"] == [("6s", "7s")]
    assert river["legal_positive"] == 0 and river["normalization_sum"] is None
    assert candidate["explanation"]["source"] == "postflop_solve"
    assert candidate["advice"]["action"] in {"fold", "all_in"}
    assert sum(candidate["explanation"]["probabilities"]) == pytest.approx(1, abs=.0001)


@pytest.mark.parametrize("cards", [
    ("3c", "5c"), ("3c", "5c", "Qc", "3s", "Ks"),
    ("3c", "5c", "Qc", "3s", "Ks", "8h"),
    ("3c", "5c", "Qc", "3s", "Ks", "8h", "6s"),
])
def test_uniform_support_matches_independent_deck_enumeration(cards):
    weights = conditional_range(np.ones(COMBO_COUNT), card_mask(cards))
    expected = set(combinations([card for card in FULL_DECK if card not in cards], 2))
    assert {COMBOS[i] for i in np.flatnonzero(weights)} == expected
    assert weights[weights > 0] == pytest.approx(np.full(len(expected), 1 / len(expected)))


def test_blocker_removes_high_weight_and_preserves_tiny_positive_odds():
    weights = np.zeros(COMBO_COUNT)
    blocked, first, second = map(combo_index, [("6s", "7s"), ("2c", "2d"), ("4c", "4d")])
    tiny = np.nextafter(0., 1.)
    weights[[blocked, first, second]] = [1, tiny, 3 * tiny]
    result = conditional_range(weights, card_mask(("6s",)))
    assert np.flatnonzero(result).tolist() == sorted([first, second])
    assert result[[blocked, first, second]].tolist() == [0, .25, .75]
    with pytest.raises(RangeSupportError, match="all positive holdings blocked"):
        conditional_range(weights, card_mask(("6s", "2c", "4c")))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.])
def test_bad_weights_are_invalid_input(value):
    weights = np.ones(COMBO_COUNT)
    weights[0] = value
    with pytest.raises(ValueError, match="invalid reach weights"):
        conditional_range(weights, card_mask(()))


@pytest.mark.parametrize("action", ["check", "call", "bet", "raise", "all_in"])
def test_action_conditioning_keeps_model_zeros_and_detects_contradictions(action):
    bot = SupportReplay()
    ids = np.array([1, 2, 3])
    weights = np.zeros(COMBO_COUNT)
    weights[[1, 2]] = [2, 3]
    node = SimpleNamespace(player=1, state=SimpleNamespace(street="turn"), actions=((action, None),))
    solve = SimpleNamespace(tree=SimpleNamespace(nodes=[node]), combos=(ids, ids),
                            average={0: np.array([[.5, 0., 1.], [.5, 1., 0.]])})
    posterior = conditional_range(bot._apply_strategy(weights, solve, 0, 0), card_mask(()))
    assert posterior[1] == 1 and np.count_nonzero(posterior) == 1
    weights[1] = 0
    with pytest.raises(RangeSupportError, match="turn observed action: zero model reach"):
        bot._apply_strategy(weights, solve, 0, 0)
    with pytest.raises(RangeSupportError, match="zero model reach"):
        conditional_range(np.zeros(COMBO_COUNT), card_mask(()))


@pytest.mark.parametrize("bad_card", ["3c", "Xs"])
def test_coach_rejects_impossible_cards_before_advice(bad_card):
    spot = failed_case().spot()
    with pytest.raises(ValueError, match="duplicate cards|cards use notation"):
        _replay(replace(spot, board=[*spot.board[:-1], bad_card]), SupportReplay())
