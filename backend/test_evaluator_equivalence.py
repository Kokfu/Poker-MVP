"""Phase 5B: the fast eval7 evaluator must be indistinguishable from Treys."""
import random

import pytest

import poker_analyzer
from poker_analyzer import (
    DISTINCT_HAND_CLASSES, EVALUATOR, FULL_DECK, Eval7Adapter, TreysAdapter,
    calculate_equity, hand_class_representatives,
)

REFERENCE = TreysAdapter()
FAST = Eval7Adapter(REFERENCE)


def test_production_evaluator_is_eval7():
    assert isinstance(EVALUATOR, Eval7Adapter)


def test_class_representatives_cover_every_hand_class_once():
    hands = hand_class_representatives()
    assert len(hands) == DISTINCT_HAND_CLASSES
    assert all(len(set(hand)) == 5 and set(hand) <= set(FULL_DECK) for hand in hands)
    ranks = {REFERENCE.score(list(hand[:2]), list(hand[2:])) for hand in hands}
    assert ranks == set(range(1, DISTINCT_HAND_CLASSES + 1))


def test_every_hand_class_has_identical_rank_and_category():
    for hand in hand_class_representatives():
        hole, board = list(hand[:2]), list(hand[2:])
        assert FAST.score(hole, board) == REFERENCE.score(hole, board)
        assert FAST.category(hole, board) == REFERENCE.category(hole, board)


@pytest.mark.parametrize("board_size", [3, 4, 5])
def test_random_hands_have_identical_ranks_and_categories(board_size):
    rng = random.Random(5_000 + board_size)
    for _ in range(20_000):
        cards = rng.sample(FULL_DECK, 2 + board_size)
        hole, board = cards[:2], cards[2:]
        assert FAST.score(hole, board) == REFERENCE.score(hole, board)
        assert FAST.category(hole, board) == REFERENCE.category(hole, board)


def test_invalid_card_counts_fail_like_treys():
    for hole, board in ((["As", "Kd"], []), (["As", "Kd"], ["2c", "3c"])):
        with pytest.raises(Exception) as reference_error:
            REFERENCE.score(hole, board)
        with pytest.raises(type(reference_error.value)):
            FAST.score(hole, board)


def _outcome(function, *args):
    try:
        return ("value", function(*args))
    except Exception as error:  # Treys itself raises for some duplicates
        return ("error", type(error))


def test_duplicate_card_probes_match_treys():
    # Range code can evaluate a combo that shares a card with the board.
    rng = random.Random(77)
    for _ in range(2_000):
        board = rng.sample(FULL_DECK, rng.choice((3, 4, 5)))
        hole = [rng.choice(board), rng.choice([c for c in FULL_DECK if c not in board])]
        assert _outcome(FAST.score, hole, board) == _outcome(REFERENCE.score, hole, board)
        assert _outcome(FAST.category, hole, board) == _outcome(REFERENCE.category, hole, board)


@pytest.mark.parametrize("hero,board", [
    (["As", "Kd"], []),
    (["7h", "7c"], ["2s", "9d", "Th"]),
    (["Qc", "Jc"], ["2c", "9c", "Th", "3d"]),
    (["5d", "4d"], ["2c", "9c", "Th", "3d", "Ah"]),
])
def test_seeded_equity_is_unchanged(monkeypatch, hero, board):
    monkeypatch.setattr(poker_analyzer, "EVALUATOR", REFERENCE)
    expected = calculate_equity(hero, board, 2_000, seed=17)
    monkeypatch.setattr(poker_analyzer, "EVALUATOR", FAST)
    assert calculate_equity(hero, board, 2_000, seed=17) == expected
