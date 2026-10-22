"""Deterministic, privacy-safe strategy inputs derived from ``HandEngine``.

This module deliberately reads authoritative engine state; it does not recreate
betting rules or inspect hidden deck information.  It is an internal boundary
for future strategy implementations, not a public API or dataset schema.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Literal

from poker_analyzer import EVALUATOR, RANK_VALUE, STRAIGHTS, SUITS

from .actions import ActionType


Position = Literal["in_position", "out_of_position"]


@dataclass(frozen=True)
class PublicAction:
    player: str
    action: str
    amount: int | None = None


@dataclass(frozen=True)
class DecisionState:
    hand_id: str
    match_id: str | None
    hand_number: int
    acting_player: str
    opponent: str
    street: str
    button_player: str
    small_blind_player: str
    big_blind_player: str
    position: Position
    hole_cards: tuple[str, ...]
    board_cards: tuple[str, ...]
    hero_stack: int
    opponent_stack: int
    effective_stack: int
    pot: int
    small_blind: int
    big_blind: int
    effective_stack_bb: float
    hero_street_commitment: int
    opponent_street_commitment: int
    current_highest_bet: int
    amount_to_call: int
    minimum_legal_target: int | None
    maximum_legal_target: int
    legal_actions: tuple[ActionType, ...]
    last_full_raise_size: int
    raising_reopened: bool
    current_street_actions: tuple[PublicAction, ...]
    hand_actions: tuple[PublicAction, ...]
    last_aggressor: str | None
    preflop_aggressor: str | None
    raises_this_street: int
    hero_has_initiative: bool

    def as_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class PokerFeatureSet:
    pot_odds: float
    call_price: int
    required_equity: float
    stack_to_pot_ratio: float
    effective_stack_bb: float
    bet_faced_fraction_of_pot: float
    is_button: bool
    position: Position
    is_preflop: bool
    is_postflop: bool
    made_hand: str
    has_pair: bool
    has_two_pair: bool
    has_trips: bool
    has_straight: bool
    has_flush: bool
    has_full_house: bool
    has_quads: bool
    has_straight_flush: bool
    flush_draw: bool
    open_ended_straight_draw: bool
    gutshot: bool
    overcards: bool
    pair_plus_draw: bool
    paired_board: bool
    monotone_board: bool
    two_tone_board: bool
    rainbow_board: bool
    connected_board: bool
    board_high_card_rank: str | None
    board_distinct_ranks: int
    board_distinct_suits: int

    def as_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class EquityEstimate:
    estimated_equity: float
    iterations: int
    method: str
    confidence: dict[str, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class DecisionObservation:
    """The complete normalized input available to a strategy at one decision."""

    decision_state: DecisionState
    poker_features: PokerFeatureSet
    equity: EquityEstimate | None = None
    opponent_profile: Any | None = None
    # Explicit opt-in infrastructure: construction remains cheap and legacy
    # Expert/Adaptive behavior deliberately ignores these Phase 3D2 fields.
    opponent_range_summary: Any | None = None
    range_equity: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _public_actions(engine) -> tuple[PublicAction, ...]:
    """Normalize engine-emitted public actions using total-target semantics."""
    return tuple(
        PublicAction(event.actor, event.applied_action, event.target_total)
        for event in engine.history.events
        if event.event_type == "action_taken"
        and event.actor in {"a", "b"}
        and event.applied_action in {"fold", "check", "call", "bet", "raise", "all_in"}
    )


def _street_actions(engine, actions: tuple[PublicAction, ...]) -> tuple[PublicAction, ...]:
    # GameState resets commitments at each street.  History is authoritative
    # for street boundaries, while action_history intentionally remains public.
    boundary = 0
    for event in engine.history.events:
        if event.event_type == "street_started" and event.street == engine.state.street:
            boundary = sum(
                1
                for prior in engine.history.events[: event.event_index]
                if prior.event_type == "action_taken" and prior.applied_action != "illegal_action"
            )
    return actions[boundary:]


def _aggressor(actions: tuple[PublicAction, ...]) -> str | None:
    aggressive = [item.player for item in actions if item.action in {"bet", "raise", "all_in"}]
    return aggressive[-1] if aggressive else None


def build_decision_state(engine, player: str) -> DecisionState:
    """Build a state solely from engine information legitimately visible to player."""
    opponent = engine.other(player)
    call = engine.state.current_highest_bet - engine.state.current_bets[player]
    maximum = engine.state.current_bets[player] + engine.state.stacks[player]
    can_increase = maximum > engine.state.current_highest_bet and engine.state.raising_reopened[player]
    minimum = (
        engine.bb if engine.state.current_highest_bet == 0 else engine.state.current_highest_bet + engine.state.last_full_raise_size
    ) if can_increase else None
    actions = _public_actions(engine)
    street_actions = _street_actions(engine, actions)
    preflop_actions = tuple(
        PublicAction(event.actor, event.applied_action, event.target_total)
        for event in engine.history.events
        if event.event_type == "action_taken" and event.street == "preflop" and event.actor and event.applied_action
    )
    last_aggressor = _aggressor(actions)
    preflop_aggressor = _aggressor(preflop_actions)
    effective = min(engine.state.stacks[player], engine.state.stacks[opponent])
    return DecisionState(
        hand_id=engine.state.hand_id, match_id=engine.history.match_id,
        hand_number=engine.hand_number, acting_player=player, opponent=opponent,
        street=engine.state.street, button_player=engine.state.button_player,
        small_blind_player=engine.state.button_player, big_blind_player=opponent if engine.state.button_player == player else player,
        position="in_position" if player == engine.state.button_player else "out_of_position",
        hole_cards=tuple(engine.holes[player]), board_cards=tuple(engine.state.community_cards),
        hero_stack=engine.state.stacks[player], opponent_stack=engine.state.stacks[opponent],
        effective_stack=effective, pot=engine.state.pot, small_blind=engine.sb, big_blind=engine.bb,
        effective_stack_bb=effective / engine.bb, hero_street_commitment=engine.state.current_bets[player],
        opponent_street_commitment=engine.state.current_bets[opponent], current_highest_bet=engine.state.current_highest_bet,
        amount_to_call=call, minimum_legal_target=minimum, maximum_legal_target=maximum,
        legal_actions=tuple(engine.legal(player)), last_full_raise_size=engine.state.last_full_raise_size,
        raising_reopened=engine.state.raising_reopened[player], current_street_actions=street_actions,
        hand_actions=actions, last_aggressor=last_aggressor, preflop_aggressor=preflop_aggressor,
        raises_this_street=sum(action.action in {"raise", "bet"} for action in street_actions),
        hero_has_initiative=last_aggressor == player,
    )


def _straight_draws(hole_cards: tuple[str, ...], board_cards: tuple[str, ...]) -> tuple[bool, bool]:
    if len(board_cards) not in (3, 4):
        return False, False
    ranks = {RANK_VALUE[card[0]] for card in hole_cards + board_cards}
    hero_ranks = {RANK_VALUE[card[0]] for card in hole_cards}
    if any(sequence <= ranks and sequence & hero_ranks for sequence in STRAIGHTS):
        return False, False
    completions = {
        candidate for candidate in range(2, 15)
        if any(sequence <= ranks | {candidate} and sequence & hero_ranks for sequence in STRAIGHTS)
    }
    return len(completions) == 2, len(completions) == 1


def build_poker_features(state: DecisionState) -> PokerFeatureSet:
    """Compute deterministic features. Pot odds = call / (pot + call)."""
    call = state.amount_to_call
    pot_odds = 0.0 if call == 0 else call / (state.pot + call) if state.pot + call else 0.0
    spr = state.effective_stack / state.pot if state.pot else 0.0
    faced = call / state.pot if state.pot else 0.0
    made = "preflop" if not state.board_cards else EVALUATOR.category(list(state.hole_cards), list(state.board_cards)).lower().replace(" ", "_")
    # Treys exposes the royal flush as a display sub-category. Strategy inputs
    # intentionally use the canonical made-hand taxonomy requested here.
    if made == "royal_flush":
        made = "straight_flush"
    flags = {
        "pair": made == "pair", "two_pair": made == "two_pair", "trips": made == "three_of_a_kind",
        "straight": made == "straight", "flush": made == "flush", "full_house": made == "full_house",
        "quads": made == "four_of_a_kind", "straight_flush": made == "straight_flush",
    }
    flush_draw = len(state.board_cards) in (3, 4) and any(
        sum(card[1] == suit for card in state.hole_cards + state.board_cards) == 4
        and any(card[1] == suit for card in state.hole_cards)
        for suit in SUITS
    )
    oesd, gutshot = _straight_draws(state.hole_cards, state.board_cards)
    ranks = [RANK_VALUE[card[0]] for card in state.board_cards]
    suits = {card[1] for card in state.board_cards}
    rank_counts = {rank: ranks.count(rank) for rank in set(ranks)}
    connected = any(max(window) - min(window) <= 4 for window in __import__("itertools").combinations(sorted(set(ranks)), min(3, len(set(ranks))))) if len(set(ranks)) >= 3 else False
    overcards = bool(ranks) and any(RANK_VALUE[card[0]] > max(ranks) for card in state.hole_cards)
    return PokerFeatureSet(
        pot_odds=pot_odds, call_price=call, required_equity=pot_odds, stack_to_pot_ratio=spr,
        effective_stack_bb=state.effective_stack_bb, bet_faced_fraction_of_pot=faced,
        is_button=state.acting_player == state.button_player, position=state.position,
        is_preflop=state.street == "preflop", is_postflop=state.street in {"flop", "turn", "river"},
        made_hand=made, has_pair=flags["pair"], has_two_pair=flags["two_pair"], has_trips=flags["trips"],
        has_straight=flags["straight"], has_flush=flags["flush"], has_full_house=flags["full_house"],
        has_quads=flags["quads"], has_straight_flush=flags["straight_flush"], flush_draw=flush_draw,
        open_ended_straight_draw=oesd, gutshot=gutshot, overcards=overcards,
        pair_plus_draw=flags["pair"] and (flush_draw or oesd or gutshot),
        paired_board=any(count >= 2 for count in rank_counts.values()), monotone_board=len(suits) == 1 and bool(suits),
        two_tone_board=len(suits) == 2, rainbow_board=len(suits) == len(state.board_cards) and bool(suits),
        connected_board=connected, board_high_card_rank=max(state.board_cards, key=lambda card: RANK_VALUE[card[0]])[0] if ranks else None,
        board_distinct_ranks=len(rank_counts), board_distinct_suits=len(suits),
    )


def build_decision_observation(engine, player: str, equity: EquityEstimate | None = None, opponent_profile: Any | None = None, opponent_range_summary: Any | None = None, range_equity: Any | None = None) -> DecisionObservation:
    state = build_decision_state(engine, player)
    return DecisionObservation(state, build_poker_features(state), equity, opponent_profile, opponent_range_summary, range_equity)
