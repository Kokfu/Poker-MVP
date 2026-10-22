"""Phase 3D1 statistical evaluation contracts."""
from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from simulation.evaluation import (
    EVALUATION_SCHEMA_VERSION,
    SMALL_SAMPLE_UNIT_THRESHOLD,
    EvaluationConfig,
    EvaluationUnit,
    _comparison_delta_ci,
    aggregate_evaluation,
    bb_per_100,
    bootstrap_interval,
    compare_strategies,
    evaluation_report,
    interpret_interval,
    json_report_text,
    net_big_blinds,
    regression_metadata,
    run_raw_evaluation,
    seed_schedule,
    strategy_matrix,
    write_json_report,
)
from simulation.evaluation_cli import main


def config(**updates):
    values = {
        "mode": "independent",
        "sample_count": 2,
        "base_seed": 200,
        "max_hands": 3,
        "equity_iterations": 1,
        "bootstrap_resamples": 31,
        "statistics_seed": 71,
    }
    values.update(updates)
    return EvaluationConfig(**values)


def unit(
    net,
    *,
    seed=1,
    orientation="strategy_as_a",
    hands=1,
    hand_nets=None,
    termination=None,
    adaptive=0,
    profile=0,
    activations=0,
    categories=(),
):
    return EvaluationUnit(
        seed=seed,
        orientation=orientation,
        strategy_seat="a" if orientation == "strategy_as_a" else "b",
        hands_played=hands,
        net_chips=net,
        hand_net_chips=tuple(hand_nets if hand_nets is not None else [net]),
        result="win" if net > 0 else "loss" if net < 0 else "tie",
        termination_reason=termination,
        adaptive_decisions=adaptive,
        profile_bearing_decisions=profile,
        exploit_activations=activations,
        activation_categories=categories,
    )


def test_net_chip_bb_and_bb100_math_and_zero_hands():
    assert sum(item.net_chips for item in (unit(200), unit(-50))) == 150
    assert net_big_blinds(150, 100) == 1.5
    assert bb_per_100(150, 100, 25) == 6.0
    assert bb_per_100(150, 100, 0) == 0.0


def test_wins_losses_ties_sizes_deviation_and_standard_error():
    metrics = aggregate_evaluation(
        [unit(100, seed=1), unit(300, seed=2), unit(-200, seed=3), unit(0, seed=4)],
        config(sample_count=4),
    )
    assert (metrics["wins"], metrics["losses"], metrics["ties"]) == (2, 1, 1)
    assert metrics["average_winning_unit_size_bb"] == 2.0
    assert metrics["average_losing_unit_size_bb"] == -2.0
    assert metrics["standard_deviation_net_bb_per_evaluation_unit"] == pytest.approx(2.081665999)
    assert metrics["standard_error_net_bb_per_evaluation_unit"] == pytest.approx(1.040832999)


def test_zero_units_are_finite_and_json_never_emits_nan_or_infinity():
    metrics = aggregate_evaluation([], config())
    assert metrics["hands_played"] == metrics["evaluation_units"] == 0
    rendered = json.dumps(metrics, allow_nan=False)
    assert "NaN" not in rendered and "Infinity" not in rendered
    assert all(math.isfinite(value) for value in (metrics["bb_per_100"], metrics["standard_error_net_bb_per_evaluation_unit"]))


def test_hand_median_and_unit_statistics_use_the_documented_levels():
    metrics = aggregate_evaluation(
        [unit(200, seed=1, hands=2, hand_nets=[-100, 300]), unit(100, seed=2, hands=1)],
        config(),
    )
    assert metrics["median_bb_per_hand"] == 1.0
    assert metrics["mean_net_bb_per_evaluation_unit"] == 1.5


def test_seat_a_seat_b_and_combined_aggregation():
    metrics = aggregate_evaluation(
        [unit(100, seed=1), unit(-40, seed=1, orientation="strategy_as_b")],
        config(),
    )
    assert metrics["seat_results"]["seat_a"]["net_chips"] == 100
    assert metrics["seat_results"]["seat_b"]["net_chips"] == -40
    assert metrics["seat_results"]["combined"]["net_chips"] == 60


