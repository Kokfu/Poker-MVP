import math
from types import SimpleNamespace

import pytest

from simulation.range_intelligence import (HoleCardCombo, RangeEquityEstimator, RangeUpdater,
    PublicRangeTracker, WeightedRange, describe_preflop, heuristic_preflop_range, legal_opponent_combos,
    showdown_calibration, summarize_range)
from simulation.bots import AggressiveBot, TightBot
from simulation.diagnostic_bots import CallingStationBot, OverAggressorBot
from simulation.engine import HandEngine


def test_combo_canonical_and_duplicate_rejected():
    assert HoleCardCombo("2c", "As").cards == ("As", "2c")
    assert HoleCardCombo("As", "2c") == HoleCardCombo("2c", "As")
    with pytest.raises(ValueError): HoleCardCombo("As", "As")


@pytest.mark.parametrize(("board", "count"), [((), 1225), (("2s", "3h", "4d"), 1081), (("2s", "3h", "4d", "5c"), 1035), (("2s", "3h", "4d", "5c", "6s"), 990)])
def test_legal_combo_counts_and_card_removal(board, count):
    combos = legal_opponent_combos(("As", "Kd"), board)
    assert len(combos) == count
    assert all(not (set(c.cards) & {"As", "Kd", *board}) for c in combos)


def test_weighted_range_is_finite_normalized_json_safe():
    r = WeightedRange.uniform(legal_opponent_combos(("As", "Kd"), ())[:4]).normalized()
    assert math.isclose(r.total_weight, 1)
    assert math.isclose(sum(r.probability(c) for c, _ in r.weights), 1)
    assert all(math.isfinite(x["probability"]) for x in r.as_dict()["top_combos_hypotheses_only"])
    with pytest.raises(ValueError): WeightedRange(((HoleCardCombo("2s", "3s"), -1),))
    with pytest.raises(ValueError): WeightedRange(((HoleCardCombo("2s", "3s"), 0),)).normalized()


def test_preflop_descriptors():
    assert describe_preflop(HoleCardCombo("As", "Ad")).pocket_pair
    assert describe_preflop(HoleCardCombo("Js", "Ts")).suited_connector
    assert describe_preflop(HoleCardCombo("As", "5s")).suited_ace
    assert describe_preflop(HoleCardCombo("Ks", "Jh")).one_gap
    assert describe_preflop(HoleCardCombo("As", "Kh")).broadway_count == 2


def test_priors_updates_and_summary_are_deterministic_non_collapsing():
    prior = heuristic_preflop_range(("As", "Kd"), action="raise")
    updater = RangeUpdater()
    after = updater.update(prior, "raise", ("2s", "7h", "Tc"), 1.0)
    assert after == updater.update(prior, "raise", ("2s", "7h", "Tc"), 1.0)
    assert after.active_combos == prior.active_combos
    assert math.isclose(after.total_weight, 1)
    summary = summarize_range(after, ("2s", "7h", "Tc"))
    assert 0 < summary.effective_combo_count <= summary.active_combos
    assert 0 <= summary.normalized_entropy <= 1
    assert 0 <= summary.weak_air_fraction <= 1


@pytest.mark.parametrize("action,fraction", [("check", None), ("call", None), ("bet", .3), ("bet", 1.0), ("raise", 1.0), ("all_in", 1.5), ("limp", None), ("3-bet", None)])
def test_supported_public_updates_are_deterministic_normalized_and_legal(action, fraction):
    prior = WeightedRange.uniform(legal_opponent_combos(("As", "Kd"), ("2s", "7h", "Tc"))).normalized()
    after = RangeUpdater().update(prior, action, ("2s", "7h", "Tc"), fraction)
    assert after == RangeUpdater().update(prior, action, ("2s", "7h", "Tc"), fraction)
    assert math.isclose(after.total_weight, 1) and after.active_combos == prior.active_combos
    assert all(not (set(c.cards) & {"As", "Kd", "2s", "7h", "Tc"}) for c, _ in after.weights)


def test_aggression_value_draw_air_and_profile_effects():
    board = ("Ks", "Qs", "2d")
    value, draw, air = HoleCardCombo("Kc", "Kd"), HoleCardCombo("Js", "Ts"), HoleCardCombo("4c", "5d")
    prior = WeightedRange(((value, 1), (draw, 1), (air, 1))).normalized()
    neutral = RangeUpdater().update(prior, "raise", board, 1)
    assert neutral.probability(value) > neutral.probability(air)
    assert neutral.probability(draw) > neutral.probability(air) > 0
    high = SimpleNamespace(statistics={"aggressive": SimpleNamespace(smoothed_frequency=.8, confidence="high")})
    passive = SimpleNamespace(statistics={"aggressive": SimpleNamespace(smoothed_frequency=.1, confidence="high")})
    high_range = RangeUpdater().update(prior, "raise", board, 1, high)
    passive_range = RangeUpdater().update(prior, "raise", board, 1, passive)
    assert high_range.probability(air) / high_range.probability(value) > passive_range.probability(air) / passive_range.probability(value)
    low = SimpleNamespace(statistics={"aggressive": SimpleNamespace(smoothed_frequency=.8, confidence="very_low")})
    assert RangeUpdater().update(prior, "raise", board, 1, low) == neutral


