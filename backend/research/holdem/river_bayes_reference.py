"""Independent Bayesian reference; used exclusively in offline evaluation."""
from itertools import combinations
from math import exp, fsum, isfinite, log

from poker_analyzer import FULL_DECK


def posterior(hero, board, prior, likelihood):
    """Enumerate unordered legal pairs; inputs are functions of a hypothetical pair.

    An impossible observation is undefined and raises rather than inventing a
    posterior. Evaluate the positive products in log space to avoid underflow.
    """
    blocked = set(hero) | set(board)
    if len(hero) != 2 or len(board) != 5 or len(blocked) != 7 or not blocked.issubset(FULL_DECK):
        raise ValueError("expected seven distinct, valid cards")
    weights = {}
    for pair in combinations((card for card in FULL_DECK if card not in blocked), 2):
        mass, chance = prior(pair), likelihood(pair)
        if not isfinite(mass) or mass < 0 or not isfinite(chance) or not 0 <= chance <= 1:
            raise ValueError("invalid prior or action likelihood")
        weights[pair] = log(mass) + log(chance) if mass and chance else float("-inf")
    top = max(weights.values())
    if not isfinite(top):
        raise ValueError("observation has zero compatible probability")
    scaled = {pair: exp(value - top) for pair, value in weights.items()}
    total = fsum(scaled.values())
    return {pair: mass / total for pair, mass in scaled.items()}


# An explicit extension of each Phase 4K reference's opening frequency.
# Conditional size masses are in .50P, .80P, 1.35P, shove order. These
# parameters specify ground truth only; candidate code cannot read them.
SIZES = (.50, .80, 1.35)
SIZE_MASS = (
    (.20, .40, .27, .13),  # high card
    (.60, .28, .10, .02),  # one pair
    (.22, .30, .27, .21),  # two pair or better
)


def opening_actions(pot, minimum, stack, bet_probability, strength):
    """Return a normalized law on legal concrete check/bet/all-in actions.

    Below-minimum bets move up to the minimum; sizes at/above the stack
    become a shove. Colliding targets have their masses added.
    """
    if (not 0 <= bet_probability <= 1 or strength not in (0, 1, 2)
            or min(pot, minimum, stack) <= 0):
        raise ValueError("invalid opening opportunity")
    actions = {("check", None): 1 - bet_probability}
    for size, fraction in zip((*SIZES, None), SIZE_MASS[strength], strict=True):
        target = stack if size is None else min(stack, max(minimum, round(pot * size)))
        key = ("all_in" if target == stack else "bet", target)
        actions[key] = actions.get(key, 0.0) + bet_probability * fraction
    return actions


def facing_actions(cost, stack, call_probability):
    """Phase 4K fold/call response law with exact or short all-in calls."""
    if min(cost, stack) <= 0 or not 0 <= call_probability <= 1:
        raise ValueError("invalid facing-wager opportunity")
    return {("fold", None): 1 - call_probability,
            ("all_in", stack) if stack <= cost else ("call", None): call_probability}
