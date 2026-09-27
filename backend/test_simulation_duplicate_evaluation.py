"""Phase 5A duplicate-deal evaluation and win-rate gate."""
from dataclasses import replace

import pytest

from simulation.duplicate_evaluation import (
    DuplicateConfig, SEED_SETS, _play_hand, duplicate_report, play_duplicate_pair,
    run_duplicate_pairs, run_tournament, summarize_pairs, win_rate_gate,
)

CONFIG = DuplicateConfig(pairs=12, bootstrap_resamples=200)


def test_seed_sets_are_disjoint_and_named():
    development = set(DuplicateConfig(pairs=1000).seeds())
    holdout = set(DuplicateConfig(pairs=1000, seed_set="holdout").seeds())
    assert not development & holdout
    assert min(holdout) == SEED_SETS["holdout"]
    with pytest.raises(ValueError):
        DuplicateConfig(seed_set="training")


def test_both_seats_receive_identical_deal():
    for seed in CONFIG.seeds():
        _, holes_a, board_a, *_ = _play_hand(CONFIG, "aggressive", "tight", seed, "a")
        _, holes_b, board_b, *_ = _play_hand(CONFIG, "aggressive", "tight", seed, "b")
        assert holes_a == holes_b
        shared = min(len(board_a), len(board_b))
        assert board_a[:shared] == board_b[:shared]


def test_bot_against_itself_cancels_exactly():
    # Deterministic identical bots in swapped seats make identical decisions,
    # so each pair must be exactly zero: the purest duplicate-luck check.
    pairs = run_duplicate_pairs(CONFIG, "tight", "tight")
    assert all(pair.net == 0 for pair in pairs)
    assert all(pair.deal_verified for pair in pairs)


def test_pair_is_zero_sum_across_perspectives():
    # Both bots are deterministic, so their role-derived RNG seeds cannot
    # change decisions and the reversed pair must mirror exactly.
    for seed in CONFIG.seeds()[:5]:
        forward = play_duplicate_pair(CONFIG, "expert", "tight", seed)
        reverse = play_duplicate_pair(CONFIG, "tight", "expert", seed)
        assert forward.net == -reverse.net


def test_results_do_not_depend_on_worker_count():
    single = run_duplicate_pairs(CONFIG, "equity", "aggressive")
    parallel = run_duplicate_pairs(replace(CONFIG, workers=2), "equity", "aggressive")
    assert single == parallel


def test_summary_metrics_and_determinism():
    pairs = run_duplicate_pairs(CONFIG, "expert", "random")
    summary = summarize_pairs(pairs, CONFIG)
    total = sum(pair.net for pair in pairs)
    assert summary["hands"] == 2 * len(pairs)
    assert summary["bb_per_100"] == pytest.approx(100 * total / CONFIG.big_blind / (2 * len(pairs)))
    assert summary["confidence_interval"]["lower"] <= summary["bb_per_100"] <= summary["confidence_interval"]["upper"]
    assert summary["deal_mismatches"] == 0 and summary["illegal_actions"] == 0
    assert summarize_pairs(pairs, CONFIG) == summary
    report = duplicate_report(CONFIG, "expert", "random")
    assert report["report_type"] == "duplicate_evaluation" and report["duplicate_schema_version"] == "1.0"
    assert report["metrics"]["bb_per_100"] == summary["bb_per_100"]


def test_tournament_matrix_is_antisymmetric_and_gate_is_consistent():
    report = run_tournament(CONFIG, ["random", "tight", "expert"])
    matrix = report["matrix_bb_per_100"]
    for first in report["bots"]:
        for second in report["bots"]:
            if first != second:
                assert matrix[first][second] == pytest.approx(-matrix[second][first])
    assert [entry["rank"] for entry in report["standings"]] == [1, 2, 3]
    assert report["totals"]["deal_mismatches"] == 0
    leader = report["standings"][0]["bot"]
    gate = win_rate_gate(report, leader)
    assert len(gate["head_to_head"]) == 2
    assert gate["passed"] == (all(item["lower"] > 0 for item in gate["head_to_head"]) and gate["pool"]["difference_interval"]["lower"] > 0)
    assert gate["acceptance_eligible"] is False  # development seeds never accept
    with pytest.raises(ValueError):
        win_rate_gate(report, "adaptive")


def test_session_mode_pairs_every_hand_and_builds_profiles():
    config = DuplicateConfig(pairs=2, session_hands=6, bootstrap_resamples=100)
    assert config.seeds() == (1_000_000, 1_000_006)
    pairs = run_duplicate_pairs(config, "adaptive", "aggressive")
    assert all(pair.deal_verified and pair.hands == 12 for pair in pairs)
    summary = summarize_pairs(pairs, config)
    assert summary["hands"] == 24
    assert summary["bb_per_100"] == pytest.approx(100 * sum(p.net for p in pairs) / 100 / 24)
    # Identical deterministic bots cancel exactly even with learning enabled.
    assert all(pair.net == 0 for pair in run_duplicate_pairs(config, "tight", "tight"))
