"""Multiway equity-and-pot-odds advice with optional public action likelihoods."""
from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from typing import Any

from poker_analyzer import EVALUATOR, FULL_DECK, detect_draws, multiway_equity, starting_hand_label  # noqa: F401 (re-exported)
from simulation.range_intelligence import PublicRangeTracker, WeightedRange, heuristic_preflop_range

DEFAULT_ITERATIONS = 20_000
BOARD_AT_STREET = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
MAX_PUBLIC_ACTIONS = 32


@dataclass(frozen=True)
class PublicAction:
    seat: int
    street: str
    action: str
    pot_fraction: float | None = None


def ranges_enabled() -> bool:
    return getenv("POKER_COACH_MULTIWAY_RANGES") == "1"


def _opponent_ranges(hero, board, opponents, actions):
    trackers = {}
    previous_count = 0
    for event in actions:
        count = BOARD_AT_STREET[event.street]
        if not 1 <= event.seat <= opponents:
            raise ValueError("action seat is outside the active opponents")
        if not previous_count <= count <= len(board):
            raise ValueError("actions must be in street order and have the required public board cards")
        previous_count = count
        if event.seat not in trackers:
            trackers[event.seat] = PublicRangeTracker.uniform(hero)
        tracker = trackers[event.seat]
        if count == 0 and event.action in ("call", "limp"):
            likelihood = dict(heuristic_preflop_range(hero, action=event.action).weights)
            tracker.weighted_range = WeightedRange(tuple(
                (combo, weight * likelihood[combo]) for combo, weight in tracker.weighted_range.weights
            )).normalized()
        else:
            tracker.observe(event.action, board[:count], event.pot_fraction)

    distributions = []
    summary = []
    for seat, tracker in sorted(trackers.items()):
        tracker.sync_board(board)
        tracker.assert_invariants(board)
        combos, weights = zip(*tracker.weighted_range.weights)
        distributions.append(([combo.cards for combo in combos], weights))
        summary.append({"seat": seat, "effective_combos": round(1 / sum(weight**2 for weight in weights), 1)})
    return distributions, summary


def advise_multiway(hero: list[str], board: list[str], opponents: int, pot: float, to_call: float,
                    iterations: int = DEFAULT_ITERATIONS, seed: int | None = None, *,
                    actions: tuple[PublicAction, ...] = ()) -> dict[str, Any]:
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

    distributions, summary = _opponent_ranges(hero, board, opponents, actions)
    result = multiway_equity(list(hero), list(board), opponents, iterations, seed, opponent_ranges=distributions)
    equity = result["equity"]
    fair_share = 1 / (opponents + 1)
    required = 0.0 if to_call == 0 else to_call / (pot + to_call)
    if to_call == 0:
        strong = equity >= min(0.6, 2 * fair_share)
        action = "bet" if strong else "check"
        reason = (
            f"Your estimated equity against {opponents} {'hand' if opponents == 1 else 'hands'} is {equity:.0%}, "
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

    note = ("Multiway advice uses equity against random hands and pot odds only. Players who stay in a pot "
            "usually hold better than random hands, so treat close spots more cautiously.")
    if summary:
        note = ("Recorded actions reweight each opponent's range using public cards available on that street. "
                "Opponents without recorded actions have uniform ranges. The estimate compares showdown equity with pot odds.")
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
        "note": note,
        **({"opponent_ranges": summary} if summary else {}),
    }
