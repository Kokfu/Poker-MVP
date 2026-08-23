"""Small exact BR validation for the Phase 4D Hold'em CFR machinery.

This is intentionally a *reduced* game, not a measurement of the full
3,510-node subgame.  It retains fixed-flop cards, Phase 4C action objects and
information-set keys, but selects three hidden-card deals and restricts the
public betting tree to check/bet/fold/call.  That leaves 4 and 16 pure
information-set policies for Players 0 and 1 respectively, so exact behavioral
best responses are cheap to enumerate.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Mapping

from .cfr import HoldemSubgameCFRTrainer
from .subgame import HoldemSubgameState


@dataclass(frozen=True)
class ReducedHoldemState:
    """Action-restricted adapter around the normal fixed-flop state."""
    base: HoldemSubgameState

    @property
    def terminal(self) -> bool: return self.base.terminal
    @property
    def player0_cards(self): return self.base.player0_cards
    @property
    def player1_cards(self): return self.base.player1_cards
    @property
    def acting_player(self) -> int | None: return self.base.acting_player
    @property
    def history(self): return self.base.history
    def information_set(self) -> str: return self.base.information_set()
    def utility_p0(self) -> float: return self.base.utility_p0()

    @property
    def legal_actions(self):
        if self.terminal: return ()
        allowed = {"check", "bet"} if not self.history or self.history[-1].action_type == "check" else {"fold", "call"}
        chosen: set[str] = set()
        # Keep one normal bet representative; all selected objects still come
        # directly from the Phase 4C abstraction.
        actions = []
        for action in self.base.legal_actions:
            if action.action_type in allowed and action.action_type not in chosen:
                actions.append(action)
                chosen.add(action.action_type)
        return tuple(actions)

    def apply(self, action):
        if action not in self.legal_actions: raise ValueError(f"illegal reduced action: {action.label}")
        return ReducedHoldemState(self.base.apply(action))


def reduced_roots() -> tuple[ReducedHoldemState, ...]:
    """Three equiprobable legal deals with real hidden-card ambiguity.

    Player 0's ``Ah Ad`` occurs against two opponent holdings and Player 1's
    ``Qs Js`` occurs against two opponent holdings.  Thus neither response can
    condition on an opponent card.
    """
    deals = ((("Ah", "Ad"), ("Qs", "Js")), (("Kh", "Kc"), ("Qs", "Js")),
             (("Ah", "Ad"), ("Kh", "Kc")))
    return tuple(ReducedHoldemState(HoldemSubgameState(p0, p1)) for p0, p1 in deals)


Policy = Mapping[str, Mapping[str, float]]


def exact_metrics(trainer: HoldemSubgameCFRTrainer) -> dict[str, float]:
    """Enumerate constrained pure BRs for a reduced trainer's average profile."""
    profile = trainer.average_strategy()
    policies: dict[int, Policy] = {player: {key: profile[key] for key, node in trainer.infosets.items()
                                             if node.player == player} for player in (0, 1)}

    def best_response(player: int) -> float:
        nodes = sorted((node for node in trainer.infosets.values() if node.player == player), key=lambda node: node.key)
        best = float("-inf") if player == 0 else float("inf")
        for picks in product(*(range(len(node.actions)) for node in nodes)):
            response = {node.key: {action: float(index == pick) for index, action in enumerate(node.actions)}
                        for node, pick in zip(nodes, picks)}
            value = trainer.profile_ev(response, policies[1]) if player == 0 else trainer.profile_ev(policies[0], response)
            best = max(best, value) if player == 0 else min(best, value)
        return best

    value = trainer.profile_ev(policies[0], policies[1]); br0, br1_as_u0 = best_response(0), best_response(1)
    nashconv = br0 - br1_as_u0
    return {"player0_ev": value, "player1_ev": -value, "br0": br0, "br1_as_u0": br1_as_u0,
            "nashconv": nashconv, "exploitability": nashconv / 2.0}


def reduced_exact_report(iterations: int = 100) -> dict[str, object]:
    trainer = HoldemSubgameCFRTrainer("vanilla", roots=reduced_roots()).train(iterations)
    return {"scope": "reduced exact validation only; not full-subgame exploitability",
            "chance_deals": len(trainer.roots), "information_sets": len(trainer.infosets), "metrics": exact_metrics(trainer)}
