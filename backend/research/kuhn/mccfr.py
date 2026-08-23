"""Seeded external-sampling MCCFR control for canonical Kuhn Poker."""
from __future__ import annotations

from time import perf_counter
from statistics import mean, stdev

from ..mccfr import ExternalSamplingMCCFRTrainer
from .evaluation import metrics
from .game import DEALS, KuhnState


TARGET_VALUE = -1.0 / 18.0


class KuhnExternalSamplingMCCFRTrainer(ExternalSamplingMCCFRTrainer):
    def __init__(self, seed: int = 0) -> None:
        super().__init__(
            (KuhnState(deal) for deal in DEALS), seed,
            action_label=lambda action: action.value,
            chance_label=lambda state: "".join(card.value for card in state.cards),
            full_tree_node_count=54,
        )

    def strategy_table(self) -> list[dict[str, object]]:
        rows = []
        for key, node in sorted(self.infosets.items()):
            rows.append({
                "information_set": key,
                "player": node.player,
                "legal_actions": [action.value for action in node.actions],
                "cumulative_regrets": {action.value: value for action, value in node.regrets.items()},
                "average_strategy": {action.value: value for action, value in node.average().items()},
            })
        return rows


def convergence_report(
    checkpoints: tuple[int, ...] = (100, 1_000, 10_000, 100_000),
    seeds: tuple[int, ...] = (7, 17, 29),
) -> dict[str, object]:
    """Exact-evaluation report for deterministic seeded MCCFR replicates."""
    ordered = tuple(sorted(set(checkpoints)))
    if not ordered or ordered[0] < 1 or not seeds:
        raise ValueError("positive checkpoints and at least one seed are required")
    reports: list[dict[str, object]] = []
    for seed in seeds:
        trainer = KuhnExternalSamplingMCCFRTrainer(seed)
        previous = 0
        for checkpoint in ordered:
            delta = checkpoint - previous
            started = perf_counter()
            trainer.train(delta)
            elapsed = perf_counter() - started
            previous = checkpoint
            measured = metrics(trainer.average_strategy(), trainer.average_strategy())
            reports.append({
                "seed": seed,
                "iterations": checkpoint,
                "player0_ev": measured["player0_ev"],
                "value_error": abs(measured["player0_ev"] - TARGET_VALUE),
                "br0": measured["br0"],
                "br1_as_u0": measured["br1_as_u0"],
                "nashconv": measured["nashconv"],
                "exploitability": measured["exploitability"],
                "runtime_seconds": elapsed,
                "iterations_per_second": delta / elapsed if elapsed else float("inf"),
            })
    summaries = []
    for checkpoint in ordered:
        rows = [row for row in reports if row["iterations"] == checkpoint]
        summaries.append({
            "iterations": checkpoint,
            "seed_count": len(rows),
            "player0_ev": _summary([float(row["player0_ev"]) for row in rows]),
            "value_error": _summary([float(row["value_error"]) for row in rows]),
            "nashconv": _summary([float(row["nashconv"]) for row in rows]),
            "exploitability": _summary([float(row["exploitability"]) for row in rows]),
        })
    return {
        "phase_4e_research_schema_version": "1.0",
        "algorithm": "external_sampling_mccfr",
        "game": "canonical-three-card-kuhn",
        "target_player0_value": TARGET_VALUE,
        "checkpoints": list(ordered),
        "seeds": list(seeds),
        "reports": reports,
        "checkpoint_seed_summaries": summaries,
        "metrics_convention": "exact six-deal EV; information-set best responses; NashConv=BR0-BR1_as_u0; exploitability=NashConv/2",
    }


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "mean": mean(values),
        "min": min(values),
        "max": max(values),
        "standard_deviation": stdev(values) if len(values) > 1 else 0.0,
    }
