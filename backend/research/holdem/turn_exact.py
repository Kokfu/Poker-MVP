"""Small exhaustive two-street control using the Phase 4F game machinery."""
from __future__ import annotations

from dataclasses import dataclass

from .cfr import HoldemSubgameCFRTrainer
from .reduced_exact import exact_metrics
from .turn_subgame import TurnHoldemState


@dataclass(frozen=True)
class ReducedTurnState:
    """A tractable action restriction over one real deal and two real turns.

    The base state owns all card removal, chance, board visibility, stack,
    payoff, and Phase 4C action logic.  Only the advertised action subset is
    reduced so exact constrained best responses remain enumerable.
    """

    base: TurnHoldemState
    reverse_turn_order: bool = False

    @property
    def terminal(self): return self.base.terminal
    @property
    def chance(self): return self.base.chance
    @property
    def acting_player(self): return self.base.acting_player
    @property
    def street(self): return self.base.street
    @property
    def player0_cards(self): return self.base.player0_cards
    @property
    def player1_cards(self): return self.base.player1_cards
    @property
    def history(self): return self.base.flop_history + self.base.turn_history
    def information_set(self): return self.base.information_set()
    def utility_p0(self): return self.base.utility_p0()

    def chance_outcomes(self):
        outcomes = self.base.chance_outcomes()
        if self.reverse_turn_order:
            outcomes = tuple(reversed(outcomes))
        return tuple((label, ReducedTurnState(child, self.reverse_turn_order), probability)
                     for label, child, probability in outcomes)

    @property
    def legal_actions(self):
        if self.terminal or self.chance:
            return ()
        if self.base.turn_card is None:
            allowed = {"check"}
        elif not self.base.turn_history or self.base.turn_history[-1].action_type == "check":
            allowed = {"check", "bet"}
        else:
            allowed = {"fold", "call"}
        picked = set(); result = []
        for action in self.base.legal_actions:
            if action.action_type in allowed and action.action_type not in picked:
                result.append(action); picked.add(action.action_type)
        return tuple(result)

    def apply(self, action):
        if action not in self.legal_actions:
            raise ValueError(f"illegal reduced action: {action.label}")
        return ReducedTurnState(self.base.apply(action), self.reverse_turn_order)


def reduced_turn_roots(reverse_turn_order: bool = False) -> tuple[ReducedTurnState, ...]:
    # Six physical cards leave Qs and Js as two equally likely public turns.
    base = TurnHoldemState(("Ah", "Ad"), ("Kh", "Kc"), deck=("Ah", "Ad", "Kh", "Kc", "Qs", "Js"))
    return (ReducedTurnState(base, reverse_turn_order),)


def reduced_turn_report(iterations: int = 20) -> dict[str, object]:
    trainer = HoldemSubgameCFRTrainer("vanilla", roots=reduced_turn_roots()).train(iterations)
    return {
        "scope": "reduced exact two-street validation only; not larger Phase 4F exploitability",
        "private_deals": 1, "turn_outcomes": 2, "information_sets": len(trainer.infosets),
        "metrics": exact_metrics(trainer),
    }
