"""Phase 5B: range-feature memoization must not change any value."""
import random

from poker_analyzer import FULL_DECK
from simulation.range_intelligence import (
    HoleCardCombo, _combo_board_features, combo_board_features, describe_preflop,
)


def test_cached_features_equal_uncached_values():
    rng = random.Random(11)
    for _ in range(3_000):
        cards = rng.sample(FULL_DECK, 2 + rng.choice((0, 3, 4, 5)))
        combo, board = HoleCardCombo(cards[0], cards[1]), tuple(cards[2:])
        assert combo_board_features(combo, board) == _combo_board_features.__wrapped__(combo, board)
        assert combo_board_features(combo, list(board)) == combo_board_features(combo, board)
        assert describe_preflop(combo) == describe_preflop.__wrapped__(combo)


def test_callers_cannot_mutate_the_cache():
    combo, board = HoleCardCombo("As", "Kd"), ("2c", "7h", "Td")
    first = combo_board_features(combo, board)
    first["made_hand"] = "tampered"
    assert combo_board_features(combo, board)["made_hand"] == "high_card"
