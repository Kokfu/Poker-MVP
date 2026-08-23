"""Full-tree vanilla CFR for Kuhn Poker.

For an action at information set I of player i, regret is incremented by
pi_-i(h) * pi_c(h) * (u_i(h,a) - u_i(h)).  Strategy sums use
pi_i(h) * pi_c(h) * sigma_i(I,a).  Enumerating all six deals makes training
deterministic; pi_c is 1/6 for each deal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .game import Action, DEALS, KuhnState

CHANCE = 1.0 / len(DEALS)
StrategyProfile = Mapping[str, Mapping[Action, float]]
DeltaTable = dict[str, dict[Action, float]]


def regret_matching(regrets: dict[Action, float], actions: Iterable[Action]) -> dict[Action, float]:
    actions = tuple(actions)
    positives = {action: max(0.0, regrets.get(action, 0.0)) for action in actions}
    total = sum(positives.values())
    if total <= 0.0:
        return {action: 1.0 / len(actions) for action in actions}
    return {action: positives[action] / total for action in actions}


@dataclass
class InfoSet:
    player: int
    key: str
    actions: tuple[Action, ...]
    regrets: dict[Action, float] = field(init=False)
    strategy_sum: dict[Action, float] = field(init=False)

    def __post_init__(self) -> None:
        self.regrets = {action: 0.0 for action in self.actions}
        self.strategy_sum = {action: 0.0 for action in self.actions}

    def strategy(self) -> dict[Action, float]:
        return regret_matching(self.regrets, self.actions)

    def average_strategy(self) -> dict[Action, float]:
        total = sum(self.strategy_sum.values())
        if total <= 0.0:
            return {action: 1.0 / len(self.actions) for action in self.actions}
        return {action: self.strategy_sum[action] / total for action in self.actions}


class KuhnCFRTrainer:
    """Deterministic exact-chance vanilla CFR trainer."""
    def __init__(self) -> None:
        self.infosets: dict[str, InfoSet] = {}
        self.iterations = 0
        self.last_diagnostic: list[dict[str, object]] = []

    def reset(self) -> None:
        self.infosets.clear(); self.iterations = 0; self.last_diagnostic = []

    def _infoset(self, state: KuhnState) -> InfoSet:
        player = state.acting_player
        assert player is not None
        key = state.information_set(player)
        if key not in self.infosets:
            self.infosets[key] = InfoSet(player, key, state.legal_actions)
        return self.infosets[key]

    def _ensure_infosets(self) -> None:
        """Register the complete fixed Kuhn information-set tree without updating it."""
        def visit(state: KuhnState) -> None:
            if state.terminal:
                return
            self._infoset(state)
            for action in state.legal_actions:
                visit(state.apply(action))

        for deal in DEALS:
            visit(KuhnState(deal))

    def _frozen_profile(self) -> dict[str, dict[Action, float]]:
        return {key: self.infosets[key].strategy() for key in sorted(self.infosets)}

    @staticmethod
    def _empty_deltas(infosets: Mapping[str, InfoSet]) -> DeltaTable:
        return {key: {action: 0.0 for action in node.actions} for key, node in infosets.items()}

    def _cfr(
        self,
        state: KuhnState,
        reach0: float,
        reach1: float,
        profile: StrategyProfile,
        regret_deltas: DeltaTable,
        strategy_sum_deltas: DeltaTable,
        diagnostic: list[dict[str, object]] | None,
    ) -> float:
        """Evaluate one chance outcome against a profile frozen for this iteration."""
        if state.terminal:
            return state.utility_p0()
        node = self._infoset(state)
        strategy = profile[node.key]
        action_values: dict[Action, float] = {}
        for action in node.actions:
            next0 = reach0 * strategy[action] if node.player == 0 else reach0
            next1 = reach1 * strategy[action] if node.player == 1 else reach1
            action_values[action] = self._cfr(
                state.apply(action), next0, next1, profile, regret_deltas, strategy_sum_deltas, diagnostic
            )
        value = sum(strategy[a] * action_values[a] for a in node.actions)
        sign = 1.0 if node.player == 0 else -1.0
        counterfactual = (reach1 if node.player == 0 else reach0) * CHANCE
        own_reach = (reach0 if node.player == 0 else reach1) * CHANCE
        regret_updates = {a: sign * counterfactual * (action_values[a] - value) for a in node.actions}
        for action in node.actions:
            regret_deltas[node.key][action] += regret_updates[action]
            strategy_sum_deltas[node.key][action] += own_reach * strategy[action]
        if diagnostic is not None:
            diagnostic.append({"deal": "".join(c.value for c in state.cards), "infoset": node.key,
                "player": node.player, "strategy": {a.value: strategy[a] for a in node.actions},
                "action_utilities_p0": {a.value: action_values[a] for a in node.actions}, "node_utility_p0": value,
                "regret_updates": {a.value: regret_updates[a] for a in node.actions},
                "strategy_sum_updates": {a.value: own_reach * strategy[a] for a in node.actions}})
        return value

    def train(self, iterations: int, diagnostic: bool = False) -> "KuhnCFRTrainer":
        if iterations < 0: raise ValueError("iterations must be non-negative")
        self._ensure_infosets()
        for offset in range(iterations):
            trace: list[dict[str, object]] | None = [] if diagnostic and offset == 0 else None
            profile = self._frozen_profile()
            regret_deltas = self._empty_deltas(self.infosets)
            strategy_sum_deltas = self._empty_deltas(self.infosets)
            for deal in DEALS:
                self._cfr(KuhnState(deal), 1.0, 1.0, profile, regret_deltas, strategy_sum_deltas, trace)
            for key in sorted(self.infosets):
                node = self.infosets[key]
                for action in node.actions:
                    node.regrets[action] += regret_deltas[key][action]
                    node.strategy_sum[action] += strategy_sum_deltas[key][action]
            if trace is not None: self.last_diagnostic = trace
            self.iterations += 1
        return self

    def average_strategy(self) -> dict[str, dict[Action, float]]:
        return {key: self.infosets[key].average_strategy() for key in sorted(self.infosets)}

    def strategy_table(self) -> list[dict[str, object]]:
        rows = []
        for key in sorted(self.infosets):
            node = self.infosets[key]
            convert = lambda values: {a.value: values[a] for a in node.actions}
            card, history = key.split("|", 1)
            rows.append({"information_set": key, "player": node.player, "private_card": card, "history": history,
                         "legal_actions": [a.value for a in node.actions], "cumulative_regrets": convert(node.regrets),
                         "current_strategy": convert(node.strategy()), "average_strategy": convert(node.average_strategy())})
        return rows