def test_persistent_match_units_and_independent_hand_units_are_distinct():
    persistent = aggregate_evaluation(
        [unit(50, hands=3, hand_nets=[10, 20, 20], termination="hand_limit")],
        config(mode="persistent_match"),
    )
    independent = aggregate_evaluation([unit(50)], config())
    assert persistent["matches"] == persistent["evaluation_units"] == 1
    assert persistent["hands_played"] == 3
    assert independent["evaluation_units"] == independent["hands_played"] == 1
    assert "matches" not in independent


def test_real_engine_evaluation_enforces_zero_sum_and_valid_histories():
    report = evaluation_report(config(sample_count=1))
    assert report["accounting"] == {
        "zero_sum_validation": "passed",
        "conservation_failures": 0,
        "validated_histories": 2,
    }
    assert all(sum(row["hand_net_chips"]) == row["net_chips"] for row in report["raw_evaluation_units"])


def test_bootstrap_is_deterministic_finite_and_constant_is_zero_width():
    first = bootstrap_interval([1.0, 2.0, 8.0], resamples=101, statistics_seed=5)
    second = bootstrap_interval([1.0, 2.0, 8.0], resamples=101, statistics_seed=5)
    other = bootstrap_interval([1.0, 2.0, 8.0], resamples=101, statistics_seed=6)
    assert first == second and first != other
    assert all(math.isfinite(first[key]) for key in ("lower", "upper"))
    assert bootstrap_interval([3.0] * 4, resamples=20, statistics_seed=9) == {
        "lower": 3.0,
        "upper": 3.0,
        "confidence_level": 0.95,
    }


def test_bootstrap_statistics_rng_does_not_change_poker_outcomes():
    cfg = config(sample_count=1)
    before = run_raw_evaluation(cfg)
    bootstrap_interval([1.0, 2.0, 3.0], resamples=100, statistics_seed=999)
    after = run_raw_evaluation(cfg)
    assert before == after


@pytest.mark.parametrize(
    ("delta", "expected"),
    [(100, "positive_estimate_supported"), (-100, "negative_estimate_supported")],
)
def test_constant_matched_delta_has_supported_sign(delta, expected):
    cfg = config(sample_count=2)
    control = [unit(0, seed=1), unit(0, seed=2)]
    treatment = [unit(delta, seed=1), unit(delta, seed=2)]
    interval, raw = _comparison_delta_ci(control, treatment, cfg)
    estimate = bb_per_100(delta * 2, cfg.big_blind, 2)
    assert raw == [delta / cfg.big_blind] * 2
    assert interpret_interval(estimate, interval) == expected


def test_interpretation_when_ci_crosses_zero_is_neutral_and_directional():
    crossing = {"lower": -1.0, "upper": 2.0}
    assert interpret_interval(1.0, crossing) == "positive_estimate_uncertain"
    assert interpret_interval(-1.0, crossing) == "negative_estimate_uncertain"
    assert interpret_interval(0.0, crossing) == "approximately_inconclusive"


def test_small_sample_warning_threshold_is_centralized():
    tiny = evaluation_report(config(sample_count=1, seat_swap=False))
    enough_units = [unit(0, seed=index) for index in range(SMALL_SAMPLE_UNIT_THRESHOLD)]
    assert tiny["sample_warning"] is True
    assert len(enough_units) == SMALL_SAMPLE_UNIT_THRESHOLD
    # Warning computation is unit-count based; a no-swap report at the threshold clears it.
    threshold = evaluation_report(config(sample_count=SMALL_SAMPLE_UNIT_THRESHOLD, seat_swap=False))
    assert threshold["sample_warning"] is False


def test_seed_schedule_config_raw_metrics_and_json_are_reproducible():
    cfg = config(sample_count=2)
    assert seed_schedule(cfg) == seed_schedule(cfg) == (200, 201)
    assert run_raw_evaluation(cfg) == run_raw_evaluation(cfg)
    assert evaluation_report(cfg) == evaluation_report(cfg)
    assert json_report_text(evaluation_report(cfg)) == json_report_text(evaluation_report(cfg))


def test_report_creation_does_not_change_future_results_and_order_is_independent():
    first_cfg = config(sample_count=1, base_seed=400)
    second_cfg = config(sample_count=1, base_seed=500)
    expected_first = run_raw_evaluation(first_cfg)
    run_raw_evaluation(second_cfg)
    assert run_raw_evaluation(first_cfg) == expected_first
    evaluation_report(first_cfg)
    assert run_raw_evaluation(first_cfg) == expected_first


