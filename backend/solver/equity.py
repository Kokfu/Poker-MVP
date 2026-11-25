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

from .combos import CARD_INDEX, CARDS, COMBOS, compatible

_EVAL_CARDS = {card: eval7.Card(card) for card in CARDS}
_EVAL_COMBOS = tuple((_EVAL_CARDS[a], _EVAL_CARDS[b]) for a, b in COMBOS)
_CARD_BITS = {card: 1 << index for card, index in CARD_INDEX.items()}
_COMBO_MASKS = np.array([_CARD_BITS[a] | _CARD_BITS[b] for a, b in COMBOS], dtype=np.uint64)


def rank_vector(board: list[str], combos: np.ndarray) -> np.ndarray:
    """eval7 strength (higher is better) for ``combos``; -1 where a combo hits the board."""
    board_mask = np.uint64(sum(_CARD_BITS[card] for card in set(board)))
    live = np.flatnonzero((_COMBO_MASKS[combos] & board_mask) == 0)
    ranks = np.full(len(combos), -1, dtype=np.int64)
    hand = [_EVAL_CARDS[card] for card in board] + [None, None]
    evaluate = eval7.evaluate
    # Convert the live combo ids once and reuse the existing card pairs.
    strengths = []
    for combo in combos[live].tolist():
        hand[-2], hand[-1] = _EVAL_COMBOS[combo]
        strengths.append(evaluate(hand))
    ranks[live] = strengths
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
    # A square matrix with identical combo order is antisymmetric. Visit
    # its upper blocks, then reflect the accumulated integer tallies once.
    symmetric = len(rows) > 96 and np.array_equal(rows, cols)
    block_size = 96 if symmetric else max(1, len(rows))
    diff = np.empty((block_size, len(cols)), dtype=np.int16)
    row_buf = np.empty(len(rows), dtype=np.int16)
    col_buf = row_buf if symmetric else np.empty(len(cols), dtype=np.int16)
    for index, full_board in enumerate(boards):
        ordinal = _ordinal_ranks(full_board, union)
        valid[index] = ordinal > 0
        # Blocked combos rank lowest here; their pairs are corrected below.
        np.take(ordinal, row_pos, out=row_buf)
        if not symmetric:
            np.take(ordinal, col_pos, out=col_buf)
        for start in range(0, len(rows), block_size):
            end = min(start + block_size, len(rows))
            first_column = start if symmetric else 0
            block = diff[:end - start, first_column:]
            np.subtract(row_buf[start:end, None], col_buf[None, first_column:], out=block)
            np.sign(block, out=block)
            total[start:end, first_column:] += block
    if symmetric:
        for start in range(block_size, len(rows), block_size):
            end = min(start + block_size, len(rows))
            total[start:end, :start] = -total[:start, start:end].T
    row_valid, col_valid = valid[:, row_pos], valid[:, col_pos]
    # Per runout, row_valid * (1 - col_valid) - (1 - row_valid) * col_valid
    # is row_valid - col_valid. The correction needs two counts, not two
    # matrix products. These sums count runouts exactly.
    row_count = row_valid.sum(axis=0)
    col_count = row_count if symmetric else col_valid.sum(axis=0)
    corrected = total - row_count[:, None] + col_count
    count = row_valid.T @ col_valid
    compat = compatible(rows, cols) & (count > 0)
    d = np.zeros(shape, dtype=np.float64)
    np.divide(corrected, count, out=d, where=compat)
    return d, compat
