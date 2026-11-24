"""Research-only calibration of river opening likelihoods on a finite size menu."""
from dataclasses import dataclass
from math import ceil

import numpy as np
from treys import Evaluator

CHECK, HALF, POT, CLOSE = range(4)
LABELS = ("check", "half_pot", "pot", "closing")
RANKS = Evaluator()


@dataclass(frozen=True)
class Opening:
    pot: int
    bettor_stack: int
    defender_stack: int
    minimum: int
    turn_pressure: bool

    def __post_init__(self):
        if min(self.pot, self.bettor_stack, self.defender_stack, self.minimum) <= 0:
            raise ValueError("expected an unopened river with two live stacks")

    @property
    def effective(self):
        return min(self.bettor_stack, self.defender_stack)

    @property
    def spr(self):
        return self.effective / self.pot

    @property
    def cell(self):
        return (int(self.spr > 1) + int(self.spr > 2), int(self.turn_pressure))

    @property
    def targets(self):
        # Same finite size abstraction as Coach, expressed in actual chips.
        half, full = max(self.minimum, ceil(self.pot / 2)), max(self.minimum, self.pot)
        cap = self.effective
        half = half if 100 * half < 85 * cap else None
        full = full if 100 * full < 85 * cap and full != half else None
        return (0, half, full, cap)

    def action(self, target):
        """Classify an actual target without treating high bet/pot as all-in."""
        if target == 0:
            return CHECK, False, False
        if not 0 < target <= self.bettor_stack or (target < self.minimum and target != self.bettor_stack):
            raise ValueError("illegal opening target")
        exhausts = target == self.bettor_stack
        closes = exhausts or target >= self.defender_stack
        if closes:
            return CLOSE, exhausts, True
        if target not in self.targets:
            raise ValueError("non-closing target outside the finite menu")
        return self.targets.index(target), exhausts, False


def hand_group(pair, board, rank):
    """Three made-hand tiers, each split by a public suit/blocker feature."""
    tier = 9 - max(7, RANKS.get_rank_class(rank))
    relevant = any(
        (sum(card[1] == suit for card in board) >= 3 and any(
            card[1] == suit and card[0] in "AKQ" for card in pair
        )) or (
            sum(card[1] == suit for card in board) == 2
            and sum(card[1] == suit for card in board[:4]) == 2
            and all(card[1] == suit for card in pair)
        )
        for suit in "shdc"
    )
    return tier * 2 + relevant


def empty_counts():
    return np.zeros((3, 2, 6, 4))


def calibrate(production, opening, groups, population, profile):
    """Dirichlet-style counts on the legal menu; no current hand labels."""
    legal = np.array([target is not None for target in opening.targets])
    a, b = opening.cell
    # Use global tier counts as a weak prior when the blocker split is sparse.
    pooled = population.reshape(3, 2, 3, 2, 4).sum(axis=(0, 1, 3))
    pooled = pooled[groups // 2].T * legal[:, None]
    cell = population[a, b, groups].T
    local = profile[a, b, groups].T
    counts = (
        8 * production + 8 * pooled / (pooled.sum(axis=0) + 8)
        + 24 * cell / (cell.sum(axis=0) + 24) + local
    ) * legal[:, None]
    return counts / counts.sum(axis=0)
