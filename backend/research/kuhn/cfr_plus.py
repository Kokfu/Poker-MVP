"""Full-tree CFR+ for canonical Kuhn Poker.

CFR+ is deliberately separate from :mod:`research.kuhn.cfr`: it uses the
same exact traversal, but projects cumulative regrets to zero after each
iteration.  Its average policy uses the standard linearly weighted convention:
iteration ``t`` contributes weight ``max(0, t - averaging_delay)``.  Thus the
default (delay zero) weights iterations 1, 2, ... by 1, 2, ... .  The delay is
an explicit reporting/training parameter rather than an implicit tuning knob.
"""
from __future__ import annotations

from .cfr import CHANCE, DeltaTable, InfoSet, StrategyProfile
from .game import Action, DEALS, KuhnState


class KuhnCFRPlusTrainer:
    """Deterministic exact-chance CFR+ trainer with linear averaging."""

    def __init__(self, averaging_delay: int = 0) -> None:
        if averaging_delay < 0:
            raise ValueError("averaging_delay must be non-negative")
        self.averaging_delay = averaging_delay
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
    def _empty_deltas(infosets: dict[str, InfoSet]) -> DeltaTable:
        return {key: {action: 0.0 for action in node.actions} for key, node in infosets.items()}

    def _cfr(self, state: KuhnState, reach0: float, reach1: float, profile: StrategyProfile,
             regret_deltas: DeltaTable, strategy_sum_deltas: DeltaTable, average_weight: float,
             diagnostic: list[dict[str, object]] | None) -> float:
        if state.terminal:
            return state.utility_p0()
        node = self._infoset(state)
        strategy = profile[node.key]
        values: dict[Action, float] = {}
        for action in node.actions:
            values[action] = self._cfr(
                state.apply(action), reach0 * strategy[action] if node.player == 0 else reach0,
                reach1 * strategy[action] if node.player == 1 else reach1, profile, regret_deltas,
                strategy_sum_deltas, average_weight, diagnostic,
            )
        value = sum(strategy[action] * values[action] for action in node.actions)
        sign = 1.0 if node.player == 0 else -1.0
        counterfactual = (reach1 if node.player == 0 else reach0) * CHANCE
        own_reach = (reach0 if node.player == 0 else reach1) * CHANCE
        updates = {action: sign * counterfactual * (values[action] - value) for action in node.actions}
        for action in node.actions:
            regret_deltas[node.key][action] += updates[action]
            strategy_sum_deltas[node.key][action] += average_weight * own_reach * strategy[action]
        if diagnostic is not None:
            diagnostic.append({"deal": "".join(card.value for card in state.cards), "infoset": node.key,
                "player": node.player, "strategy": {a.value: strategy[a] for a in node.actions},
                "regret_updates": {a.value: updates[a] for a in node.actions}, "average_weight": average_weight})
        return value

    def _apply_iteration_deltas(self, regret_deltas: DeltaTable, strategy_sum_deltas: DeltaTable) -> None:
        """Apply one frozen-profile iteration, then project regrets into CFR+ space."""
        for key in sorted(self.infosets):
            node = self.infosets[key]
            for action in node.actions:
                node.regrets[action] = max(0.0, node.regrets[action] + regret_deltas[key][action])
                node.strategy_sum[action] += strategy_sum_deltas[key][action]

    def train(self, iterations: int, diagnostic: bool = False) -> "KuhnCFRPlusTrainer":
        if iterations < 0:
            raise ValueError("iterations must be non-negative")
        self._ensure_infosets()
        for offset in range(iterations):
            trace = [] if diagnostic and offset == 0 else None
            profile = self._frozen_profile()
            regret_deltas = self._empty_deltas(self.infosets)
            strategy_sum_deltas = self._empty_deltas(self.infosets)
            iteration = self.iterations + 1
            average_weight = float(max(0, iteration - self.averaging_delay))
            for deal in DEALS:
                self._cfr(KuhnState(deal), 1.0, 1.0, profile, regret_deltas, strategy_sum_deltas,
                          average_weight, trace)
            self._apply_iteration_deltas(regret_deltas, strategy_sum_deltas)
            if trace is not None:
                self.last_diagnostic = trace
            self.iterations += 1
        return self

    def average_strategy(self) -> dict[str, dict[Action, float]]:
        return {key: self.infosets[key].average_strategy() for key in sorted(self.infosets)}

    def strategy_table(self) -> list[dict[str, object]]:
        rows = []
        for key in sorted(self.infosets):
            node = self.infosets[key]
            convert = lambda values: {action.value: values[action] for action in node.actions}
            card, history = key.split("|", 1)
            rows.append({"information_set": key, "player": node.player, "private_card": card, "history": history,
                         "legal_actions": [a.value for a in node.actions], "cumulative_regrets": convert(node.regrets),
                         "current_strategy": convert(node.strategy()), "average_strategy": convert(node.average_strategy())})
        return rows
