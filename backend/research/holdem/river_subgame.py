"""Bounded fixed-flop / turn-chance / river-chance research game (Phase 4G)."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from poker_analyzer import EVALUATOR
from simulation.decision_state import DecisionState, PublicAction
from .abstraction import AbstractAction, HoldemAbstraction

FIXED_FLOP = ("As", "Kd", "7c")
RIVER_RESEARCH_DECK = ("Ah", "Ad", "Kh", "Kc", "Qs", "Js", "Ts")
STARTING_POT, STACK, BIG_BLIND = 100, 100, 10
# This is a measured-tree safety ceiling, not a claim that this is a full game.
MAX_EXACT_TREE_NODES = 2_000_000


@dataclass(frozen=True)
class RiverHoldemState:
    """Private deal plus visible public history; deck is never an infoset input."""
    player0_cards: tuple[str, str]
    player1_cards: tuple[str, str]
    flop_history: tuple[AbstractAction, ...] = ()
    turn_card: str | None = None
    turn_history: tuple[AbstractAction, ...] = ()
    river_card: str | None = None
    river_history: tuple[AbstractAction, ...] = ()
    deck: tuple[str, ...] = RIVER_RESEARCH_DECK

    @staticmethod
    def _complete(history: tuple[AbstractAction, ...]) -> bool:
        return history == (AbstractAction("check", "check"), AbstractAction("check", "check")) or bool(history and history[-1].action_type == "call")

    @staticmethod
    def _commitments(history: tuple[AbstractAction, ...], starts: tuple[int, int]) -> tuple[int, int]:
        result = [0, 0]; actor = 0
        for action in history:
            if action.action_type in {"bet", "raise"}: result[actor] = action.target_total  # type: ignore[assignment]
            elif action.action_type == "all_in": result[actor] = starts[actor]
            elif action.action_type == "call": result[actor] = max(result)
            actor = 1 - actor
        return tuple(result)  # type: ignore[return-value]

    def _flop_totals(self): return self._commitments(self.flop_history, (STACK, STACK))
    def _turn_starts(self):
        totals = self._flop_totals(); return (STACK - totals[0], STACK - totals[1])
    def _turn_totals(self): return self._commitments(self.turn_history, self._turn_starts())
    def _river_starts(self):
        f, t = self._flop_totals(), self._turn_totals(); return (STACK - f[0] - t[0], STACK - f[1] - t[1])

    @property
    def terminal(self) -> bool:
        for history in (self.flop_history, self.turn_history, self.river_history):
            if history and history[-1].action_type == "fold": return True
        # An all-in called before a future street ends the bounded game.
        if self.turn_card is None:
            totals = self._flop_totals()
            return bool(self.flop_history and self.flop_history[-1].action_type == "call" and (any(a.action_type == "all_in" for a in self.flop_history) or any(total >= STACK for total in totals)))
        if self.river_card is None:
            totals, starts = self._turn_totals(), self._turn_starts()
            return bool(self.turn_history and self.turn_history[-1].action_type == "call" and (any(a.action_type == "all_in" for a in self.turn_history) or any(total >= start for total, start in zip(totals, starts))))
        return self._complete(self.river_history)

    @property
    def chance(self) -> bool:
        return not self.terminal and ((self.turn_card is None and self._complete(self.flop_history)) or (self.turn_card is not None and self.river_card is None and self._complete(self.turn_history)))

    @property
    def chance_stage(self) -> str:
        """Public street that this chance node is about to reveal."""
        if not self.chance: raise ValueError("non-chance state has no chance stage")
        return "turn" if self.turn_card is None else "river"

    @property
    def street(self) -> str:
        return "flop" if self.turn_card is None else "turn" if self.river_card is None else "river"

    def _current_history(self): return self.flop_history if self.street == "flop" else self.turn_history if self.street == "turn" else self.river_history
    def _current_starts(self): return (STACK, STACK) if self.street == "flop" else self._turn_starts() if self.street == "turn" else self._river_starts()
    def _current_commitments(self): return self._commitments(self._current_history(), self._current_starts())
    def _total_commitments(self):
        f, t = self._flop_totals(), self._turn_totals(); r = self._commitments(self.river_history, self._river_starts())
        return (f[0] + t[0] + r[0], f[1] + t[1] + r[1])

    @property
    def acting_player(self) -> int | None:
        if self.terminal or self.chance: return None
        history = self._current_history()
        if not history: return 0
        last = history[-1]
        if last.action_type == "check": return 1 if len(history) == 1 else None
        return 1 - ((len(history) - 1) % 2) if last.action_type in {"bet", "raise", "all_in"} else None

    def _legal_types(self):
        history, commits, starts = self._current_history(), self._current_commitments(), self._current_starts()
        if not history or history == (AbstractAction("check", "check"),): return ("check", "bet", "all_in")
        actor = self.acting_player; assert actor is not None
        return (("fold", "call", "all_in") if max(commits) < starts[actor] else ("fold", "call")) if commits[actor] < max(commits) else ("check", "bet", "all_in")

    def _public_actions(self):
        result: list[PublicAction] = []
        for history, starts in ((self.flop_history, (STACK, STACK)), (self.turn_history, self._turn_starts()), (self.river_history, self._river_starts())):
            actor = 0
            for action in history:
                result.append(PublicAction(str(actor), action.action_type, starts[actor] if action.action_type == "all_in" else action.target_total)); actor = 1 - actor
        return tuple(result)

    def decision_state(self, player: int | None = None) -> DecisionState:
        actor = self.acting_player if player is None else player
        if actor is None: raise ValueError("chance and terminal states have no decision state")
        commits, totals, starts = self._current_commitments(), self._total_commitments(), self._current_starts(); highest = max(commits)
        legal = self._legal_types(); minimum = BIG_BLIND if highest == 0 else highest + max(BIG_BLIND, highest)
        if minimum > starts[actor] or "bet" not in legal: minimum = None
        board = FIXED_FLOP + (() if self.turn_card is None else (self.turn_card,)) + (() if self.river_card is None else (self.river_card,))
        actions = self._public_actions(); current = self._current_history()
        return DecisionState(hand_id="phase-4g-river-chance", match_id=None, hand_number=1, acting_player=str(actor), opponent=str(1-actor), street=self.street, button_player="1", small_blind_player="1", big_blind_player="0", position="out_of_position" if actor == 0 else "in_position", hole_cards=self.player0_cards if actor == 0 else self.player1_cards, board_cards=board, hero_stack=STACK-totals[actor], opponent_stack=STACK-totals[1-actor], effective_stack=min(STACK-totals[0], STACK-totals[1]), pot=STARTING_POT+sum(totals), small_blind=5, big_blind=BIG_BLIND, effective_stack_bb=min(STACK-totals[0], STACK-totals[1])/BIG_BLIND, hero_street_commitment=commits[actor], opponent_street_commitment=commits[1-actor], current_highest_bet=highest, amount_to_call=highest-commits[actor], minimum_legal_target=minimum, maximum_legal_target=starts[actor], legal_actions=legal, last_full_raise_size=max(BIG_BLIND, highest), raising_reopened=True, current_street_actions=actions[-len(current):], hand_actions=actions, last_aggressor=str((len(current)-1)%2) if highest else None, preflop_aggressor=None, raises_this_street=sum(a.action_type in {"bet", "raise"} for a in current), hero_has_initiative=False)

    @property
    def legal_actions(self): return () if self.terminal or self.chance else HoldemAbstraction.abstract_actions(self.decision_state())
    def apply(self, action):
        if action not in self.legal_actions: raise ValueError(f"illegal abstract action: {action.label}")
        if self.street == "flop": return RiverHoldemState(self.player0_cards, self.player1_cards, self.flop_history+(action,), None, (), None, (), self.deck)
        if self.street == "turn": return RiverHoldemState(self.player0_cards, self.player1_cards, self.flop_history, self.turn_card, self.turn_history+(action,), None, (), self.deck)
        return RiverHoldemState(self.player0_cards, self.player1_cards, self.flop_history, self.turn_card, self.turn_history, self.river_card, self.river_history+(action,), self.deck)

    def remaining_turn_cards(self):
        used = set(FIXED_FLOP) | set(self.player0_cards) | set(self.player1_cards); cards = tuple(c for c in self.deck if c not in used)
        if len(cards) != len(set(cards)) or used & set(cards): raise AssertionError("invalid turn card removal")
        return cards
    def remaining_river_cards(self):
        if self.turn_card is None: raise ValueError("river candidates require selected turn")
        used = set(FIXED_FLOP) | set(self.player0_cards) | set(self.player1_cards) | {self.turn_card}; cards = tuple(c for c in self.deck if c not in used)
        if len(cards) != len(set(cards)) or used & set(cards): raise AssertionError("invalid conditional river card removal")
        return cards
    def chance_outcomes(self):
        if not self.chance: raise ValueError("outcomes requested outside chance node")
        cards = self.remaining_turn_cards() if self.turn_card is None else self.remaining_river_cards(); probability = 1.0/len(cards)
        if self.turn_card is None: return tuple((c, RiverHoldemState(self.player0_cards,self.player1_cards,self.flop_history,c,(),None,(),self.deck), probability) for c in cards)
        return tuple((c, RiverHoldemState(self.player0_cards,self.player1_cards,self.flop_history,self.turn_card,self.turn_history,c,(),self.deck), probability) for c in cards)
    def information_set(self): return HoldemAbstraction.information_set(self.decision_state())
    def utility_p0(self):
        if not self.terminal: raise ValueError("utility requested from nonterminal")
        totals = self._total_commitments(); histories = (self.flop_history, self.turn_history, self.river_history)
        for history in histories:
            if history and history[-1].action_type == "fold":
                folder = (len(history)-1)%2; return float(-STARTING_POT/2-totals[0]) if folder == 0 else float(STARTING_POT/2+totals[1])
        board = FIXED_FLOP + (() if self.turn_card is None else (self.turn_card,)) + (() if self.river_card is None else (self.river_card,))
        s0, s1 = EVALUATOR.score(list(self.player0_cards),list(board)), EVALUATOR.score(list(self.player1_cards),list(board))
        if s0 == s1: return float((totals[1]-totals[0])/2)
        return float(STARTING_POT/2+totals[1]) if s0 < s1 else float(-STARTING_POT/2-totals[0])
    def utility(self, player): return self.utility_p0() if player == 0 else -self.utility_p0()


def river_chance_states(deck: Iterable[str] = RIVER_RESEARCH_DECK):
    cards = tuple(deck)
    if len(cards) < 7 or len(cards) != len(set(cards)) or set(cards) & set(FIXED_FLOP): raise ValueError("deck needs seven unique cards disjoint from fixed flop")
    return tuple(RiverHoldemState(p0,p1,deck=cards) for p0 in combinations(cards,2) for p1 in combinations(tuple(c for c in cards if c not in p0),2))


def river_subgame_convention():
    return {"name":"phase-4g-fixed-flop-turn-river-chance-abstract-subgame","scope":"bounded three-street research game, not full heads-up no-limit Hold'em","fixed_flop":list(FIXED_FLOP),"private_card_deck":list(RIVER_RESEARCH_DECK),"starting_pot":STARTING_POT,"remaining_stack_each":STACK,"position":"Player 0 is out of position and acts first on flop, turn, and river","flop_actions":"Phase 4C fold/check/call/all-in plus legal 50%, 75%, 125%-pot total-target bets","turn_chance":"after a completed non-all-in flop round, uniformly sample every legal remaining turn","turn_actions":"same Phase 4C action set with reset street commitments and carried pot/stacks","river_chance":"after a completed non-all-in turn round, uniformly sample every remaining card conditional on the selected turn","river_actions":"same Phase 4C action set with reset street commitments and carried pot/stacks","maximum_raises":"one all-in response; normal reraises are excluded","terminal_payoff":"zero-sum Player 0 net chip change; folds settle immediately and river check/call showdowns use all five public cards","showdown":"Treys five-card-board evaluation; equal scores split matched contributions","no_future_card_after_river":True}
