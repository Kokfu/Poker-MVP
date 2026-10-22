"""A bounded, fixed-flop Hold'em research game for Phase 4D.

This is explicitly *not* full heads-up no-limit Hold'em.  Chance deals two
private cards to each player from a six-card research deck, the flop is fixed,
and there are no turn or river cards.  The only betting street is that flop.
All public decisions are converted through the accepted Phase 4C abstraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from poker_analyzer import EVALUATOR
from simulation.decision_state import DecisionState, PublicAction

from .abstraction import AbstractAction, HoldemAbstraction


FIXED_BOARD = ("As", "Kd", "7c")
RESEARCH_DECK = ("Ah", "Ad", "Kh", "Kc", "Qs", "Js")
STARTING_POT = 100
STACK = 100
BIG_BLIND = 10


@dataclass(frozen=True)
class HoldemSubgameState:
    """One concrete chance outcome and public flop-betting history."""

    player0_cards: tuple[str, str]
    player1_cards: tuple[str, str]
    history: tuple[AbstractAction, ...] = ()

    @property
    def acting_player(self) -> int | None:
        if self.terminal:
            return None
        if not self.history:
            return 0
        last = self.history[-1]
        if last.action_type == "check":
            return 1 if len(self.history) == 1 else None
        if last.action_type in {"bet", "raise", "all_in"}:
            return 1 - ((len(self.history) - 1) % 2)
        return None

    @property
    def terminal(self) -> bool:
        if not self.history:
            return False
        if self.history[-1].action_type == "fold":
            return True
        if self.history == (AbstractAction("check", "check"), AbstractAction("check", "check")):
            return True
        wagered = any(action.action_type in {"bet", "raise", "all_in"} for action in self.history)
        return wagered and self.history[-1].action_type == "call"

    def _commitments(self) -> tuple[int, int]:
        commitments = [0, 0]
        actor = 0
        for action in self.history:
            if action.action_type in {"bet", "raise"}:
                assert action.target_total is not None
                commitments[actor] = action.target_total
            elif action.action_type == "all_in":
                commitments[actor] = STACK
            elif action.action_type == "call":
                commitments[actor] = max(commitments)
            actor = 1 - actor
        return tuple(commitments)  # type: ignore[return-value]

    def _legal_types(self) -> tuple[str, ...]:
        if not self.history or self.history == (AbstractAction("check", "check"),):
            return ("check", "bet", "all_in")
        commits = self._commitments()
        actor = self.acting_player
        assert actor is not None
        facing = commits[actor] < max(commits)
        if not facing:
            return ("check", "bet", "all_in")
        # An all-in is a legal short/full raise whenever chips remain beyond a call.
        return ("fold", "call", "all_in") if max(commits) < STACK else ("fold", "call")

    def decision_state(self, player: int | None = None) -> DecisionState:
        """Create the Phase 4C input using only this player's visible cards."""
        actor = self.acting_player if player is None else player
        if actor is None:
            raise ValueError("terminal states have no decision state")
        commits = self._commitments()
        opponent = 1 - actor
        legal = self._legal_types()
        highest = max(commits)
        maximum = STACK
        can_normal_raise = "bet" in legal or ("all_in" in legal and highest + max(1, highest) <= STACK)
        minimum = BIG_BLIND if highest == 0 else highest + max(BIG_BLIND, highest)
        if minimum > maximum or not can_normal_raise:
            minimum = None
        actions = tuple(
            PublicAction(str(index % 2), item.action_type, item.target_total if item.action_type != "all_in" else STACK)
            for index, item in enumerate(self.history)
        )
        cards = self.player0_cards if actor == 0 else self.player1_cards
        return DecisionState(
            hand_id="phase-4d-fixed-flop", match_id=None, hand_number=1,
            acting_player=str(actor), opponent=str(opponent), street="flop",
            button_player="1", small_blind_player="1", big_blind_player="0",
            position="out_of_position" if actor == 0 else "in_position",
            hole_cards=cards, board_cards=FIXED_BOARD,
            hero_stack=STACK - commits[actor], opponent_stack=STACK - commits[opponent],
            effective_stack=min(STACK - commits[actor], STACK - commits[opponent]), pot=STARTING_POT + sum(commits),
            small_blind=5, big_blind=BIG_BLIND, effective_stack_bb=min(STACK - commits[actor], STACK - commits[opponent]) / BIG_BLIND,
            hero_street_commitment=commits[actor], opponent_street_commitment=commits[opponent],
            current_highest_bet=highest, amount_to_call=highest - commits[actor],
            minimum_legal_target=minimum, maximum_legal_target=maximum,
            legal_actions=legal, last_full_raise_size=max(BIG_BLIND, highest),
            raising_reopened=True, current_street_actions=actions, hand_actions=actions,
            last_aggressor=str((len(self.history) - 1) % 2) if highest else None,
            preflop_aggressor=None, raises_this_street=sum(item.action_type in {"bet", "raise"} for item in self.history),
            hero_has_initiative=bool(highest and (len(self.history) - 1) % 2 == actor),
        )

    @property
    def legal_actions(self) -> tuple[AbstractAction, ...]:
        return HoldemAbstraction.abstract_actions(self.decision_state())

    def apply(self, action: AbstractAction) -> "HoldemSubgameState":
        if action not in self.legal_actions:
            raise ValueError(f"illegal abstract action: {action.label}")
        return HoldemSubgameState(self.player0_cards, self.player1_cards, self.history + (action,))

    def information_set(self) -> str:
        return HoldemAbstraction.information_set(self.decision_state())

    def utility_p0(self) -> float:
        """Net chip change from the start of the fixed-flop subgame."""
        if not self.terminal:
            raise ValueError("utility requested from nonterminal state")
        commits = self._commitments()
        if self.history[-1].action_type == "fold":
            folder = (len(self.history) - 1) % 2
            return float(-STARTING_POT / 2 - commits[0]) if folder == 0 else float(STARTING_POT / 2 + commits[1])
        p0_score = EVALUATOR.score(list(self.player0_cards), list(FIXED_BOARD))
        p1_score = EVALUATOR.score(list(self.player1_cards), list(FIXED_BOARD))
        if p0_score == p1_score:
            return float((commits[1] - commits[0]) / 2)
        p0_wins = p0_score < p1_score
        return float(STARTING_POT / 2 + commits[1]) if p0_wins else float(-STARTING_POT / 2 - commits[0])

    def utility(self, player: int) -> float:
        if player not in (0, 1):
            raise ValueError("player must be 0 or 1")
        return self.utility_p0() if player == 0 else -self.utility_p0()


