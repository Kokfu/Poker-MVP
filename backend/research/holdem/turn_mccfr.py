"""Phase 4F adapter for the accepted external-sampling MCCFR core."""
from __future__ import annotations

from time import perf_counter

from ..mccfr import ExternalSamplingMCCFRTrainer
from .cfr import HoldemSubgameCFRTrainer
from .turn_subgame import TURN_RESEARCH_DECK, TurnHoldemState, turn_chance_states


class TurnChanceExternalSamplingMCCFRTrainer(ExternalSamplingMCCFRTrainer):
    """Samples a private deal at root and one conditional turn when reached."""

    def __init__(self, seed: int = 0, roots: tuple[TurnHoldemState, ...] | None = None) -> None:
        supplied = roots or turn_chance_states()
        super().__init__(
            supplied, seed,
            action_label=lambda action: action.label,
            chance_label=lambda state: "/".join((*state.player0_cards, *state.player1_cards)),
        )
        self.infoset_streets: dict[str, str] = {}

    def _node(self, state: TurnHoldemState):
        node = super()._node(state)
        street = state.street
        prior = self.infoset_streets.setdefault(node.key, street)
        if prior != street:
            raise AssertionError("information set aliases distinct streets")
        return node

    def _distribution(self, state: TurnHoldemState) -> dict[object, float]:
        node = self.infosets.get(state.information_set())
        if node is None:
            actions = tuple(state.legal_actions)
            return {action: 1.0 / len(actions) for action in actions}
        return node.average()

    def profile_ev(self) -> float:
        def walk(state: TurnHoldemState) -> float:
            if state.terminal:
                return state.utility_p0()
            if state.chance:
                return sum(probability * walk(child) for _, child, probability in state.chance_outcomes())
            distribution = self._distribution(state)
            return sum(distribution[action] * walk(state.apply(action)) for action in state.legal_actions)
        return sum(walk(root) for root in self.roots) / len(self.roots)

    def all_information_set_keys(self) -> tuple[str, ...]:
        return tuple(HoldemSubgameCFRTrainer(roots=self.roots).infosets)

    def turn_sampling_diagnostics(self) -> dict[str, object]:
        counts = {card: self.future_chance_sample_counts[card] for card in TURN_RESEARCH_DECK}
        seen = [card for card, count in counts.items() if count]
        return {
            "eligible_turn_cards": list(TURN_RESEARCH_DECK),
            "per_card_sample_counts": counts,
            "unseen_turn_cards": [card for card, count in counts.items() if not count],
            "min_turn_sample_frequency": min(counts.values()),
            "max_turn_sample_frequency": max(counts.values()),
            "all_reachable_turns_seen": len(seen) == len(counts),
        }


def turn_training_report(checkpoints: tuple[int, ...] = (100, 1_000, 10_000), seed: int = 7) -> dict[str, object]:
    if tuple(sorted(set(checkpoints))) != checkpoints or not checkpoints or checkpoints[0] < 1:
        raise ValueError("checkpoints must be sorted positive unique values")
    trainer = TurnChanceExternalSamplingMCCFRTrainer(seed)
    rows = []
    prior = 0
    previous = None
    for checkpoint in checkpoints:
        started = perf_counter()
        trainer.train(checkpoint - prior)
        elapsed = perf_counter() - started
        policy = trainer.average_strategy()
        diagnostics = trainer.diagnostics(trainer.all_information_set_keys())
        rows.append({
            "logical_iterations": checkpoint, "traversals": diagnostics["traversals"],
            "runtime_seconds": elapsed, "iterations_per_second": (checkpoint - prior) / elapsed if elapsed else float("inf"),
            "visited_nodes": diagnostics["visited_nodes"], "nodes_per_iteration": diagnostics["visited_nodes_per_iteration"],
            "information_sets_touched": diagnostics["information_sets_touched"],
            "zero_visit_information_sets": diagnostics["zero_visit_information_sets"],
            "flop_infosets_touched": sum(street == "flop" for street in trainer.infoset_streets.values()),
            "turn_infosets_touched": sum(street == "turn" for street in trainer.infoset_streets.values()),
            "profile_ev_player0": trainer.profile_ev(), "average_strategy_l1_change": _l1(previous, policy) if previous else None,
            "finite": diagnostics["finite"], "turn_sampling": trainer.turn_sampling_diagnostics(),
        })
        previous, prior = policy, checkpoint
    return {"phase_4f_research_schema_version": "1.0", "seed": seed, "checkpoints": rows}


def _l1(before: dict[str, dict[object, float]], after: dict[str, dict[object, float]]) -> float:
    return sum(abs(after.get(key, {}).get(action, 0.0) - before.get(key, {}).get(action, 0.0))
               for key in set(before or {}) | set(after)
               for action in set((before or {}).get(key, {})) | set(after.get(key, {})))
