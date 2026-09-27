"""Vectorized showdown and equity matrices for range-versus-range solving.

Values are expressed as ``D[i, j] = P(win) - P(lose)`` for row combo ``i``
against column combo ``j`` (so ``equity = (1 + D) / 2``).  Pairs that share a
card are impossible and carry ``D = 0`` plus ``compat = False``.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import random

import eval7
import numpy as np

from .combos import CARD_INDEX, CARDS, COMBO_CARDS, compatible

_EVAL_CARDS = [eval7.Card(card) for card in CARDS]


def rank_vector(board: list[str], combos: np.ndarray) -> np.ndarray:
    """eval7 strength (higher is better) for ``combos``; -1 where a combo hits the board."""
    board_cards = [_EVAL_CARDS[CARD_INDEX[card]] for card in board]
    board_set = {CARD_INDEX[card] for card in board}
    evaluate = eval7.evaluate
    ranks = np.full(len(combos), -1, dtype=np.int64)
    for position, combo in enumerate(combos):
        first, second = COMBO_CARDS[combo]
        if first in board_set or second in board_set:
            continue
        ranks[position] = evaluate(board_cards + [_EVAL_CARDS[first], _EVAL_CARDS[second]])
    return ranks


def _ordinal_ranks(board: list[str], union: np.ndarray) -> np.ndarray:
    """Dense int16 strength order per runout; blocked combos get 0 (lowest)."""
    ranks = rank_vector(board, union)
    return np.unique(ranks, return_inverse=True)[1].astype(np.int16) + (0 if (ranks < 0).any() else 1)


def runout_boards(board: list[str], samples: int | None, seed_text: str = "") -> list[list[str]]:
    """Every completion of ``board`` to five cards, or a seeded sample of them."""
    missing = 5 - len(board)
    if missing == 0:
        return [list(board)]
    remaining = [card for card in CARDS if card not in board]
    digest = sha256(("runouts|" + "".join(board) + "|" + seed_text).encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    if missing > 2:
        # Preflop: never materialize millions of boards; sample with replacement.
        if samples is None:
            raise ValueError("preflop equity requires a sample count")
        return [list(board) + rng.sample(remaining, missing) for _ in range(samples)]
    completions = list(combinations(remaining, missing))
    if samples is not None and samples < len(completions):
        completions = rng.sample(completions, samples)
    return [list(board) + list(extra) for extra in completions]


def equity_matrix(board: list[str], rows: np.ndarray, cols: np.ndarray, samples: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(D, compat)`` for rows versus cols over all (or sampled) runouts.

    Exact on the river and, when ``samples`` is None, exact on the turn.
    """
    union = np.union1d(rows, cols)
    row_pos, col_pos = np.searchsorted(union, rows), np.searchsorted(union, cols)
    shape = (len(rows), len(cols))
    boards = runout_boards(board, samples)
    total = np.zeros(shape, dtype=np.int16 if len(boards) < 30_000 else np.int32)
    valid = np.zeros((len(boards), len(union)), dtype=np.float32)
    for index, full_board in enumerate(boards):
        ordinal = _ordinal_ranks(full_board, union)
        valid[index] = ordinal > 0
        # Blocked combos rank lowest here; their pairs are corrected below.
        total += np.sign(ordinal[row_pos][:, None] - ordinal[col_pos][None, :])
    row_valid, col_valid = valid[:, row_pos], valid[:, col_pos]
    row_blocked, col_blocked = 1.0 - row_valid, 1.0 - col_valid
    # Remove (valid row vs blocked col: +1) and (blocked row vs valid col: -1).
    corrected = total - (row_valid.T @ col_blocked) + (row_blocked.T @ col_valid)
    count = row_valid.T @ col_valid
    compat = compatible(rows, cols) & (count > 0)
    d = np.zeros(shape, dtype=np.float64)
    np.divide(corrected, count, out=d, where=compat)
    return d, compat
