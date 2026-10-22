"""Deterministic statistical evaluation for accepted heads-up strategies.

Persistent matches are the statistical unit in ``persistent_match`` mode;
independently reset hands are the unit in ``independent`` mode.  Bootstrap
randomness is deliberately local to this module and never reaches poker RNGs.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, Sequence

from .bots import BOT_TYPES
from .engine import HandEngine
from .history import validate_hand_history
from .match import MatchConfig, run_match


EVALUATION_SCHEMA_VERSION = "1.0"
SMALL_SAMPLE_UNIT_THRESHOLD = 30
EvaluationMode = Literal["independent", "persistent_match"]
Orientation = Literal["strategy_as_a", "strategy_as_b"]


class EvaluationAccountingError(RuntimeError):
    """Raised immediately when engine output violates conservation/history."""


@dataclass(frozen=True)
class EvaluationConfig:
    mode: EvaluationMode = "persistent_match"
    bot_a: str = "expert"
    bot_b: str = "random"
    starting_stack: int = 10_000
    small_blind: int = 50
    big_blind: int = 100
    max_hands: int = 100
    sample_count: int = 100
    base_seed: int = 10_000
    equity_iterations: int = 100
    seat_swap: bool = True
    bootstrap_resamples: int = 2_000
    statistics_seed: int = 91_001
    confidence_level: float = 0.95

    def __post_init__(self) -> None:
        if self.mode not in {"independent", "persistent_match"}:
            raise ValueError("mode must be independent or persistent_match")
        if self.bot_a not in BOT_TYPES or self.bot_b not in BOT_TYPES:
            raise ValueError("bot names must identify registered built-in bots")
        integer_values = {
            "starting_stack": self.starting_stack,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "max_hands": self.max_hands,
            "sample_count": self.sample_count,
            "base_seed": self.base_seed,
            "equity_iterations": self.equity_iterations,
            "bootstrap_resamples": self.bootstrap_resamples,
            "statistics_seed": self.statistics_seed,
        }
        if any(type(value) is not int for value in integer_values.values()):
            raise ValueError("integer evaluation fields must be integers")
        if self.starting_stack <= 0:
            raise ValueError("starting_stack must be positive")
        if self.small_blind <= 0 or self.big_blind <= 0:
            raise ValueError("blinds must be positive")
        if self.small_blind > self.big_blind:
            raise ValueError("small_blind cannot exceed big_blind")
        if self.max_hands <= 0:
            raise ValueError("max_hands must be positive")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if self.equity_iterations <= 0:
            raise ValueError("equity_iterations must be positive")
        if self.bootstrap_resamples <= 0:
            raise ValueError("bootstrap_resamples must be positive")
        if not isinstance(self.seat_swap, bool):
            raise ValueError("seat_swap must be boolean")
        if not isinstance(self.confidence_level, (int, float)) or not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationUnit:
    seed: int
    orientation: Orientation
    strategy_seat: Literal["a", "b"]
    hands_played: int
    net_chips: int
    hand_net_chips: tuple[int, ...]
    result: Literal["win", "loss", "tie"]
    illegal_actions: int = 0
    fallback_actions: int = 0
    exceptions: int = 0
    termination_reason: str | None = None
    adaptive_decisions: int = 0
    profile_bearing_decisions: int = 0
    exploit_activations: int = 0
    activation_categories: tuple[tuple[str, int], ...] = ()

    def as_dict(self, big_blind: int) -> dict[str, Any]:
        value = asdict(self)
        value["hand_net_chips"] = list(self.hand_net_chips)
        value["activation_categories"] = dict(self.activation_categories)
        value["net_big_blinds"] = net_big_blinds(self.net_chips, big_blind)
        return value


def seed_schedule(config: EvaluationConfig) -> tuple[int, ...]:
    """Return seeds without creating or advancing any poker RNG."""
    return tuple(config.base_seed + index for index in range(config.sample_count))


def orientations(config: EvaluationConfig) -> tuple[Orientation, ...]:
    return ("strategy_as_a", "strategy_as_b") if config.seat_swap else ("strategy_as_a",)


def net_big_blinds(net_chips: int | float, big_blind: int) -> float:
    if big_blind <= 0:
        raise ValueError("big_blind must be positive")
    return float(net_chips) / big_blind


def bb_per_100(net_chips: int | float, big_blind: int, hands_played: int) -> float:
    """Return ``100 * total_net_bb / hands_played``, or zero for no hands."""
    if hands_played <= 0:
        return 0.0
    return 100.0 * net_big_blinds(net_chips, big_blind) / hands_played


def _derived_seed(seed: int, role: str) -> int:
    digest = hashlib.sha256(f"evaluation-1.0:{seed}:{role}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _bot(name: str, seed: int, role: str, equity_iterations: int):
    return BOT_TYPES[name](
        seed=_derived_seed(seed, role), equity_iterations=equity_iterations
    )


def _adaptive_diagnostics(bot: Any) -> dict[str, Any]:
    trace = list(getattr(bot, "decision_trace", ()))
    categories = Counter(
        str(item["category"])
        for item in trace
        if item.get("exploit_applied") and item.get("category")
    )
    return {
        "adaptive_decisions": int(getattr(bot, "decision_count", 0)),
        "profile_bearing_decisions": sum(
            int(int(item.get("profile_hands_observed", 0)) > 0) for item in trace
        ),
        "exploit_activations": int(getattr(bot, "exploit_activations", 0)),
        "activation_categories": tuple(sorted(categories.items())),
    }


def _validate_history_and_conservation(history, net_a: int, net_b: int) -> None:
    if net_a + net_b != 0:
        raise EvaluationAccountingError(
            f"zero-sum conservation failed: {net_a} + {net_b}"
        )
    validation = validate_hand_history(history)
    if not validation.valid:
        raise EvaluationAccountingError(
            "history validation failed: " + "; ".join(validation.errors)
        )


def _run_independent_unit(
    config: EvaluationConfig, seed: int, orientation: Orientation
) -> EvaluationUnit:
    strategy_as_a = orientation == "strategy_as_a"
    strategy = _bot(config.bot_a, seed, "strategy", config.equity_iterations)
    opponent = _bot(config.bot_b, seed, "opponent", config.equity_iterations)
    first, second = (strategy, opponent) if strategy_as_a else (opponent, strategy)
    engine = HandEngine(
        first,
        second,
        starting_stacks={"a": config.starting_stack, "b": config.starting_stack},
        bb=config.big_blind,
        small_blind=config.small_blind,
        seed=seed,
        simulation_seed=seed,
        button="a",
        hand_id=f"evaluation-{seed}-{orientation}",
    )
    result = engine.play()
    net_a = result["stacks"]["a"] - config.starting_stack
    net_b = result["stacks"]["b"] - config.starting_stack
    _validate_history_and_conservation(result["history"], net_a, net_b)
    net = net_a if strategy_as_a else net_b
    diagnostics = _adaptive_diagnostics(strategy)
    return EvaluationUnit(
        seed=seed,
        orientation=orientation,
        strategy_seat="a" if strategy_as_a else "b",
        hands_played=1,
        net_chips=net,
        hand_net_chips=(net,),
        result="win" if net > 0 else "loss" if net < 0 else "tie",
        illegal_actions=result["illegal_actions"],
        fallback_actions=len(result["illegal_diagnostics"]),
        **diagnostics,
    )


def _run_persistent_unit(
    config: EvaluationConfig, seed: int, orientation: Orientation
) -> EvaluationUnit:
    strategy_as_a = orientation == "strategy_as_a"
    strategy = _bot(config.bot_a, seed, "strategy", config.equity_iterations)
    opponent = _bot(config.bot_b, seed, "opponent", config.equity_iterations)
    first, second = (strategy, opponent) if strategy_as_a else (opponent, strategy)
    result = run_match(
        first,
        second,
        MatchConfig(
            starting_stack_a=config.starting_stack,
            starting_stack_b=config.starting_stack,
            small_blind=config.small_blind,
            big_blind=config.big_blind,
            max_hands=config.max_hands,
            seed=seed,
        ),
    )
    if result.bot_a_net_chips + result.bot_b_net_chips != 0:
        raise EvaluationAccountingError("match zero-sum conservation failed")
    for hand in result.per_hand_summaries:
        _validate_history_and_conservation(
            hand.history, hand.net_chips["a"], hand.net_chips["b"]
        )
    seat = "a" if strategy_as_a else "b"
    net = result.bot_a_net_chips if strategy_as_a else result.bot_b_net_chips
    hand_nets = tuple(hand.net_chips[seat] for hand in result.per_hand_summaries)
    if sum(hand_nets) != net:
        raise EvaluationAccountingError("per-hand nets do not equal match net")
    diagnostics = _adaptive_diagnostics(strategy)
    return EvaluationUnit(
        seed=seed,
        orientation=orientation,
        strategy_seat=seat,
        hands_played=result.hands_played,
        net_chips=net,
        hand_net_chips=hand_nets,
        result="win" if net > 0 else "loss" if net < 0 else "tie",
        illegal_actions=result.illegal_action_count,
        fallback_actions=result.fallback_diagnostic_count,
        termination_reason=result.termination_reason,
        **diagnostics,
    )


def run_raw_evaluation(config: EvaluationConfig) -> tuple[EvaluationUnit, ...]:
    runner = _run_independent_unit if config.mode == "independent" else _run_persistent_unit
    return tuple(
        runner(config, seed, orientation)
        for seed in seed_schedule(config)
        for orientation in orientations(config)
    )


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def _sample_stdev(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def _percentile_interval(values: Sequence[float], confidence_level: float) -> dict[str, float]:
    ordered = sorted(values)
    tail = (1.0 - confidence_level) / 2.0
    return {
        "lower": _quantile(ordered, tail),
        "upper": _quantile(ordered, 1.0 - tail),
        "confidence_level": float(confidence_level),
    }


def bootstrap_interval(
    observations: Sequence[float],
    *,
    resamples: int,
    statistics_seed: int,
    confidence_level: float = 0.95,
) -> dict[str, float]:
    """Deterministic percentile CI for an arithmetic mean."""
    if not observations:
        return {"lower": 0.0, "upper": 0.0, "confidence_level": float(confidence_level)}
    rng = random.Random(statistics_seed)
    size = len(observations)
    estimates = [
        _mean([observations[rng.randrange(size)] for _ in range(size)])
        for _ in range(resamples)
    ]
    return _percentile_interval(estimates, confidence_level)


def _bootstrap_bb100(
    units: Sequence[EvaluationUnit], config: EvaluationConfig, seed_offset: int = 0
) -> dict[str, float]:
    if not units:
        return {"lower": 0.0, "upper": 0.0, "confidence_level": config.confidence_level}
    rng = random.Random(config.statistics_seed + seed_offset)
    size = len(units)
    estimates: list[float] = []
    for _ in range(config.bootstrap_resamples):
        sample = [units[rng.randrange(size)] for _ in range(size)]
        estimates.append(
            bb_per_100(
                sum(unit.net_chips for unit in sample),
                config.big_blind,
                sum(unit.hands_played for unit in sample),
            )
        )
    return _percentile_interval(estimates, config.confidence_level)


def _basic_metrics(units: Sequence[EvaluationUnit], big_blind: int) -> dict[str, Any]:
    hands = sum(unit.hands_played for unit in units)
    net_chips = sum(unit.net_chips for unit in units)
    unit_bb = [net_big_blinds(unit.net_chips, big_blind) for unit in units]
    hand_bb = [
        net_big_blinds(value, big_blind)
        for unit in units
        for value in unit.hand_net_chips
    ]
    deviation = _sample_stdev(unit_bb)
    wins = [value for value in unit_bb if value > 0]
    losses = [value for value in unit_bb if value < 0]
    return {
        "hands_played": hands,
        "evaluation_units": len(units),
        "wins": sum(unit.result == "win" for unit in units),
        "losses": sum(unit.result == "loss" for unit in units),
        "ties": sum(unit.result == "tie" for unit in units),
        "net_chips": net_chips,
        "net_big_blinds": net_big_blinds(net_chips, big_blind),
        "bb_per_100": bb_per_100(net_chips, big_blind, hands),
        "mean_bb_per_hand": _mean(hand_bb),
        "median_bb_per_hand": _median(hand_bb),
        "mean_net_bb_per_evaluation_unit": _mean(unit_bb),
        "standard_deviation_net_bb_per_evaluation_unit": deviation,
        "standard_error_net_bb_per_evaluation_unit": deviation / math.sqrt(len(unit_bb)) if unit_bb else 0.0,
        "average_winning_unit_size_bb": _mean(wins),
        "average_losing_unit_size_bb": _mean(losses),
        "illegal_actions": sum(unit.illegal_actions for unit in units),
        "fallback_actions": sum(unit.fallback_actions for unit in units),
        "exceptions": sum(unit.exceptions for unit in units),
    }


def aggregate_evaluation(
    units: Sequence[EvaluationUnit], config: EvaluationConfig
) -> dict[str, Any]:
    metrics = _basic_metrics(units, config.big_blind)
    unit_bb = [net_big_blinds(unit.net_chips, config.big_blind) for unit in units]
    metrics["confidence_intervals"] = {
        "mean_net_bb_per_evaluation_unit": bootstrap_interval(
            unit_bb,
            resamples=config.bootstrap_resamples,
            statistics_seed=config.statistics_seed,
            confidence_level=config.confidence_level,
        ),
        "bb_per_100": _bootstrap_bb100(units, config, 1),
    }
    by_orientation = {
        orientation: _basic_metrics(
            [unit for unit in units if unit.orientation == orientation], config.big_blind
        )
        for orientation in orientations(config)
    }
    metrics["seat_results"] = {
        "seat_a": by_orientation.get("strategy_as_a", _basic_metrics([], config.big_blind)),
        "seat_b": by_orientation.get("strategy_as_b", _basic_metrics([], config.big_blind)),
        "combined": _basic_metrics(units, config.big_blind),
    }
    if config.mode == "persistent_match":
        lengths = [unit.hands_played for unit in units]
        metrics.update(
            {
                "matches": len(units),
                "average_hands_per_match": _mean(lengths),
                "median_hands_per_match": _median(lengths),
                "elimination_terminations": sum(unit.termination_reason == "elimination" for unit in units),
                "hand_limit_terminations": sum(unit.termination_reason == "hand_limit" for unit in units),
            }
        )
    adaptive_decisions = sum(unit.adaptive_decisions for unit in units)
    if adaptive_decisions:
        categories: Counter[str] = Counter()
        for unit in units:
            categories.update(dict(unit.activation_categories))
        activations = sum(unit.exploit_activations for unit in units)
        metrics["adaptive_diagnostics"] = {
            "adaptive_decisions": adaptive_decisions,
            "profile_bearing_decisions": sum(unit.profile_bearing_decisions for unit in units),
            "exploit_activations": activations,
            "activation_rate": activations / adaptive_decisions,
            "activation_categories": dict(sorted(categories.items())),
        }
    return _json_safe(metrics)


def evaluation_report(config: EvaluationConfig) -> dict[str, Any]:
    units = run_raw_evaluation(config)
    warning = len(units) < SMALL_SAMPLE_UNIT_THRESHOLD
    metrics = aggregate_evaluation(units, config)
    warnings = (
        [{"code": "insufficient_evaluation_units", "threshold": SMALL_SAMPLE_UNIT_THRESHOLD, "observed": len(units)}]
        if warning
        else []
    )
    if metrics["illegal_actions"]:
        warnings.append({"code": "illegal_actions_observed", "count": metrics["illegal_actions"]})
    if metrics["fallback_actions"]:
        warnings.append({"code": "fallback_actions_observed", "count": metrics["fallback_actions"]})
    if metrics["exceptions"]:
        warnings.append({"code": "exceptions_observed", "count": metrics["exceptions"]})
    report = {
        "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
        "report_type": "strategy_evaluation",
        "configuration": config.as_dict(),
        "methodology": {
            "evaluation_mode": config.mode,
            "statistical_unit": "independently_reset_hand" if config.mode == "independent" else "whole_persistent_match",
            "seat_method": "seat-swapped orientation-paired matched seed schedule" if config.seat_swap else "strategy as seat A only",
            "duplicate_deal_pairing": False,
            "confidence_method": "deterministic percentile bootstrap",
            "bootstrap_resamples": config.bootstrap_resamples,
            "statistics_seed": config.statistics_seed,
        },
        "sample": {
            "number_of_seeds": len(seed_schedule(config)),
            "seeds": list(seed_schedule(config)),
            "seat_orientations": list(orientations(config)),
            "hands": sum(unit.hands_played for unit in units),
            "evaluation_units": len(units),
            "matches": len(units) if config.mode == "persistent_match" else 0,
        },
        "metrics": metrics,
        "accounting": {
            "zero_sum_validation": "passed",
            "conservation_failures": 0,
            "validated_histories": sum(unit.hands_played for unit in units),
        },
        "sample_warning": warning,
        "warnings": warnings,
        "raw_evaluation_units": [unit.as_dict(config.big_blind) for unit in units],
    }
    return _json_safe(report)


def interpret_interval(estimate: float, interval: dict[str, float]) -> str:
    if interval["lower"] > 0:
        return "positive_estimate_supported"
    if interval["upper"] < 0:
        return "negative_estimate_supported"
    if estimate > 0:
        return "positive_estimate_uncertain"
    if estimate < 0:
        return "negative_estimate_uncertain"
    return "approximately_inconclusive"


def _comparison_delta_ci(
    control: Sequence[EvaluationUnit],
    treatment: Sequence[EvaluationUnit],
    config: EvaluationConfig,
) -> tuple[dict[str, float], list[float]]:
    control_map = {(unit.seed, unit.orientation): unit for unit in control}
    treatment_map = {(unit.seed, unit.orientation): unit for unit in treatment}
    keys = sorted(set(control_map) & set(treatment_map))
    if len(keys) != len(control) or len(keys) != len(treatment):
        raise ValueError("comparison schedules do not correspond one-to-one")
    raw_delta_bb = [
        net_big_blinds(treatment_map[key].net_chips - control_map[key].net_chips, config.big_blind)
        for key in keys
    ]
    rng = random.Random(config.statistics_seed + 10_000)
    estimates: list[float] = []
    for _ in range(config.bootstrap_resamples):
        sampled = [keys[rng.randrange(len(keys))] for _ in keys]
        t_net = sum(treatment_map[key].net_chips for key in sampled)
        c_net = sum(control_map[key].net_chips for key in sampled)
        t_hands = sum(treatment_map[key].hands_played for key in sampled)
        c_hands = sum(control_map[key].hands_played for key in sampled)
        estimates.append(
            bb_per_100(t_net, config.big_blind, t_hands)
            - bb_per_100(c_net, config.big_blind, c_hands)
        )
    return _percentile_interval(estimates, config.confidence_level), raw_delta_bb


def compare_strategies(
    control: str,
    treatment: str,
    opponent: str,
    config: EvaluationConfig,
) -> dict[str, Any]:
    for name in (control, treatment, opponent):
        if name not in BOT_TYPES:
            raise ValueError(f"unknown bot: {name}")
    control_config = replace(config, bot_a=control, bot_b=opponent)
    treatment_config = replace(config, bot_a=treatment, bot_b=opponent)
    control_units = run_raw_evaluation(control_config)
    treatment_units = run_raw_evaluation(treatment_config)
    control_metrics = aggregate_evaluation(control_units, control_config)
    treatment_metrics = aggregate_evaluation(treatment_units, treatment_config)
    delta = treatment_metrics["bb_per_100"] - control_metrics["bb_per_100"]
    interval, raw_delta_bb = _comparison_delta_ci(
        control_units, treatment_units, config
    )
    warning = len(control_units) < SMALL_SAMPLE_UNIT_THRESHOLD
    warnings = (
        [{"code": "insufficient_evaluation_units", "threshold": SMALL_SAMPLE_UNIT_THRESHOLD, "observed": len(control_units)}]
        if warning
        else []
    )
    total_illegal = control_metrics["illegal_actions"] + treatment_metrics["illegal_actions"]
    total_fallback = control_metrics["fallback_actions"] + treatment_metrics["fallback_actions"]
    total_exceptions = control_metrics["exceptions"] + treatment_metrics["exceptions"]
    if total_illegal:
        warnings.append({"code": "illegal_actions_observed", "count": total_illegal})
    if total_fallback:
        warnings.append({"code": "fallback_actions_observed", "count": total_fallback})
    if total_exceptions:
        warnings.append({"code": "exceptions_observed", "count": total_exceptions})
    report = {
        "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
        "report_type": "strategy_comparison",
        "configuration": control_config.as_dict(),
        "treatment_configuration": treatment_config.as_dict(),
        "comparison": {"control": control, "treatment": treatment, "opponent": opponent, "delta_definition": f"{treatment} - {control}"},
        "methodology": {
            "evaluation_mode": config.mode,
            "statistical_unit": "independently_reset_hand" if config.mode == "independent" else "whole_persistent_match",
            "comparison_pairing": "matched-seed, matched-orientation schedule",
            "duplicate_deal_pairing": False,
            "pairing_limitation": "strategy actions can change random trajectories and persistent match lengths; this is not duplicate-deal poker",
            "confidence_method": "deterministic matched-schedule percentile bootstrap",
            "bootstrap_resamples": config.bootstrap_resamples,
            "statistics_seed": config.statistics_seed,
        },
        "sample": {
            "number_of_seeds": config.sample_count,
            "seeds": list(seed_schedule(config)),
            "seat_orientations": list(orientations(config)),
            "evaluation_units_per_strategy": len(control_units),
            "control_hands": control_metrics["hands_played"],
            "treatment_hands": treatment_metrics["hands_played"],
        },
        "absolute_results": {"control": control_metrics, "treatment": treatment_metrics},
        "delta": {
            "bb_per_100": delta,
            "confidence_interval": interval,
            "raw_matched_unit_delta_bb": raw_delta_bb,
            "interpretation": interpret_interval(delta, interval),
        },
        "accounting": {"zero_sum_validation": "passed", "conservation_failures": 0},
        "sample_warning": warning,
        "warnings": warnings,
    }
    return _json_safe(report)


def strategy_matrix(
    strategies: Sequence[str], opponents: Sequence[str], config: EvaluationConfig
) -> dict[str, Any]:
    rows = []
    for strategy in strategies:
        for opponent in opponents:
            report = evaluation_report(replace(config, bot_a=strategy, bot_b=opponent))
            rows.append(
                {
                    "strategy": strategy,
                    "opponent": opponent,
                    "hands": report["sample"]["hands"],
                    "evaluation_units": report["sample"]["evaluation_units"],
                    "bb_per_100": report["metrics"]["bb_per_100"],
                    "confidence_interval": report["metrics"]["confidence_intervals"]["bb_per_100"],
                    "sample_warning": report["sample_warning"],
                }
            )
    return _json_safe(
        {
            "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
            "report_type": "strategy_matrix",
            "configuration": config.as_dict(),
            "weighting": "no pooled effect; every strategy-opponent row is reported separately",
            "rows": rows,
        }
    )


def regression_metadata(current: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    current_metrics = current["metrics"]
    reference_metrics = reference["metrics"]
    effect = current_metrics["bb_per_100"] - reference_metrics["bb_per_100"]
    current_ci = current_metrics["confidence_intervals"]["bb_per_100"]
    reference_ci = reference_metrics["confidence_intervals"]["bb_per_100"]
    return _json_safe(
        {
            "effect_bb_per_100": effect,
            "direction": "positive" if effect > 0 else "negative" if effect < 0 else "unchanged",
            "current_sample_units": current_metrics["evaluation_units"],
            "reference_sample_units": reference_metrics["evaluation_units"],
            "uncertainty_intervals_overlap": not (
                current_ci["upper"] < reference_ci["lower"]
                or reference_ci["upper"] < current_ci["lower"]
            ),
            "automatic_failure": False,
            "note": "Phase 3D1 metadata only; no noisy performance CI gate is applied",
        }
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def json_report_text(report: dict[str, Any]) -> str:
    return json.dumps(_json_safe(report), indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_json_report(
    report: dict[str, Any], path: str | Path, *, overwrite: bool = False
) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        raise ValueError(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json_report_text(report), encoding="utf-8")
    return target
