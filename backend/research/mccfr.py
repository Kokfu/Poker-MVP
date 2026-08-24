"""Research-only external-sampling Monte Carlo CFR core.

One logical iteration performs one sampled traversal for each player.  Chance
and non-traverser actions are sampled; traverser actions are enumerated.  For
the sampled distribution used here (true chance and current opponent policy),
the sampled counterfactual-regret multiplier ``pi_-i / q`` is one.  Average
policy entries use the standard external-sampling correction
``pi_i / q_-i``.  Keeping this small game-facing core separate prevents it
from becoming an alternate implementation of any production poker rule.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import isfinite
import random
import sys
from time import perf_counter
from typing import Any, Callable, Hashable, Iterable, Mapping


Action = Hashable


def external_sampling_regret_updates(
    strategy: Mapping[Action, float], action_values: Mapping[Action, float],
) -> dict[Action, float]:
    """Return the no-extra-ratio external-sampling regret estimator.

    Chance and opponent actions are sampled from their target distributions,
    so their counterfactual reach is already present in trajectory
    probability.  The sampled estimator therefore needs only
    ``u(a) - sum_a sigma(a) u(a)`` here.
    """
    value = sum(strategy[action] * action_values[action] for action in strategy)
    return {action: action_values[action] - value for action in strategy}


def external_sampling_strategy_sum_increment(
    strategy: Mapping[Action, float], own_reach: float, sampled_opponent_reach: float,
) -> dict[Action, float]:
    """Return the external-sampling average-policy increment.

    The sample probability at a traverser information set is
    ``q_c * q_-i``.  With true chance and opponent-policy sampling,
    ``q_c`` remains in the expectation and only ``q_-i`` is cancelled:
    ``(pi_i / q_-i) * sigma_i``.  Thus no second chance importance ratio is
    applied.
    """
    if sampled_opponent_reach <= 0.0 or not isfinite(sampled_opponent_reach):
        raise AssertionError("invalid sampled opponent reach")
    correction = own_reach / sampled_opponent_reach
    return {action: correction * strategy[action] for action in strategy}


def regret_matching(regrets: dict[Action, float], actions: tuple[Action, ...]) -> dict[Action, float]:
    positive = {action: max(0.0, regrets[action]) for action in actions}
    total = sum(positive.values())
    if total <= 0.0:
        return {action: 1.0 / len(actions) for action in actions}
    return {action: positive[action] / total for action in actions}


@dataclass
class MCCFRInfoSet:
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

    def average(self) -> dict[Action, float]:
        total = sum(self.strategy_sum.values())
        if total <= 0.0:
            return {action: 1.0 / len(self.actions) for action in self.actions}
        return {action: self.strategy_sum[action] / total for action in self.actions}


class ExternalSamplingMCCFRTrainer:
    """External-sampling MCCFR over immutable two-player zero-sum states.

    ``roots`` are chance outcomes and ``chance_weights`` is their actual
    distribution.  The trainer owns a dedicated ``random.Random`` instance;
    nothing supplied by a game state may provide or consume that RNG.
    """

    def __init__(
        self,
        roots: Iterable[Any],
        seed: int,
        *,
        chance_weights: Iterable[float] | None = None,
        action_label: Callable[[Action], str] = str,
        chance_label: Callable[[Any], str] = repr,
        full_tree_node_count: int | None = None,
    ) -> None:
        self.roots = tuple(roots)
        if not self.roots:
            raise ValueError("at least one chance root is required")
        supplied_weights = tuple(chance_weights) if chance_weights is not None else (1.0,) * len(self.roots)
        if len(supplied_weights) != len(self.roots) or any(weight <= 0.0 or not isfinite(weight) for weight in supplied_weights):
            raise ValueError("chance weights must be finite and positive")
        total = sum(supplied_weights)
        self.chance_weights = tuple(weight / total for weight in supplied_weights)
        self.seed = seed
        self.rng = random.Random(seed)
        self.action_label = action_label
        self.chance_label = chance_label
        self.full_tree_node_count = full_tree_node_count
        self.infosets: dict[str, MCCFRInfoSet] = {}
        self.iterations = 0
        self.last_runtime_seconds = 0.0
        self.total_visited_nodes = 0
        self.total_traversals = 0
        self.chance_sample_counts: Counter[str] = Counter()
        self.future_chance_sample_counts: Counter[str] = Counter()
        self.action_sample_counts: Counter[str] = Counter()
        self.infoset_visit_counts: Counter[str] = Counter()
        self.last_trajectories: list[dict[str, object]] = []
        self.last_diagnostic: list[dict[str, object]] = []
        self.last_traversal_profiles: list[dict[str, object]] = []

    def _node(self, state: Any) -> MCCFRInfoSet:
        player = state.acting_player
        assert player in (0, 1)
        key = state.information_set()
        actions = tuple(state.legal_actions)
        node = self.infosets.get(key)
        if node is None:
            node = MCCFRInfoSet(player, key, actions)
            self.infosets[key] = node
        elif node.player != player or node.actions != actions:
            raise AssertionError("inconsistent information set")
        return node

    def _sample_root(self) -> tuple[Any, float]:
        threshold = self.rng.random()
        cumulative = 0.0
        for root, probability in zip(self.roots, self.chance_weights):
            cumulative += probability
            if threshold < cumulative:
                return root, probability
        # Protects only roundoff at the upper endpoint; all configured chance
        # outcomes have strictly positive probability.
        return self.roots[-1], self.chance_weights[-1]

    def _sample_action(self, strategy: dict[Action, float]) -> Action:
        threshold = self.rng.random()
        cumulative = 0.0
        last: Action | None = None
        for action, probability in strategy.items():
            if probability < 0.0 or not isfinite(probability):
                raise AssertionError("invalid strategy probability")
            cumulative += probability
            last = action
            if threshold < cumulative:
                return action
        if last is None or abs(cumulative - 1.0) > 1e-12:
            raise AssertionError("strategy probabilities do not sum to one")
        return last

    def _sample_future_chance(self, state: Any) -> tuple[Any, float, str]:
        """Sample one game-provided non-root chance outcome.

        A future chance node uses the same dedicated RNG and true-probability
        convention as root chance.  Game states expose only the public label,
        child, and conditional probability needed here; they never expose a
        deck order to an information-set key or policy.
        """
        outcomes = tuple(state.chance_outcomes())
        if not outcomes:
            raise AssertionError("chance node has no outcomes")
        labels, children, weights = zip(*outcomes)
        if any(weight <= 0.0 or not isfinite(weight) for weight in weights):
            raise AssertionError("invalid future chance probability")
        if abs(sum(weights) - 1.0) > 1e-12:
            raise AssertionError("future chance probabilities do not sum to one")
        threshold = self.rng.random()
        cumulative = 0.0
        for label, child, probability in zip(labels, children, weights):
            cumulative += probability
            if threshold < cumulative:
                return child, probability, str(label)
        return children[-1], weights[-1], str(labels[-1])

    def _frozen_profile(self) -> dict[str, dict[Action, float]]:
        """Snapshot current policies for one traverser traversal.

        A logical iteration deliberately has two sequential update boundaries:
        traverser 0 snapshots, traverses, and applies its updates; traverser 1
        then snapshots the resulting policy.  This is alternating external
        sampling, not a shared iteration-start profile.  The snapshot is
        populated lazily on first decision use: in this finite acyclic tree an
        unvisited information set cannot have been mutated already, while a
        revisited one is served from the cached strategy.  That is equivalent
        to eager copying for the traversal and avoids copying every untouched
        information set on every sampled pass.
        """
        return {}

    @staticmethod
    def _strategy_from_profile(
        node: MCCFRInfoSet, profile: dict[str, dict[Action, float]],
    ) -> dict[Action, float]:
        strategy = profile.get(node.key)
        if strategy is None:
            strategy = dict(node.strategy())
            profile[node.key] = strategy
        return strategy

    def _traverse(
        self,
        state: Any,
        traverser: int,
        own_reach: float,
        sampled_opponent_reach: float,
        profile: dict[str, dict[Action, float]],
        trace: list[dict[str, object]],
        diagnostic: list[dict[str, object]] | None,
    ) -> float:
        self.total_visited_nodes += 1
        if state.terminal:
            utility = state.utility_p0()
            return utility if traverser == 0 else -utility
        if getattr(state, "chance", False):
            child, probability, label = self._sample_future_chance(state)
            self.future_chance_sample_counts[label] += 1
            trace.append({
                "future_chance": label,
                "chance_probability": probability,
            })
            if diagnostic is not None:
                diagnostic.append({
                    "traverser": traverser,
                    "sampled_future_chance": label,
                    "sample_probability": probability,
                })
            # True conditional chance sampling needs no extra estimator ratio:
            # its probability remains in the expectation just as root chance.
            return self._traverse(
                child, traverser, own_reach, sampled_opponent_reach,
                profile, trace, diagnostic,
            )
        node = self._node(state)
        strategy = self._strategy_from_profile(node, profile)
        self.infoset_visit_counts[node.key] += 1
        if node.player == traverser:
            values: dict[Action, float] = {}
            for action in node.actions:
                values[action] = self._traverse(
                    state.apply(action), traverser, own_reach * strategy[action], sampled_opponent_reach,
                    profile, trace, diagnostic,
                )
            # q(h) is the actual chance probability times sampled opponent
            # reach, so pi_-i(h) / q(h) is one in this sampler.
            value = sum(strategy[action] * values[action] for action in node.actions)
            updates = external_sampling_regret_updates(strategy, values)
            strategy_increment = external_sampling_strategy_sum_increment(
                strategy, own_reach, sampled_opponent_reach,
            )
            for action in node.actions:
                node.regrets[action] += updates[action]
                node.strategy_sum[action] += strategy_increment[action]
            if diagnostic is not None:
                diagnostic.append({
                    "traverser": traverser,
                    "infoset": node.key,
                    "player": node.player,
                    "enumerated_actions": [self.action_label(action) for action in node.actions],
                    "strategy": {self.action_label(action): strategy[action] for action in node.actions},
                    "action_utilities_for_traverser": {self.action_label(action): values[action] for action in node.actions},
                    "regret_updates": {self.action_label(action): updates[action] for action in node.actions},
                    "average_strategy_correction": own_reach / sampled_opponent_reach,
                })
            return value
        action = self._sample_action(strategy)
        probability = strategy[action]
        self.action_sample_counts[self.action_label(action)] += 1
        trace.append({"infoset": node.key, "action": self.action_label(action), "probability": probability})
        if diagnostic is not None:
            diagnostic.append({
                "traverser": traverser,
                "infoset": node.key,
                "player": node.player,
                "sampled_opponent_action": self.action_label(action),
                "sample_probability": probability,
            })
        return self._traverse(
            state.apply(action), traverser, own_reach, sampled_opponent_reach * probability,
            profile, trace, diagnostic,
        )

    def train(self, iterations: int, diagnostic: bool = False) -> "ExternalSamplingMCCFRTrainer":
        if iterations < 0:
            raise ValueError("iterations must be non-negative")
        started = perf_counter()
        self.last_trajectories = []
        self.last_diagnostic = []
        self.last_traversal_profiles = []
        for offset in range(iterations):
            for traverser in (0, 1):
                # Each pass is internally frozen.  The following pass begins
                # only after this one has updated regrets, by design.
                profile = self._frozen_profile()
                root, chance_probability = self._sample_root()
                label = self.chance_label(root)
                self.chance_sample_counts[label] += 1
                trace: list[dict[str, object]] = []
                rows: list[dict[str, object]] | None = [] if diagnostic and offset == 0 else None
                self._traverse(root, traverser, 1.0, 1.0, profile, trace, rows)
                self.total_traversals += 1
                self.last_trajectories.append({
                    "iteration": self.iterations + 1,
                    "traversal": self.total_traversals,
                    "traverser": traverser,
                    "chance": label,
                    "chance_probability": chance_probability,
                    "opponent_samples": trace,
                })
                # Retain only the most recent logical iteration's two frozen
                # snapshots.  Keeping every full profile would make a long
                # research run consume memory proportional to iterations.
                if offset == iterations - 1:
                    self.last_traversal_profiles.append({
                        "iteration": self.iterations + 1,
                        "traversal": self.total_traversals,
                        "traverser": traverser,
                        "profile": {key: dict(strategy) for key, strategy in sorted(profile.items())},
                    })
                if rows is not None:
                    self.last_diagnostic.extend(rows)
            self.iterations += 1
        self.last_runtime_seconds = perf_counter() - started
        self._assert_numerical_safety()
        return self

    def _assert_numerical_safety(self) -> None:
        for node in self.infosets.values():
            if not all(isfinite(value) for value in node.regrets.values()):
                raise AssertionError("non-finite MCCFR regret")
            if not all(isfinite(value) for value in node.strategy_sum.values()):
                raise AssertionError("non-finite MCCFR strategy sum")
            strategy = node.average()
            if not all(isfinite(value) and value >= 0.0 for value in strategy.values()) or abs(sum(strategy.values()) - 1.0) > 1e-12:
                raise AssertionError("invalid MCCFR average strategy")

    def average_strategy(self) -> dict[str, dict[Action, float]]:
        return {key: node.average() for key, node in sorted(self.infosets.items())}

    def diagnostics(self, all_information_sets: Iterable[str] = ()) -> dict[str, object]:
        known = set(all_information_sets)
        memory = sys.getsizeof(self.infosets)
        for node in self.infosets.values():
            memory += sys.getsizeof(node) + sys.getsizeof(node.regrets) + sys.getsizeof(node.strategy_sum)
        return {
            "seed": self.seed,
            "iterations": self.iterations,
            "traversals": self.total_traversals,
            "traversals_per_iteration": self.total_traversals / self.iterations if self.iterations else 0.0,
            "visited_nodes": self.total_visited_nodes,
            "visited_nodes_per_iteration": self.total_visited_nodes / self.iterations if self.iterations else 0.0,
            "full_tree_node_count": self.full_tree_node_count,
            "fraction_full_tree_visited_per_iteration": (
                self.total_visited_nodes / (self.iterations * self.full_tree_node_count)
                if self.iterations and self.full_tree_node_count else None
            ),
            "information_sets_touched": len(self.infosets),
            "estimated_infoset_memory_bytes": memory,
            "zero_visit_information_sets": sorted(known - set(self.infoset_visit_counts)),
            "chance_sample_counts": dict(sorted(self.chance_sample_counts.items())),
            "future_chance_sample_counts": dict(sorted(self.future_chance_sample_counts.items())),
            "action_sample_counts": dict(sorted(self.action_sample_counts.items())),
            "information_set_visit_frequencies": dict(sorted(self.infoset_visit_counts.items())),
            "finite": True,
        }
