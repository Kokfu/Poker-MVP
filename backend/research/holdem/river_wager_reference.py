"""Synthetic Phase 4Q action law and sampled public calibration observations."""
from random import Random

from poker_analyzer import FULL_DECK
from research.holdem.phase_4k import BIG_BLIND, RANKER
from research.holdem.river_wager_calibration import CHECK, HALF, POT, CLOSE, Opening, empty_counts, hand_group


REVEAL = (.75, .50, .40, .25)
PROFILES = (0, 3, 30, 100)


def law(opening, group, style):
    """Return P(check, half-pot, pot, closing) under an explicit synthetic law.

    Unavailable attempted sizes contribute to the closing target, including
    a short all-in below the nominal minimum. The reference uses no Hero cards.
    """
    tier, blocker = divmod(group, 2)
    rates = (.34, .62, .90) if style.aggressive else (.045, .17, .58)
    rate = rates[tier] * (.90 if style.tight else 1)
    rate *= (1.20 if tier == 2 else .85) if opening.turn_pressure else 1
    if blocker and tier == 0:
        rate *= 1.35
    rate = min(.98, rate)
    sizes = [(.47, .30, .23), (.67, .27, .06), (.23, .30, .47)][tier]
    size = list(sizes)
    if not style.aggressive:
        size[2] *= .55 if tier < 2 else 1.20
    if opening.spr > 2:
        size[2] *= (.60, .30, .80)[tier]
    if blocker and tier == 0:
        size[2] *= 1.50
    scale = rate / sum(size)
    result = [1 - rate, 0., 0., 0.]
    for action, mass in zip((HALF, POT, CLOSE), size, strict=True):
        result[action if opening.targets[action] is not None else CLOSE] += scale * mass
    return result


def public_sample(rng, style, index):
    """A scripted Hero randomizes showdown independently conditional on action.

    A revealed pair is all the estimator is allowed to use. A check reaches
    showdown if Hero checks behind (or Villain checks back); for each wager,
    the audit Hero calls at the declared rate. Other outcomes are unlabeled.
    """
    # Villain acts first; Hero may bet after a check and Villain then mucks.
    # The same context grid is used as evaluation, but cards and sequences are
    # independent and no conditional probability is sent to the estimator.
    pot, effective, pressure = (
        (1200, 300, True), (1000, 750, False), (800, 1000, True),
        (500, 1000, False), (1000, 2500, True), (500, 2750, False),
    )[index % 6]
    opening = Opening(pot, effective, effective, BIG_BLIND, pressure)
    board = tuple(rng.sample(FULL_DECK, 5))
    pool = tuple(card for card in FULL_DECK if card not in board)
    pair = tuple(rng.sample(pool, 2))
    group = hand_group(pair, board, RANKER.score(list(pair), list(board)))
    action = rng.choices(range(4), law(opening, group, style))[0]
    revealed = group if rng.random() < REVEAL[action] else None
    return opening, action, revealed


def counts(style, seed, prefixes):
    rng = Random(seed)
    sizes = tuple(sorted(set(prefixes)))
    table = empty_counts()
    snapshots = {0: table.copy()} if 0 in sizes else {}
    for index in range(max(sizes)):
        opening, action, group = public_sample(rng, style, index)
        if group is not None:
            table[(*opening.cell, group, action)] += min(REVEAL) / REVEAL[action]
        if index + 1 in sizes:
            snapshots[index + 1] = table.copy()
    return snapshots
