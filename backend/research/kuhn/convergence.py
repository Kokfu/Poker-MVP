"""Reusable exact convergence reports for deterministic Kuhn CFR algorithms."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from .evaluation import metrics

TARGET_VALUE = -1.0 / 18.0
DEFAULT_CHECKPOINTS = (1, 10, 100, 1_000, 10_000, 100_000)


def comparison_algorithm_metadata(averaging_delay: int = 0) -> dict[str, dict[str, str | int]]:
    """Describe the intentionally different policy-averaging conventions."""
    if averaging_delay < 0:
        raise ValueError("averaging_delay must be non-negative")
    return {
        "vanilla-cfr": {
            "algorithm": "vanilla_cfr",
            "regret_update": "cumulative",
            "averaging": "reach_weighted_unweighted_iterations",
            "weight_formula": "1",
        },
        "cfr-plus": {
            "algorithm": "cfr_plus",
            "regret_update": "cumulative_regret_plus",
            "averaging": "delayed_linear",
            "averaging_delay": averaging_delay,
            "weight_formula": "max(0, iteration - averaging_delay)",
        },
    }


class Trainer(Protocol):
    def train(self, iterations: int) -> object: ...
    def average_strategy(self) -> dict: ...


def checkpoint_report(factory: Callable[[], Trainer], checkpoints: Iterable[int] = DEFAULT_CHECKPOINTS) -> list[dict[str, float | int]]:
    """Train incrementally and evaluate each average policy exactly, not by sampling."""
    ordered = tuple(sorted(set(checkpoints)))
    if not ordered or ordered[0] < 1:
        raise ValueError("checkpoints must be positive")
    trainer = factory()
    previous = 0
    reports: list[dict[str, float | int]] = []
    for checkpoint in ordered:
        trainer.train(checkpoint - previous)
        previous = checkpoint
        measure = metrics(trainer.average_strategy(), trainer.average_strategy())
        reports.append({"iterations": checkpoint, **measure, "value_error": abs(measure["player0_ev"] - TARGET_VALUE)})
    return reports


def comparison_report(algorithms: dict[str, Callable[[], Trainer]], checkpoints: Iterable[int] = DEFAULT_CHECKPOINTS,
                      algorithm_metadata: dict[str, dict[str, str | int]] | None = None) -> dict[str, object]:
    """Produce aligned exact metric rows for any set of deterministic trainers."""
    reports = {name: checkpoint_report(factory, checkpoints) for name, factory in algorithms.items()}
    return {"kuhn_cfr_convergence_schema_version": "1.0", "game": "canonical-three-card-kuhn",
            "target_player0_value": TARGET_VALUE, "checkpoints": list(sorted(set(checkpoints))), "algorithms": reports,
            "algorithm_metadata": algorithm_metadata or {},
            "metrics_convention": "exact six-deal EV; information-set best responses; NashConv=BR0-BR1_as_u0; exploitability=NashConv/2"}
