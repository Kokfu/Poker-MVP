"""Deterministic full-tree Vanilla CFR and CFR+ for the Phase 4D subgame."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from .subgame import HoldemSubgameState, chance_states


def regret_matching(regrets: dict[str, float], actions: tuple[str, ...]) -> dict[str, float]:
    positive = {action: max(0.0, regrets[action]) for action in actions}
    total = sum(positive.values())
    return ({action: positive[action] / total for action in actions} if total else
            {action: 1.0 / len(actions) for action in actions})


@dataclass
class InfoSet:
    player: int
    key: str
    actions: tuple[str, ...]
    regrets: dict[str, float] = field(init=False)
    strategy_sum: dict[str, float] = field(init=False)
    visits: int = 0

    def __post_init__(self) -> None:
        self.regrets = {action: 0.0 for action in self.actions}
        self.strategy_sum = {action: 0.0 for action in self.actions}

    def strategy(self) -> dict[str, float]: return regret_matching(self.regrets, self.actions)
    def average(self) -> dict[str, float]:
        total = sum(self.strategy_sum.values())
        return ({action: self.strategy_sum[action] / total for action in self.actions} if total else
                {action: 1.0 / len(self.actions) for action in self.actions})


class HoldemSubgameCFRTrainer:
    """Generic game-facing CFR core instantiated with Phase 4D state methods.

    The trainer depends only on terminal/acting-player/legal/apply/infoset/utility
    state operations, keeping the solver separate from Hold'em rules and bots.
    """
    def __init__(self, algorithm: str = "vanilla", averaging_delay: int = 0,
                 roots: tuple[HoldemSubgameState, ...] | None = None) -> None:
        if algorithm not in {"vanilla", "cfr_plus"}: raise ValueError("algorithm must be vanilla or cfr_plus")
        if averaging_delay < 0: raise ValueError("averaging_delay must be non-negative")
        self.algorithm, self.averaging_delay = algorithm, averaging_delay
        supplied_roots = roots or chance_states()
        self.roots = tuple(sorted(supplied_roots, key=lambda state: (state.player0_cards, state.player1_cards)))
        self.chance = 1.0 / len(self.roots)
        self.infosets: dict[str, InfoSet] = {}; self.iterations = 0; self.last_runtime_seconds = 0.0
        self.last_frozen_profile: dict[str, dict[str, float]] = {}
        self._transitions: dict[HoldemSubgameState, tuple[tuple[str, HoldemSubgameState], ...]] = {}
        self._state_nodes: dict[HoldemSubgameState, InfoSet] = {}
        self._ensure_infosets()

    def _node(self, state: HoldemSubgameState) -> InfoSet:
        player = state.acting_player; assert player is not None
        key = state.information_set(); actions = tuple(item.label for item in state.legal_actions)
        node = self.infosets.get(key)
        if node is None: self.infosets[key] = node = InfoSet(player, key, actions)
        elif node.actions != actions or node.player != player: raise AssertionError("inconsistent abstract information set")
        self._state_nodes[state] = node
        return node

    def _ensure_infosets(self) -> None:
        def visit(state: HoldemSubgameState) -> None:
            if state.terminal: return
            self._node(state)
            transitions = tuple((action.label, state.apply(action)) for action in state.legal_actions)
            self._transitions[state] = transitions
            for _, child in transitions: visit(child)
        for root in self.roots: visit(root)

    def _walk(self, state, reach0, reach1, profile, regret_delta, sum_delta, weight) -> float:
        if state.terminal: return state.utility_p0()
        node = self._state_nodes[state]; strategy = profile[node.key]; values = {}
        for label, child in self._transitions[state]:
            values[label] = self._walk(child, reach0 * strategy[label] if node.player == 0 else reach0,
                reach1 * strategy[label] if node.player == 1 else reach1, profile, regret_delta, sum_delta, weight)
        value = sum(strategy[label] * values[label] for label in node.actions)
        sign = 1.0 if node.player == 0 else -1.0
        cf = (reach1 if node.player == 0 else reach0) * self.chance
        own = (reach0 if node.player == 0 else reach1) * self.chance
        for label in node.actions:
            regret_delta[node.key][label] += sign * cf * (values[label] - value)
            sum_delta[node.key][label] += weight * own * strategy[label]
        node.visits += 1
        return value

    def train(self, iterations: int) -> "HoldemSubgameCFRTrainer":
        if iterations < 0: raise ValueError("iterations must be non-negative")
        started = perf_counter()
        for _ in range(iterations):
            profile = {key: node.strategy() for key, node in sorted(self.infosets.items())}
            self.last_frozen_profile = profile
            regrets = {key: {action: 0.0 for action in node.actions} for key, node in self.infosets.items()}
            sums = {key: {action: 0.0 for action in node.actions} for key, node in self.infosets.items()}
            weight = 1.0 if self.algorithm == "vanilla" else float(max(0, self.iterations + 1 - self.averaging_delay))
            for root in self.roots: self._walk(root, 1.0, 1.0, profile, regrets, sums, weight)
            for key, node in self.infosets.items():
                for action in node.actions:
                    node.regrets[action] = max(0.0, node.regrets[action] + regrets[key][action]) if self.algorithm == "cfr_plus" else node.regrets[action] + regrets[key][action]
                    node.strategy_sum[action] += sums[key][action]
            self.iterations += 1
        self.last_runtime_seconds = perf_counter() - started
        return self

    def average_strategy(self) -> dict[str, dict[str, float]]: return {key: node.average() for key, node in sorted(self.infosets.items())}
    def strategy_table(self) -> list[dict[str, object]]:
        return [{"information_set": key, "player": node.player, "legal_abstract_actions": list(node.actions),
                 "current_strategy": node.strategy(), "average_strategy": node.average(),
                 "cumulative_regrets": dict(node.regrets), "visits": node.visits}
                for key, node in sorted(self.infosets.items())]

    def strategy_document(self) -> dict[str, object]:
        """Deterministic research-only serialization; no production schema is used."""
        return {"phase_4d_research_strategy_schema_version": "1.0", "algorithm": self.algorithm,
                "iterations": self.iterations, "information_sets": self.strategy_table()}

    def profile_ev(self, policy0=None, policy1=None) -> float:
        policy0, policy1 = policy0 or self.average_strategy(), policy1 or self.average_strategy()
        def walk(state):
            if state.terminal: return state.utility_p0()
            policy = policy0 if state.acting_player == 0 else policy1
            node = self._state_nodes[state]; distribution = policy[node.key]
            return sum(distribution[label] * walk(child) for label, child in self._transitions[state])
        return sum(walk(root) for root in self.roots) * self.chance
