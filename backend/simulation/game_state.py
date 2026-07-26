from dataclasses import dataclass, field
from typing import Literal
from .actions import ActionType

Street = Literal["preflop", "flop", "turn", "river", "showdown", "complete"]
@dataclass
class Observation:
    hand_id: str; player: str; position: str; street: Street; hole_cards: list[str]; community_cards: list[str]
    pot: int; hero_stack: int; opponent_stack: int; current_bet: int; amount_to_call: int; minimum_raise: int; minimum_target_to: int | None; maximum_target_to: int; all_in_target_to: int
    legal_actions: list[ActionType]; action_history: list[dict]
@dataclass
class GameState:
    hand_id: str; button_player: str; acting_player: str; street: Street = "preflop"; community_cards: list[str] = field(default_factory=list)
    pot: int = 0; stacks: dict[str, int] = field(default_factory=dict); current_bets: dict[str, int] = field(default_factory=dict)
    amount_to_call: int = 0; minimum_raise: int = 100; legal_actions: list[ActionType] = field(default_factory=list); action_history: list[dict] = field(default_factory=list)
    current_highest_bet: int = 0; last_full_raise_size: int = 100; pending_players: set[str] = field(default_factory=set)
    acted_since_full_raise: dict[str, bool] = field(default_factory=dict); raising_reopened: dict[str, bool] = field(default_factory=dict)