def chance_states(deck: Iterable[str] = RESEARCH_DECK) -> tuple[HoldemSubgameState, ...]:
    """Deterministically enumerate all disjoint unordered two-card private deals."""
    cards = tuple(deck)
    if len(cards) < 4 or len(set(cards)) != len(cards) or set(cards) & set(FIXED_BOARD):
        raise ValueError("research deck must contain unique cards disjoint from the fixed board")
    outcomes = []
    for p0 in combinations(cards, 2):
        remaining = tuple(card for card in cards if card not in p0)
        outcomes.extend(HoldemSubgameState(p0, p1) for p1 in combinations(remaining, 2))
    return tuple(outcomes)


def subgame_convention() -> dict[str, object]:
    return {
        "name": "phase-4d-fixed-flop-abstract-subgame",
        "starting_street": "flop", "public_board": list(FIXED_BOARD), "future_cards": False,
        "starting_pot": STARTING_POT, "remaining_stack_each": STACK,
        "chance": "exact deterministic enumeration of disjoint two-card private deals from the six-card research deck",
        "actions": "Phase 4C fold/check/call/all-in and its legal 50%, 75%, 125%-pot bet/raise representatives",
        "payoff": "zero-sum net chip change from the subgame start; showdown is evaluated on the fixed flop",
        "information": "own two cards, fixed public flop, public abstract betting history and visible stack/pot geometry only",
    }
