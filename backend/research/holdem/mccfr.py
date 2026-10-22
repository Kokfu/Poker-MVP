"""External-sampling MCCFR for the fixed Phase 4D research subgame only."""
from __future__ import annotations

from time import perf_counter
import sys

from .cfr import HoldemSubgameCFRTrainer
from .subgame import HoldemSubgameState, chance_states
from ..mccfr import ExternalSamplingMCCFRTrainer


class HoldemSubgameExternalSamplingMCCFRTrainer(ExternalSamplingMCCFRTrainer):
    def __init__(self, seed: int = 0, roots: tuple[HoldemSubgameState, ...] | None = None) -> None:
        supplied_roots = roots or chance_states()
        super().__init__(
            supplied_roots, seed,
            action_label=lambda action: action.label,
            chance_label=lambda state: "/".join((*state.player0_cards, *state.player1_cards)),
            full_tree_node_count=3510 if len(supplied_roots) == 90 else None,
        )

    def _distribution(self, state: HoldemSubgameState) -> dict[object, float]:
        node = self.infosets.get(state.information_set())
        if node is None:
            actions = tuple(state.legal_actions)
            return {action: 1.0 / len(actions) for action in actions}
        return node.average()

    def profile_ev(self) -> float:
        def walk(state: HoldemSubgameState) -> float:
            if state.terminal:
                return state.utility_p0()
            distribution = self._distribution(state)
            return sum(distribution[action] * walk(state.apply(action)) for action in state.legal_actions)
        return sum(walk(root) for root in self.roots) / len(self.roots)

    def all_information_set_keys(self) -> tuple[str, ...]:
        # This exact-control object is used only to label never-sampled sets in
        # diagnostics; it is never trained or used by the MCCFR traversal.
        return tuple(HoldemSubgameCFRTrainer(roots=self.roots).infosets)

    def strategy_table(self) -> list[dict[str, object]]:
        return [{
            "information_set": key,
            "player": node.player,
            "legal_abstract_actions": [action.label for action in node.actions],
            "cumulative_regrets": {action.label: value for action, value in node.regrets.items()},
            "average_strategy": {action.label: value for action, value in node.average().items()},
        } for key, node in sorted(self.infosets.items())]


def scaling_report(iterations: int = 1_000, seed: int = 7) -> dict[str, object]:
    """Operational comparison, not an exploitability claim for the full subgame."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    exact = HoldemSubgameCFRTrainer("vanilla")
    split = max(1, iterations // 2)
    exact_started = perf_counter()
    exact.train(split)
    exact_before = exact.average_strategy()
    exact.train(iterations - split)
    exact_elapsed = perf_counter() - exact_started
    sampled = HoldemSubgameExternalSamplingMCCFRTrainer(seed)
    sampled_started = perf_counter()
    sampled.train(split)
    sampled_before = sampled.average_strategy()
    sampled.train(iterations - split)
    sampled_elapsed = perf_counter() - sampled_started
    diagnostics = sampled.diagnostics(sampled.all_information_set_keys())
    return {
        "phase_4e_research_schema_version": "1.0",
        "scope": "fixed Phase 4D flop subgame only; no full-subgame exploitability is reported",
        "iterations": iterations,
        "exact_vanilla_cfr": {
            "nodes_visited_per_iteration": 3510,
            "information_sets": len(exact.infosets),
            "profile_ev_player0": exact.profile_ev(),
            "average_strategy_l1_change": _l1(exact_before, exact.average_strategy()),
            "runtime_seconds": exact_elapsed,
            "iterations_per_second": iterations / exact_elapsed if exact_elapsed else float("inf"),
            "estimated_infoset_memory_bytes": _infoset_memory(exact.infosets),
        },
        "external_sampling_mccfr": {
            "seed": seed,
            "traversals": diagnostics["traversals"],
            "traversals_per_iteration": diagnostics["traversals_per_iteration"],
            "nodes_visited": diagnostics["visited_nodes"],
            "nodes_visited_per_iteration": diagnostics["visited_nodes_per_iteration"],
            "fraction_full_tree_visited_per_iteration": diagnostics["fraction_full_tree_visited_per_iteration"],
            "information_sets_touched": diagnostics["information_sets_touched"],
            "zero_visit_information_sets": diagnostics["zero_visit_information_sets"],
            "profile_ev_player0": sampled.profile_ev(),
            "average_strategy_l1_change": _l1(sampled_before, sampled.average_strategy()),
            "runtime_seconds": sampled_elapsed,
            "iterations_per_second": iterations / sampled_elapsed if sampled_elapsed else float("inf"),
            "estimated_infoset_memory_bytes": diagnostics["estimated_infoset_memory_bytes"],
            "sampling_diagnostics": diagnostics,
        },
    }


def _l1(before: dict[str, dict[object, float]], after: dict[str, dict[object, float]]) -> float:
    return sum(
        abs(after.get(key, {}).get(action, 0.0) - before.get(key, {}).get(action, 0.0))
        for key in set(before) | set(after)
        for action in set(before.get(key, {})) | set(after.get(key, {}))
    )


def _infoset_memory(infosets: dict[str, object]) -> int:
    total = sys.getsizeof(infosets)
    for node in infosets.values():
        total += sys.getsizeof(node)
        total += sys.getsizeof(node.regrets) + sys.getsizeof(node.strategy_sum)
    return total
