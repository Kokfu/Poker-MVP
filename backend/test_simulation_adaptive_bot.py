"""Focused contracts for the separate confidence-gated adaptive strategy."""
import json
from dataclasses import replace
from math import isfinite
from types import SimpleNamespace

from simulation.adaptive_bot import ExpertAdaptiveBot
from simulation.bots import BOT_TYPES, RandomBot
from simulation.decision_state import DecisionObservation, DecisionState, PokerFeatureSet, build_decision_observation
from simulation.engine import HandEngine
from simulation.expert_bot import ExpertRuleBot
from simulation.adaptive_benchmark import run_archetype_diagnostic


def observation(*, street="flop", cards=("Qs", "9h"), board=("2c", "7d", "Jh"), legal=("check", "bet"), initiative=True, profile=None, features=None, call=0):
    state = DecisionState("adaptive-unit", None, 1, "a", "b", street, "a", "a", "b", "in_position", cards, board if street != "preflop" else (), 1000, 1000, 1000, 300, 50, 100, 10.0, 0, call, call, call, 200, 1000, legal, 100, "raise" in legal, (), (), None, None, 0, initiative)
    f = PokerFeatureSet(
        pot_odds=0.0, call_price=call, required_equity=0.0, stack_to_pot_ratio=10.0, effective_stack_bb=10.0,
        bet_faced_fraction_of_pot=0.0, is_button=True, position="in_position", is_preflop=street == "preflop", is_postflop=street != "preflop",
        made_hand="preflop" if street == "preflop" else "high_card", has_pair=False, has_two_pair=False, has_trips=False, has_straight=False,
        has_flush=False, has_full_house=False, has_quads=False, has_straight_flush=False, flush_draw=False, open_ended_straight_draw=False,
        gutshot=False, overcards=False, pair_plus_draw=False, paired_board=False, monotone_board=False, two_tone_board=False,
        rainbow_board=False, connected_board=False, board_high_card_rank=None, board_distinct_ranks=0, board_distinct_suits=0,
    )
    return DecisionObservation(state, features or f, opponent_profile=profile)


def profile(*, fold=.75, call=.20, aggression=.25, confidence="high", opportunities=80):
    stat = lambda rate: SimpleNamespace(smoothed_frequency=rate, confidence=confidence, opportunities=opportunities, occurrences=round(rate * opportunities))
    return SimpleNamespace(statistics={"aggressive": stat(aggression), "fold_to_raise": stat(fold)}, street_statistics={"flop": {"fold_to_bet": stat(fold), "call_vs_bet": stat(call)}})


def test_adaptive_registered_and_no_profile_is_exact_expert_control():
    o = observation(profile=None)
    assert BOT_TYPES["adaptive"] is ExpertAdaptiveBot
    assert ExpertAdaptiveBot().decide_decision(o) == ExpertRuleBot().decide_decision(o)


def test_confidence_gate_blocks_tiny_overfold_and_high_confidence_can_bluff():
    low = ExpertAdaptiveBot(); high = ExpertAdaptiveBot()
    low_observation = observation(initiative=False, profile=profile(confidence="very_low", opportunities=2))
    assert low.decide_decision(low_observation) == ExpertRuleBot().decide_decision(low_observation)
    assert low.last_explanation.low_confidence_forced_baseline
    action = high.decide_decision(observation(initiative=False, profile=profile()))
    assert action.type == "bet" and action.amount == 200
    assert high.last_explanation.exploit_applied and high.last_explanation.category == "overfold"


def test_calling_station_suppresses_pure_bluff_and_value_sizing_stays_legal():
    station = profile(fold=.10, call=.82)
    bot = ExpertAdaptiveBot(); assert bot.decide_decision(observation(profile=station)).type == "check"
    feature = replace(observation().poker_features, has_two_pair=True)
    value = ExpertAdaptiveBot(); action = value.decide_decision(observation(profile=station, features=feature))
    assert action.type == "bet" and 200 <= action.amount <= 1000 and value.last_explanation.sizing_adjustment


def test_adaptive_is_deterministic_private_and_legal_in_engine():
    first, second = HandEngine(ExpertAdaptiveBot(1), RandomBot(2), seed=42), HandEngine(ExpertAdaptiveBot(1), RandomBot(2), seed=42)
    a = first.bots["a"].decide_decision(build_decision_observation(first, "a")); b = second.bots["a"].decide_decision(build_decision_observation(second, "a"))
    assert a == b and first.bots["a"].last_explanation == second.bots["a"].last_explanation
    rendered = json.dumps(first.bots["a"].last_explanation.__dict__, allow_nan=False).lower()
    assert "deck" not in rendered and "future" not in rendered and isfinite(first.bots["a"].last_explanation.signal_strength)
    result = HandEngine(ExpertAdaptiveBot(3), RandomBot(4), seed=9).play()
    assert result["illegal_actions"] == 0


def test_real_public_history_archetypes_activate_without_lookahead():
    rows = run_archetype_diagnostic(hands=200, seeds=(9501,), starting_stack=100000)
    for name in ("overfolder", "calling_station", "overaggressor"):
        row = rows[name][0]
        activations = [entry for entry in row["trace"] if entry["exploit_applied"]]
        assert row["trace"][0]["profile_hands_observed"] == 0
        assert all(entry["profile_hands_observed"] <= entry["hand_number"] - 1 for entry in row["trace"])
        assert activations, name
        assert all(entry["opportunities"] >= 20 and entry["confidence"] in {"medium", "high"} for entry in activations)


def test_real_passive_history_activates_distinct_passive_initiative_legally():
    row = run_archetype_diagnostic(hands=200, seeds=(9501,), starting_stack=100000)["passive"][0]
    activations = [entry for entry in row["trace"] if entry["category"] == "passive_initiative" and entry["exploit_applied"]]
    assert activations
    activation = activations[0]
    assert activation["baseline_action"] == "check" and activation["final_action"] == "bet"
    assert activation["statistic"] == "aggressive" and activation["occurrences"] == 0
    assert activation["profile_hands_observed"] <= activation["hand_number"] - 1
    assert activation["final_target"] is not None and row["illegal_actions"] == row["fallbacks"] == 0
