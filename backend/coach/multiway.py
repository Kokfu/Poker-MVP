"""Multiway (2-8 opponents) spot advice from equity and pot odds.

The solver Coach is heads-up only.  For pots with more than one opponent this
module gives a simpler, clearly labelled estimate: Monte Carlo equity against
N random hands, compared with the equity the price of a call requires.  It
does not track opponents, ranges, or betting history, and it never touches the
heads-up solver path.
"""
from __future__ import annotations

import random
from typing import Any

from poker_analyzer import EVALUATOR, FULL_DECK, detect_draws, starting_hand_label

MIN_OPPONENTS, MAX_OPPONENTS = 1, 8
DEFAULT_ITERATIONS = 20_000


def multiway_equity(hero: list[str], board: list[str], opponents: int, iterations: int = DEFAULT_ITERATIONS,
                    seed: int | None = None) -> dict[str, float]:
    """Hero's share of the pot against ``opponents`` random hands (ties split evenly)."""
    if not MIN_OPPONENTS <= opponents <= MAX_OPPONENTS:
        raise ValueError(f"opponents must be {MIN_OPPONENTS}-{MAX_OPPONENTS}")
    unseen = [card for card in FULL_DECK if card not in set(hero) | set(board)]
    rng = random.Random(seed)
    missing = 5 - len(board)
    draw = 2 * opponents + missing
    wins = ties = 0
    share = 0.0
    for _ in range(iterations):
        deal = rng.sample(unseen, draw)
        final_board = board + deal[:missing]
        hero_score = EVALUATOR.score(hero, final_board)
        others = [EVALUATOR.score(deal[missing + 2 * i: missing + 2 * i + 2], final_board) for i in range(opponents)]
        best_other = min(others)  # lower score = stronger hand
        if hero_score < best_other:
            wins += 1
            share += 1.0
        elif hero_score == best_other:
            ties += 1
            share += 1.0 / (others.count(hero_score) + 1)
    return {"equity": share / iterations, "win_rate": wins / iterations, "tie_rate": ties / iterations}


def advise_multiway(hero: list[str], board: list[str], opponents: int, pot: float, to_call: float,
                    iterations: int = DEFAULT_ITERATIONS, seed: int | None = None) -> dict[str, Any]:
    cards = list(hero) + list(board)
    if len(hero) != 2:
        raise ValueError("enter exactly two hero cards")
    if len(board) not in (0, 3, 4, 5):
        raise ValueError("the board must have 0, 3, 4, or 5 cards")
    if any(card not in FULL_DECK for card in cards):
        raise ValueError("cards use notation like As, Kd, Th, 7c")
    if len(set(cards)) != len(cards):
        raise ValueError("duplicate cards are not allowed")
    if pot < 0 or to_call < 0:
        raise ValueError("pot and amount to call cannot be negative")

    result = multiway_equity(list(hero), list(board), opponents, iterations, seed)
    equity = result["equity"]
    fair_share = 1 / (opponents + 1)
    required = 0.0 if to_call == 0 else to_call / (pot + to_call)
    if to_call == 0:
        strong = equity >= min(0.6, 2 * fair_share)
        action = "bet" if strong else "check"
        reason = (
            f"You win about {equity:.0%} of the time against {opponents} {'hand' if opponents == 1 else 'hands'}, "
            f"well above an even share ({fair_share:.0%}). Bet for value." if strong else
            f"Your {equity:.0%} is not far enough above an even share ({fair_share:.0%}) to bet into {opponents} "
            f"{'player' if opponents == 1 else 'players'}. Check and see the next card."
        )
    elif equity < required - 0.02:
        action = "fold"
        reason = f"Calling {to_call:g} into {pot:g} needs {required:.0%} equity; you have about {equity:.0%}."
    elif equity < required + 0.10:
        action = "call"
        reason = f"Calling {to_call:g} into {pot:g} needs {required:.0%} equity; your {equity:.0%} is enough to call."
    else:
        action = "raise"
        reason = f"Your {equity:.0%} is far above the {required:.0%} a call needs. Raise for value."

    return {
        "opponents": opponents,
        "equity": equity,
        "win_rate": result["win_rate"],
        "tie_rate": result["tie_rate"],
        "fair_share": fair_share,
        "required_equity": required,
        "action": action,
        "reason": reason,
        "hand_label": starting_hand_label(list(hero)) if not board else EVALUATOR.category(list(hero), list(board)),
        "draws": detect_draws(list(hero), list(board)) if board else [],
        "iterations": iterations,
        "note": "Multiway advice uses equity against random hands and pot odds only. Players who stay in a pot "
                "usually hold better than random hands, so treat close spots more cautiously.",
    }
