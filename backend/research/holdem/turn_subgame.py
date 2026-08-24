"""Bounded fixed-flop / chance-turn Hold'em research game for Phase 4F.

This is deliberately not full heads-up no-limit Hold'em: it has a fixed flop,
seven-card research deck, exactly one public turn chance node, and no river.
It retains Phase 4C's visible-state abstraction and total-target actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from poker_analyzer import EVALUATOR
from simulation.decision_state import DecisionState, PublicAction

from .abstraction import AbstractAction, HoldemAbstraction


FIXED_FLOP = ("As", "Kd", "7c")
TURN_RESEARCH_DECK = ("Ah", "Ad", "Kh", "Kc", "Qs", "Js", "Ts")
STARTING_POT = 100
STACK = 100
BIG_BLIND = 10
MAX_EXACT_TREE_NODES = 150_000


@dataclass(frozen=True)
class TurnHoldemState:
    """A concrete private deal, public betting history, and optional turn.

    ``deck`` is retained solely to derive conditional physical turn outcomes.
    It is never copied into a decision state, abstract action, or infoset.
    """

    player0_cards: tuple[str, str]
    player1_cards: tuple[str, str]
    flop_history: tuple[AbstractAction, ...] = ()
    turn_card: str | None = None
    turn_history: tuple[AbstractAction, ...] = ()
    deck: tuple[str, ...] = TURN_RESEARCH_DECK

    @property
    def terminal(self) -> bool:
        if self.flop_history and self.flop_history[-1].action_type == "fold":
            return True
        # A called flop all-in cannot produce a turn decision in this bounded
        # fixture.  A normal flop call instead closes the street and reaches
        # the real public turn chance node below.
        if self.turn_card is None:
            flop_totals = self._commitments(self.flop_history, (STACK, STACK))
            return bool(self.flop_history and self.flop_history[-1].action_type == "call" and (
                any(item.action_type == "all_in" for item in self.flop_history)
                or any(total >= STACK for total in flop_totals)
            ))
        if self.turn_history and self.turn_history[-1].action_type == "fold":
            return True
        return bool(self.turn_history and self.turn_history[-1].action_type == "call") or self._street_complete(self.turn_history)

    @staticmethod
    def _street_complete(history: tuple[AbstractAction, ...]) -> bool:
        return history == (AbstractAction("check", "check"), AbstractAction("check", "check")) or (
            bool(history) and history[-1].action_type == "call"
        )

    @property
    def chance(self) -> bool:
        return not self.terminal and self.turn_card is None and self._street_complete(self.flop_history)

    @property
    def street(self) -> str:
        return "turn" if self.turn_card is not None else "flop"

    def _street_start_stacks(self) -> tuple[int, int]:
        flop = self._commitments(self.flop_history, (STACK, STACK))
        return (STACK - flop[0], STACK - flop[1])

    @staticmethod
    def _commitments(history: tuple[AbstractAction, ...], starts: tuple[int, int]) -> tuple[int, int]:
        commitments = [0, 0]
        actor = 0
        for action in history:
            if action.action_type in {"bet", "raise"}:
                assert action.target_total is not None
                commitments[actor] = action.target_total
            elif action.action_type == "all_in":
                commitments[actor] = starts[actor]
            elif action.action_type == "call":
                commitments[actor] = max(commitments)
            actor = 1 - actor
        return tuple(commitments)  # type: ignore[return-value]

    def _current_history(self) -> tuple[AbstractAction, ...]:
        return self.turn_history if self.turn_card is not None else self.flop_history

    def _current_commitments(self) -> tuple[int, int]:
        starts = self._street_start_stacks() if self.turn_card is not None else (STACK, STACK)
        return self._commitments(self._current_history(), starts)

    def _total_commitments(self) -> tuple[int, int]:
        flop = self._commitments(self.flop_history, (STACK, STACK))
        turn = self._commitments(self.turn_history, (STACK - flop[0], STACK - flop[1]))
        return (flop[0] + turn[0], flop[1] + turn[1])

    @property
    def acting_player(self) -> int | None:
        if self.terminal or self.chance:
            return None
        history = self._current_history()
        if not history:
            return 0
        last = history[-1]
        if last.action_type == "check":
            return 1 if len(history) == 1 else None
        if last.action_type in {"bet", "raise", "all_in"}:
            return 1 - ((len(history) - 1) % 2)
        return None

    def _legal_types(self) -> tuple[str, ...]:
        history = self._current_history()
        if not history or history == (AbstractAction("check", "check"),):
            return ("check", "bet", "all_in")
        commitments = self._current_commitments()
        actor = self.acting_player
        assert actor is not None
        facing = commitments[actor] < max(commitments)
        if not facing:
            return ("check", "bet", "all_in")
        starts = self._street_start_stacks() if self.turn_card is not None else (STACK, STACK)
        return ("fold", "call", "all_in") if max(commitments) < starts[actor] else ("fold", "call")

    def _public_actions(self) -> tuple[PublicAction, ...]:
        result: list[PublicAction] = []
        for history, starts in (
            (self.flop_history, (STACK, STACK)),
            (self.turn_history, self._street_start_stacks()),
        ):
            actor = 0
            for item in history:
                amount = starts[actor] if item.action_type == "all_in" else item.target_total
                result.append(PublicAction(str(actor), item.action_type, amount))
                actor = 1 - actor
        return tuple(result)

    def decision_state(self, player: int | None = None) -> DecisionState:
        actor = self.acting_player if player is None else player
        if actor is None:
            raise ValueError(f"chance and terminal states have no decision state: {self}")
        commits = self._current_commitments()
        totals = self._total_commitments()
        starts = self._street_start_stacks() if self.turn_card is not None else (STACK, STACK)
        opponent = 1 - actor
        legal = self._legal_types()
        highest = max(commits)
        maximum = starts[actor]
        can_normal_bet = "bet" in legal
        minimum = BIG_BLIND if highest == 0 else highest + max(BIG_BLIND, highest)
        if minimum > maximum or not can_normal_bet:
            minimum = None
        actions = self._public_actions()
        cards = self.player0_cards if actor == 0 else self.player1_cards
        board = FIXED_FLOP if self.turn_card is None else FIXED_FLOP + (self.turn_card,)
        return DecisionState(
            hand_id="phase-4f-turn-chance", match_id=None, hand_number=1,
            acting_player=str(actor), opponent=str(opponent), street=self.street,
            button_player="1", small_blind_player="1", big_blind_player="0",
            position="out_of_position" if actor == 0 else "in_position",
            hole_cards=cards, board_cards=board,
            hero_stack=STACK - totals[actor], opponent_stack=STACK - totals[opponent],
            effective_stack=min(STACK - totals[actor], STACK - totals[opponent]),
            pot=STARTING_POT + sum(totals), small_blind=5, big_blind=BIG_BLIND,
            effective_stack_bb=min(STACK - totals[actor], STACK - totals[opponent]) / BIG_BLIND,
            hero_street_commitment=commits[actor], opponent_street_commitment=commits[opponent],
            current_highest_bet=highest, amount_to_call=highest - commits[actor],
            minimum_legal_target=minimum, maximum_legal_target=maximum,
            legal_actions=legal, last_full_raise_size=max(BIG_BLIND, highest), raising_reopened=True,
            current_street_actions=actions[-len(self._current_history()):], hand_actions=actions,
            last_aggressor=str((len(self._current_history()) - 1) % 2) if highest else None,
            preflop_aggressor=None,
            raises_this_street=sum(item.action_type in {"bet", "raise"} for item in self._current_history()),
            hero_has_initiative=bool(highest and (len(self._current_history()) - 1) % 2 == actor),
        )

    @property
    def legal_actions(self) -> tuple[AbstractAction, ...]:
        if self.chance or self.terminal:
            return ()
        return HoldemAbstraction.abstract_actions(self.decision_state())

    def apply(self, action: AbstractAction) -> "TurnHoldemState":
        if action not in self.legal_actions:
            raise ValueError(f"illegal abstract action: {action.label}")
        if self.turn_card is None:
            return TurnHoldemState(self.player0_cards, self.player1_cards, self.flop_history + (action,), None, (), self.deck)
        return TurnHoldemState(self.player0_cards, self.player1_cards, self.flop_history, self.turn_card, self.turn_history + (action,), self.deck)

    def remaining_turn_cards(self) -> tuple[str, ...]:
        used = set(FIXED_FLOP) | set(self.player0_cards) | set(self.player1_cards)
        cards = tuple(card for card in self.deck if card not in used)
        if len(cards) != len(set(cards)) or used & set(cards):
            raise AssertionError("invalid physical turn card removal")
        return cards

    def chance_outcomes(self) -> tuple[tuple[str, "TurnHoldemState", float], ...]:
        if not self.chance:
            raise ValueError("turn outcomes requested outside the turn chance node")
        cards = self.remaining_turn_cards()
        probability = 1.0 / len(cards)
        return tuple((card, TurnHoldemState(
            self.player0_cards, self.player1_cards, self.flop_history, card, (), self.deck,
        ), probability) for card in cards)

    def information_set(self) -> str:
        return HoldemAbstraction.information_set(self.decision_state())

    def utility_p0(self) -> float:
        if not self.terminal:
            raise ValueError("utility requested from nonterminal state")
        totals = self._total_commitments()
        final_history = self.turn_history if self.turn_history else self.flop_history
        if final_history[-1].action_type == "fold":
            folder = (len(final_history) - 1) % 2
            return float(-STARTING_POT / 2 - totals[0]) if folder == 0 else float(STARTING_POT / 2 + totals[1])
        # A flop all-in call is terminal in this deliberately bounded game;
        # it does not create a player decision or sampled turn branch.
        board = FIXED_FLOP if self.turn_card is None else FIXED_FLOP + (self.turn_card,)
        p0_score = EVALUATOR.score(list(self.player0_cards), list(board))
        p1_score = EVALUATOR.score(list(self.player1_cards), list(board))
        if p0_score == p1_score:
            return float((totals[1] - totals[0]) / 2)
        return float(STARTING_POT / 2 + totals[1]) if p0_score < p1_score else float(-STARTING_POT / 2 - totals[0])

    def utility(self, player: int) -> float:
        if player not in (0, 1):
            raise ValueError("player must be 0 or 1")
        return self.utility_p0() if player == 0 else -self.utility_p0()


def turn_chance_states(deck: Iterable[str] = TURN_RESEARCH_DECK) -> tuple[TurnHoldemState, ...]:
    """Enumerate collision-free unordered private deals before the flop."""
    cards = tuple(deck)
    if len(cards) < 6 or len(set(cards)) != len(cards) or set(cards) & set(FIXED_FLOP):
        raise ValueError("deck needs at least six unique cards disjoint from the fixed flop")
    outcomes = []
    for p0 in combinations(cards, 2):
        remaining = tuple(card for card in cards if card not in p0)
        outcomes.extend(TurnHoldemState(p0, p1, deck=cards) for p1 in combinations(remaining, 2))
    return tuple(outcomes)


def turn_subgame_convention() -> dict[str, object]:
    return {
        "name": "phase-4f-fixed-flop-turn-chance-abstract-subgame",
        "scope": "bounded two-street research game, not full heads-up no-limit Hold'em",
        "fixed_flop": list(FIXED_FLOP), "private_card_deck": list(TURN_RESEARCH_DECK),
        "starting_pot": STARTING_POT, "remaining_stack_each": STACK,
        "position": "Player 0 is out of position and acts first on both flop and turn; Player 1 is button/in position",
        "flop_actions": "Phase 4C fold/check/call/all-in plus legal 50%, 75%, 125%-pot total-target bets",
        "turn_actions": "the same Phase 4C action set with street-local total targets and remaining stacks",
        "maximum_raises": "one all-in response; normal reraises are not included in this bounded action tree",
        "turn_chance": "after a completed non-all-in flop round, enumerate only deck cards not on fixed flop or either private hand, uniformly",
        "exact_controls": "enumerate every legal remaining turn card; MCCFR samples exactly one conditional turn card with its dedicated RNG",
        "terminal_payoff": "zero-sum Player 0 net chip change from subgame start; folds settle immediately, turn showdowns use fixed flop plus turn, and a flop all-in call terminates on the fixed-flop fixture without a turn decision",
        "river": "absent",
    }
