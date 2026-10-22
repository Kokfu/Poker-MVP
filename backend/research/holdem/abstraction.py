"""Deterministic, information-set-safe Hold'em research abstractions.

The module intentionally has no ``HandEngine`` dependency.  Its input is the
immutable, player-visible ``DecisionState`` boundary, and its only concrete
output is an engine action using the engine's documented total-target contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil
from typing import Literal

from poker_analyzer import EVALUATOR, RANK_VALUE, STRAIGHTS, SUITS
from simulation.actions import Action
from simulation.decision_state import DecisionState, PublicAction


AGGRESSION_FRACTIONS: tuple[tuple[str, float], ...] = (
    ("half_pot", 0.50),
    ("three_quarter_pot", 0.75),
    ("pot_and_quarter", 1.25),
)
CARD_BUCKETS = (
    "preflop_premium", "preflop_strong", "preflop_medium",
    "preflop_speculative", "preflop_weak", "postflop_air",
    "postflop_draw", "postflop_pair", "postflop_pair_draw",
    "postflop_two_pair", "postflop_trips", "postflop_straight_plus",
    "postflop_full_house_plus",
)


@dataclass(frozen=True)
class AbstractAction:
    """A bounded research action; target is always a current-street total."""

    label: str
    action_type: Literal["fold", "check", "call", "bet", "raise", "all_in"]
    target_total: int | None = None


def _straight_draw(hole_cards: tuple[str, ...], board_cards: tuple[str, ...]) -> bool:
    if len(board_cards) not in (3, 4):
        return False
    ranks = {RANK_VALUE[card[0]] for card in hole_cards + board_cards}
    hero_ranks = {RANK_VALUE[card[0]] for card in hole_cards}
    if any(sequence <= ranks and sequence & hero_ranks for sequence in STRAIGHTS):
        return False
    completions = {
        rank for rank in range(2, 15)
        if any(sequence <= ranks | {rank} and sequence & hero_ranks for sequence in STRAIGHTS)
    }
    return bool(completions)


def _flush_draw(hole_cards: tuple[str, ...], board_cards: tuple[str, ...]) -> bool:
    return len(board_cards) in (3, 4) and any(
        sum(card[1] == suit for card in hole_cards + board_cards) == 4
        and any(card[1] == suit for card in hole_cards)
        for suit in SUITS
    )


def _preflop_bucket(hole_cards: tuple[str, ...]) -> str:
    first, second = sorted(hole_cards, key=lambda card: RANK_VALUE[card[0]], reverse=True)
    high, low = RANK_VALUE[first[0]], RANK_VALUE[second[0]]
    if high == low:
        if high >= 13:
            return "preflop_premium"
        if high >= 10:
            return "preflop_strong"
        if high >= 6:
            return "preflop_medium"
        return "preflop_speculative"
    suited = first[1] == second[1]
    connected = high - low <= 2
    score = high + low / 2 + (2 if suited else 0) + (1 if connected else 0)
    if score >= 26:
        return "preflop_premium"
    if score >= 22:
        return "preflop_strong"
    if score >= 18:
        return "preflop_medium"
    if score >= 15:
        return "preflop_speculative"
    return "preflop_weak"


def card_bucket(state: DecisionState) -> str:
    """Bucket only Hero cards and the public board visible at this decision."""
    if state.street == "preflop":
        return _preflop_bucket(state.hole_cards)
    made = EVALUATOR.category(list(state.hole_cards), list(state.board_cards)).lower().replace(" ", "_")
    if made in {"full_house", "four_of_a_kind", "straight_flush", "royal_flush"}:
        return "postflop_full_house_plus"
    if made in {"straight", "flush"}:
        return "postflop_straight_plus"
    if made == "three_of_a_kind":
        return "postflop_trips"
    if made == "two_pair":
        return "postflop_two_pair"
    has_draw = _flush_draw(state.hole_cards, state.board_cards) or _straight_draw(state.hole_cards, state.board_cards)
    if made == "pair":
        return "postflop_pair_draw" if has_draw else "postflop_pair"
    return "postflop_draw" if has_draw else "postflop_air"


def _band(value: float, boundaries: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for boundary, label in zip(boundaries, labels):
        if value <= boundary:
            return label
    return labels[-1]


def _history_token(action: PublicAction, state: DecisionState) -> str:
    actor = "hero" if action.player == state.acting_player else "villain"
    if action.action not in {"bet", "raise", "all_in"} or action.amount is None:
        return f"{actor}:{action.action}"
    size_bb = action.amount / state.big_blind
    return f"{actor}:{action.action}:{_band(size_bb, (2, 5, 15), ('tiny', 'small', 'large', 'huge'))}"


def _geometry(state: DecisionState) -> dict[str, str | bool | int]:
    pot_bb = state.pot / state.big_blind
    spr = state.effective_stack / state.pot if state.pot else float("inf")
    call_fraction = state.amount_to_call / state.pot if state.pot else 0.0
    return {
        "pot_bb": _band(pot_bb, (2, 6, 20), ("small", "medium", "large", "very_large")),
        "spr": _band(spr, (1, 3, 8), ("committed", "short", "medium", "deep")),
        "call_pressure": _band(call_fraction, (0, .33, .75), ("free", "small", "large", "very_large")),
        "hero_commitment": _band(state.hero_street_commitment / state.big_blind, (0, 2, 8), ("none", "small", "large", "huge")),
        "opponent_commitment": _band(state.opponent_street_commitment / state.big_blind, (0, 2, 8), ("none", "small", "large", "huge")),
        "raises_this_street": min(state.raises_this_street, 3),
        "raising_reopened": state.raising_reopened,
    }


class HoldemAbstraction:
    """Pure mapping between visible decision states and bounded research actions."""

    @staticmethod
    def abstract_actions(state: DecisionState) -> tuple[AbstractAction, ...]:
        actions: list[AbstractAction] = []
        for action_type in ("fold", "check", "call", "all_in"):
            if action_type in state.legal_actions:
                actions.append(AbstractAction(action_type, action_type))
        aggressive = "bet" if "bet" in state.legal_actions else "raise" if "raise" in state.legal_actions else None
        if aggressive is None:
            return tuple(actions)
        minimum, maximum = state.minimum_legal_target, state.maximum_legal_target
        if minimum is None or minimum > maximum:
            return tuple(actions)
        seen_targets = set()
        for label, fraction in AGGRESSION_FRACTIONS:
            desired = state.hero_street_commitment + max(1, ceil(state.pot * fraction))
            target = min(max(desired, minimum), maximum)
            if target not in seen_targets:
                actions.append(AbstractAction(f"{aggressive}_{label}", aggressive, target))
                seen_targets.add(target)
        return tuple(actions)

    @staticmethod
    def concretize(state: DecisionState, abstract_action: AbstractAction) -> Action:
        """Return an engine action only after enforcing its legal total-target bounds."""
        if abstract_action.action_type not in state.legal_actions:
            raise ValueError(f"abstract action is not legal: {abstract_action.label}")
        if abstract_action.action_type in {"bet", "raise"}:
            target = abstract_action.target_total
            if (target is None or state.minimum_legal_target is None
                    or not state.minimum_legal_target <= target <= state.maximum_legal_target):
                raise ValueError(f"invalid total-target abstraction: {abstract_action.label}")
            return Action(abstract_action.action_type, target)
        if abstract_action.target_total is not None:
            raise ValueError(f"non-sizing abstract action has a target: {abstract_action.label}")
        return Action(abstract_action.action_type)

    @staticmethod
    def information_set(state: DecisionState) -> str:
        """Stable key containing no hidden card, future board, deck, RNG, or ID."""
        payload = {
            "street": state.street,
            "position": state.position,
            "card_bucket": card_bucket(state),
            "geometry": _geometry(state),
            "history": [_history_token(action, state) for action in state.hand_actions[-6:]],
            "legal_actions": [action.label for action in HoldemAbstraction.abstract_actions(state)],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"h4c:{sha256(canonical.encode('utf-8')).hexdigest()}"


def concrete_state_key(state: DecisionState) -> str:
    """Exact visible-state key used only as a state-space diagnostic baseline."""
    payload = {
        "street": state.street, "position": state.position,
        "hole_cards": sorted(state.hole_cards), "board_cards": list(state.board_cards),
        "pot": state.pot, "hero_stack": state.hero_stack, "opponent_stack": state.opponent_stack,
        "hero_street_commitment": state.hero_street_commitment,
        "opponent_street_commitment": state.opponent_street_commitment,
        "current_highest_bet": state.current_highest_bet,
        "amount_to_call": state.amount_to_call, "minimum_legal_target": state.minimum_legal_target,
        "maximum_legal_target": state.maximum_legal_target, "raising_reopened": state.raising_reopened,
        "history": [(action.player, action.action, action.amount) for action in state.hand_actions],
        "legal_actions": list(state.legal_actions),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