@pytest.mark.parametrize("bot_name", ["random", "tight", "aggressive", "equity", "expert", "adaptive"])
def test_every_registered_strategy_evaluates_without_framework_illegality(bot_name):
    report = evaluation_report(replace(config(sample_count=1), bot_a=bot_name))
    assert report["metrics"]["evaluation_units"] == 2
    assert report["metrics"]["illegal_actions"] == 0
    assert report["metrics"]["fallback_actions"] == 0
    assert report["metrics"]["exceptions"] == 0


def test_expert_adaptive_comparison_uses_same_schedule_and_reports_delta():
    report = compare_strategies("expert", "adaptive", "random", config(sample_count=1))
    assert report["comparison"]["delta_definition"] == "adaptive - expert"
    assert report["methodology"]["comparison_pairing"].startswith("matched-seed")
    assert report["methodology"]["duplicate_deal_pairing"] is False
    assert len(report["delta"]["raw_matched_unit_delta_bb"]) == 2


def test_adaptive_persistent_match_retains_profiles_and_reports_diagnostics():
    report = evaluation_report(
        EvaluationConfig(
            mode="persistent_match",
            bot_a="adaptive",
            bot_b="random",
            starting_stack=100_000,
            max_hands=6,
            sample_count=1,
            base_seed=9501,
            equity_iterations=1,
            seat_swap=False,
            bootstrap_resamples=20,
        )
    )
    diagnostics = report["metrics"]["adaptive_diagnostics"]
    assert diagnostics["adaptive_decisions"] > 0
    assert diagnostics["profile_bearing_decisions"] > 0
    assert diagnostics["exploit_activations"] >= 0


def test_adaptive_activation_categories_are_aggregated_when_present():
    metrics = aggregate_evaluation(
        [unit(1, adaptive=10, profile=8, activations=3, categories=(("overfold", 2), ("anti_aggression", 1)))],
        config(),
    )
    assert metrics["adaptive_diagnostics"]["activation_rate"] == 0.3
    assert metrics["adaptive_diagnostics"]["activation_categories"] == {"anti_aggression": 1, "overfold": 2}


def test_diagnostic_counts_are_machine_readable_warnings(monkeypatch):
    observed = replace(unit(1), illegal_actions=2, fallback_actions=1)
    monkeypatch.setattr("simulation.evaluation.run_raw_evaluation", lambda _config: (observed,))
    report = evaluation_report(config(seat_swap=False))
    assert {item["code"] for item in report["warnings"]} >= {
        "illegal_actions_observed",
        "fallback_actions_observed",
    }


def test_matrix_keeps_opponents_separate_and_regression_is_metadata_only():
    cfg = config(sample_count=1, seat_swap=False)
    matrix = strategy_matrix(["expert"], ["random", "tight"], cfg)
    assert len(matrix["rows"]) == 2
    assert matrix["weighting"].startswith("no pooled effect")
    current = evaluation_report(cfg)
    metadata = regression_metadata(current, current)
    assert metadata["direction"] == "unchanged" and metadata["automatic_failure"] is False


def test_json_export_schema_config_seeds_ci_and_overwrite(tmp_path):
    report = evaluation_report(config(sample_count=1))
    target = tmp_path / "evaluation.json"
    write_json_report(report, target)
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["evaluation_schema_version"] == EVALUATION_SCHEMA_VERSION
    assert loaded["configuration"]["base_seed"] == 200
    assert loaded["sample"]["seeds"] == [200]
    assert "confidence_intervals" in loaded["metrics"]
    with pytest.raises(ValueError, match="already exists"):
        write_json_report(report, target)
    write_json_report(report, target, overwrite=True)
    assert json.loads(target.read_text(encoding="utf-8")) == loaded


def test_cli_valid_compare_exits_zero_and_output_is_reproducible(capsys):
    args = [
        "compare", "--control", "expert", "--treatment", "adaptive", "--opponent", "random",
        "--mode", "independent", "--sample-count", "1", "--equity-iterations", "1",
        "--bootstrap-resamples", "10",
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out
    assert first == second


@pytest.mark.parametrize(
    "args",
    [
        ["compare", "--opponent", "not-a-bot"],
        ["compare", "--opponent", "random", "--sample-count", "0"],
        ["compare", "--opponent", "random", "--bootstrap-resamples", "0"],
    ],
)
def test_cli_rejects_invalid_bot_sample_and_bootstrap(args):
    with pytest.raises(SystemExit) as raised:
        main(args)
    assert raised.value.code == 2
