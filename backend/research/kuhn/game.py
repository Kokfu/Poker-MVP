"""Canonical three-card Kuhn Poker, independent from the Hold'em engine.

Terminal utility is always from Player 0's perspective.  Both players ante one;
therefore a check/check showdown is +/-1 and a bet/call showdown is +/-2.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import permutations


class Card(str, Enum):
    J = "J"
    Q = "Q"
    K = "K"


class Action(str, Enum):
    CHECK = "check"
    BET = "bet"
    CALL = "call"
    FOLD = "fold"


DEALS: tuple[tuple[Card, Card], ...] = tuple(permutations(Card, 2))
TERMINAL_HISTORIES = {"check-check", "bet-fold", "bet-call", "check-bet-fold", "check-bet-call"}


@dataclass(frozen=True, slots=True)
class KuhnState:
    cards: tuple[Card, Card]
    history: tuple[Action, ...] = ()

    @property
    def history_key(self) -> str:
        return "-".join(action.value for action in self.history)

    @property
    def terminal(self) -> bool:
        return self.history_key in TERMINAL_HISTORIES

    @property
    def acting_player(self) -> int | None:
        if self.terminal:
            return None
        return 0 if self.history in ((), (Action.CHECK, Action.BET)) else 1

    @property
    def legal_actions(self) -> tuple[Action, ...]:
        if self.terminal:
            return ()
        if self.history in ((), (Action.CHECK,)):
            return (Action.CHECK, Action.BET)
        return (Action.FOLD, Action.CALL)

    def apply(self, action: Action) -> "KuhnState":
        if action not in self.legal_actions:
            raise ValueError(f"illegal Kuhn action {action.value} after {self.history_key!r}")
        return KuhnState(self.cards, self.history + (action,))

    def information_set(self, player: int | None = None) -> str:
        player = self.acting_player if player is None else player
        if player not in (0, 1):
            raise ValueError("information sets exist only at non-terminal decision states")
        # Deliberately excludes cards[1 - player], the hidden opposing card.
        return f"{self.cards[player].value}|{self.history_key}"

    def utility_p0(self) -> float:
        if not self.terminal:
            raise ValueError("utility is defined only for terminal Kuhn states")
        history = self.history_key
        if history in ("bet-fold", "check-bet-fold"):
            bettor = 0 if history == "bet-fold" else 1
            return 1.0 if bettor == 0 else -1.0
        winner = 0 if self.cards[0] > self.cards[1] else 1
        magnitude = 1.0 if history == "check-check" else 2.0
        return magnitude if winner == 0 else -magnitude