def test_entropy_and_effective_count_are_well_behaved():
    combos = (HoleCardCombo("2s", "3s"), HoleCardCombo("4s", "5s"))
    uniform, concentrated = WeightedRange.uniform(combos).normalized(), WeightedRange(((combos[0], 1), (combos[1], 0))).normalized()
    assert summarize_range(uniform).normalized_entropy >= summarize_range(concentrated).normalized_entropy
    assert summarize_range(concentrated).effective_combo_count == 1


def test_river_exact_winner_loser_tie_and_weighted_math():
    estimator = RangeEquityEstimator(); board = ("As", "Ks", "Qs", "Js", "2d")
    winner = WeightedRange(((HoleCardCombo("Ts", "3c"), 1),))
    loser = WeightedRange(((HoleCardCombo("9c", "3c"), 1),))
    tie = WeightedRange(((HoleCardCombo("Tc", "3c"), 1),))
    assert estimator.estimate(("Ah", "Ad"), board, winner).hero_equity == 0
    assert estimator.estimate(("Ah", "Ad"), board, loser).hero_equity == 1
    result = estimator.estimate(("Th", "3d"), board, tie)
    assert result.hero_equity == .5 and result.tie_probability == 1


def test_monte_carlo_seeded_and_no_runout_collision():
    r = WeightedRange.uniform((HoleCardCombo("2s", "3s"), HoleCardCombo("4s", "5s")))
    e = RangeEquityEstimator(); a = e.estimate(("As", "Kd"), ("Qh", "Jc", "7d"), r, 100, 7)
    b = e.estimate(("As", "Kd"), ("Qh", "Jc", "7d"), r, 100, 7)
    assert a == b and a.method == "monte_carlo" and math.isclose(a.hero_equity + a.opponent_equity, 1)
    turn = e.estimate(("As", "Kd"), ("Qh", "Jc", "7d", "2c"), r, 100, 7)
    assert turn.iterations == 100 and 0 <= turn.hero_equity <= 1 and math.isfinite(turn.tie_probability)


def test_range_equity_rng_does_not_consume_engine_deck_rng():
    left = HandEngine(CallingStationBot(2), OverAggressorBot(3), seed=42)
    right = HandEngine(CallingStationBot(2), OverAggressorBot(3), seed=42)
    diagnostic_range = PublicRangeTracker.uniform(left.holes["a"]).weighted_range
    RangeEquityEstimator().estimate(left.holes["a"], (), diagnostic_range, 80, 918)
    left_result, right_result = left.play(), right.play()
    assert left_result["history"].final_board == right_result["history"].final_board
    assert left_result["history"].events == right_result["history"].events


def test_calibration_is_explicit_post_hand_diagnostic_only():
    actual = HoleCardCombo("2s", "3s")
    r = WeightedRange(((actual, .25), (HoleCardCombo("4s", "5s"), .75)))
    diagnostic = showdown_calibration(r, actual)
    assert diagnostic["actual_combo_probability"] == .25 and diagnostic["rank"] == 2
    assert math.isfinite(diagnostic["log_score"])


def test_real_engine_history_drives_public_range_without_reading_villain_cards():
    engine = HandEngine(CallingStationBot(2), OverAggressorBot(3), seed=42)
    result = engine.play()
    tracker = PublicRangeTracker.uniform(engine.holes["a"])
    before = tracker.weighted_range
    for event in result["history"].events:
        if event.event_type == "action_taken" and event.actor == "b" and event.applied_action not in {"fold", None}:
            tracker.observe(event.applied_action, event.board, None)
    assert tracker.weighted_range != before
    assert all("opponent" not in key and "deck" not in key for key in tracker.weighted_range.as_dict())


def test_showdown_calibration_is_after_public_showdown_and_snapshot_is_immutable():
    engine = HandEngine(CallingStationBot(2), OverAggressorBot(3), seed=42)
    result = engine.play(); tracker = PublicRangeTracker.uniform(engine.holes["a"])
    for event in result["history"].events:
        if event.event_type == "action_taken" and event.actor == "b": tracker.observe(event.applied_action, event.board)
    before_showdown = tracker.weighted_range
    showdown = next(event for event in result["history"].events if event.event_type == "showdown")
    actual = HoleCardCombo(*showdown.revealed_hole_cards["b"])
    diagnostic = showdown_calibration(before_showdown, actual)
    assert diagnostic["actual_combo_probability"] > 0 and diagnostic["rank"] > 0
    assert tracker.weighted_range == before_showdown
