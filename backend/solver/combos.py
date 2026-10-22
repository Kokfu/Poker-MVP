"""Hole-card combo indexing shared by every solver component."""
from __future__ import annotations

from itertools import combinations

import numpy as np

from poker_analyzer import FULL_DECK, RANK_VALUE, RANKS

CARDS: tuple[str, ...] = FULL_DECK
CARD_INDEX = {card: index for index, card in enumerate(CARDS)}
COMBOS: tuple[tuple[str, str], ...] = tuple(combinations(CARDS, 2))
COMBO_COUNT = len(COMBOS)  # 1,326
COMBO_INDEX = {frozenset(combo): index for index, combo in enumerate(COMBOS)}
COMBO_CARDS = np.array([[CARD_INDEX[a], CARD_INDEX[b]] for a, b in COMBOS], dtype=np.int16)


def combo_index(cards) -> int:
    return COMBO_INDEX[frozenset(cards)]


def card_mask(cards) -> np.ndarray:
    """Boolean vector over combos: True where the combo uses any of ``cards``."""
    indices = [CARD_INDEX[card] for card in cards]
    if not indices:
        return np.zeros(COMBO_COUNT, dtype=bool)
    return np.isin(COMBO_CARDS, indices).any(axis=1)


def compatible(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """``(len(first), len(second))`` mask of combo pairs that share no card."""
    # Card-incidence product: a pair clashes when they share any card.
    a = np.zeros((len(first), 52), dtype=np.float32)
    b = np.zeros((len(second), 52), dtype=np.float32)
    a[np.arange(len(first))[:, None], COMBO_CARDS[first]] = 1.0
    b[np.arange(len(second))[:, None], COMBO_CARDS[second]] = 1.0
    return (a @ b.T) == 0


def hand_class(cards) -> str:
    """Canonical 169-class label such as ``AA``, ``AKs``, or ``T9o``."""
    first, second = sorted(cards, key=lambda card: RANK_VALUE[card[0]], reverse=True)
    if first[0] == second[0]:
        return first[0] * 2
    return first[0] + second[0] + ("s" if first[1] == second[1] else "o")


HAND_CLASSES: tuple[str, ...] = tuple(
    [rank * 2 for rank in reversed(RANKS)]
    + [high + low + suffix for i, high in enumerate(reversed(RANKS)) for low in list(reversed(RANKS))[i + 1:] for suffix in "so"]
)
CLASS_INDEX = {label: index for index, label in enumerate(HAND_CLASSES)}
COMBO_CLASS = np.array([CLASS_INDEX[hand_class(combo)] for combo in COMBOS], dtype=np.int16)
CLASS_COMBO_COUNT = np.bincount(COMBO_CLASS, minlength=len(HAND_CLASSES))
