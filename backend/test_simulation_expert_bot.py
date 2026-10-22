"""Focused contract tests for the deterministic ExpertRuleBot baseline."""
import json
from dataclasses import replace
from math import isfinite
from types import SimpleNamespace

import pytest

from simulation.bots import BOT_TYPES, AggressiveBot, EquityBot, RandomBot, TightBot
from simulation.decision_state import DecisionObservation, DecisionState, PokerFeatureSet, PublicAction, build_decision_observation
from simulation.engine import HandEngine, SimulationRunner
from simulation.expert_bot import ExpertRuleBot
from simulation.match_service import run_builtin_match


def expert_observation(*, cards=("As", "Kh"), street="preflop", board=(), legal=("fold", "check", "call", "bet", "raise", "all_in"), call=0, pot=300, minimum=200, maximum=1000, position="in_position", stack_bb=50, actions=(), initiative=False, features=None, profile=None):
    state = DecisionState("unit", None, 1, "a", "b", street, "a", "a", "b", position, cards, board, 1000, 1000, int(stack_bb * 100), pot, 50, 100, stack_bb, 0, call, call, call, minimum, maximum, legal, 100, "raise" in legal, actions, actions, None, None, 0, initiative)
    base = PokerFeatureSet(
        pot_odds=call / (pot + call) if call else 0.0, call_price=call, required_equity=call / (pot + call) if call else 0.0,
        stack_to_pot_ratio=stack_bb, effective_stack_bb=stack_bb, bet_faced_fraction_of_pot=call / pot if pot else 0.0,
        is_button=position == "in_position", position=position, is_preflop=street == "preflop", is_postflop=street != "preflop",
        made_hand="preflop" if street == "preflop" else "high_card", has_pair=False, has_two_pair=False, has_trips=False, has_straight=False,
        has_flush=False, has_full_house=False, has_quads=False, has_straight_flush=False, flush_draw=False, open_ended_straight_draw=False,
        gutshot=False, overcards=False, pair_plus_draw=False, paired_board=False, monotone_board=False, two_tone_board=False,
        rainbow_board=False, connected_board=False, board_high_card_rank=None, board_distinct_ranks=0, board_distinct_suits=0,
    )
    return DecisionObservation(state, features or base, opponent_profile=profile)


def post_features(**changes):
    base = expert_observation(street="flop").poker_features
    return type(base)(**{**base.__dict__, **changes})


def profile(vpip, aggression, confidence="medium"):
    stat = lambda value: SimpleNamespace(smoothed_frequency=value, confidence=confidence)
    return SimpleNamespace(statistics={"vpip": stat(vpip), "aggressive": stat(aggression)})


def test_expert_is_registered_and_runs_legally_against_every_builtin():
    for index, opponent in enumerate((RandomBot, TightBot, AggressiveBot, EquityBot, ExpertRuleBot)):
        result = SimulationRunner(ExpertRuleBot(seed=10), opponent(seed=20, equity_iterations=50), hands=25, seed=100 + index, equity_iterations=50).run()
        assert result["illegal_actions"] == 0
    assert BOT_TYPES["expert"] is ExpertRuleBot


def test_expert_decisions_and_explanations_are_deterministic_and_finite():
    first = HandEngine(ExpertRuleBot(), RandomBot(2), seed=42)
    second = HandEngine(ExpertRuleBot(), RandomBot(2), seed=42)
    one = first.bots["a"].decide_decision(build_decision_observation(first, "a"))
    two = second.bots["a"].decide_decision(build_decision_observation(second, "a"))
    explanation = first.bots["a"].last_explanation
    assert one == two and explanation == second.bots["a"].last_explanation
    assert explanation and explanation.chosen_action == one.type and explanation.strategy_category
    assert isfinite(explanation.pot_odds) and isfinite(explanation.spr)
    json.dumps(explanation.__dict__, allow_nan=False)


def test_expert_preserves_authoritative_total_target_bounds():
    game = HandEngine(ExpertRuleBot(), RandomBot(2), seed=9)
    observation = build_decision_observation(game, "a")
    action = game.bots["a"].decide_decision(observation)
    state = observation.decision_state
    assert action.type in state.legal_actions
    if action.type in {"bet", "raise"}:
        assert state.minimum_legal_target <= action.amount <= state.maximum_legal_target


def test_expert_does_not_consume_deck_or_depend_on_bot_rng_for_a_decision():
    game = HandEngine(ExpertRuleBot(seed=1), RandomBot(2), seed=22)
    before_deck = list(game.deck.cards)
    before_rng = game.bots["a"].rng.getstate()
    game.bots["a"].decide_decision(build_decision_observation(game, "a"))
    assert game.deck.cards == before_deck and game.bots["a"].rng.getstate() == before_rng


def test_expert_is_supported_by_persistent_matches_without_fallbacks():
    result = run_builtin_match(bot_a="expert", bot_b="tight", max_hands=25, seed=71, equity_iterations=500)
    assert result["illegal_actions"] == 0 and result["fallback_diagnostics"] == 0


@pytest.mark.parametrize(("cards", "actions", "call", "stack_bb", "expected"), [
    (("As", "Ah"), (), 0, 50, "raise"),                 # premium unopened
    (("7s", "2h"), (PublicAction("b", "raise", 600),), 500, 50, "fold"),  # weak vs raise
    (("As", "9s"), (PublicAction("b", "raise", 300),), 200, 50, "call"),  # strong defend
    (("As", "Ah"), (), 0, 15, "all_in"),                # short commitment
    (("Js", "Ts"), (), 0, 100, "raise"),                # deep non-shove
    (("9s", "8s"), (PublicAction("b", "call", 100),), 0, 50, "raise"),   # limp isolate
    (("As", "Ah"), (PublicAction("b", "raise", 300), PublicAction("a", "call", 300), PublicAction("b", "raise", 900)), 600, 50, "raise"),
])
def test_expert_preflop_representative_branches(cards, actions, call, stack_bb, expected):
    bot = ExpertRuleBot()
    action = bot.decide_decision(expert_observation(cards=cards, call=call, stack_bb=stack_bb, actions=actions, legal=("fold", "check", "call", "raise", "all_in")))
    assert action.type == expected


@pytest.mark.parametrize(("features", "call", "expected"), [
    (post_features(has_two_pair=True), 0, "bet"),
    (post_features(has_two_pair=True), 100, "raise"),
    (post_features(has_pair=True, board_high_card_rank="A"), 0, "check"),
    (post_features(has_pair=True, board_high_card_rank="A"), 500, "fold"),
    (post_features(has_pair=True, board_high_card_rank="K", stack_to_pot_ratio=2), 100, "raise"),
    (post_features(flush_draw=True), 0, "bet"),
    (post_features(open_ended_straight_draw=True), 100, "raise"),
    (post_features(gutshot=True), 500, "fold"),
    (post_features(has_pair=True, flush_draw=True, pair_plus_draw=True, board_high_card_rank="A"), 500, "call"),
    (post_features(), 0, "check"),
])
def test_expert_postflop_made_hand_draw_and_air_branches(features, call, expected):
    bot = ExpertRuleBot()
    features = replace(features, pot_odds=call / (300 + call) if call else 0, required_equity=call / (300 + call) if call else 0, bet_faced_fraction_of_pot=call / 300)
    cards = ("Ks", "9h") if features.stack_to_pot_ratio == 2 else ("Qs", "9h")
    action = bot.decide_decision(expert_observation(street="flop", board=("2c", "7d", "Jh"), cards=cards, features=features, call=call, legal=("fold", "check", "call", "bet", "raise", "all_in")))
    assert action.type == expected


def test_expert_bluffs_only_deterministically_and_profile_adjustments_are_numeric():
    feature = post_features()
    baseline = ExpertRuleBot().decide_decision(expert_observation(street="flop", features=feature, initiative=True, legal=("check", "bet")))
    station_bot = ExpertRuleBot(); station = station_bot.decide_decision(expert_observation(street="flop", features=feature, initiative=True, legal=("check", "bet"), profile=profile(.70, .20)))
    pressure_bot = ExpertRuleBot(); pressure = pressure_bot.decide_decision(expert_observation(street="flop", features=feature, initiative=False, legal=("check", "bet"), profile=profile(.25, .20)))
    assert baseline.type == "bet" and station.type == "check" and pressure.type == "bet"
    assert station_bot.last_explanation.opponent_adjustment == "reduce_bluffs_vs_loose_passive"
    assert pressure_bot.last_explanation.opponent_adjustment == "selective_pressure_vs_tight_passive"


@pytest.mark.parametrize("confidence", ["very_low", "low"])
def test_low_confidence_profiles_stay_at_baseline_and_explain_warning(confidence):
    bot = ExpertRuleBot()
    action = bot.decide_decision(expert_observation(street="flop", features=post_features(), initiative=True, legal=("check", "bet"), profile=profile(.70, .20, confidence)))
    assert action.type == "bet" and "low" in bot.last_explanation.warnings[0]


def test_expert_explanation_has_no_private_data_and_observation_is_not_mutated():
    observation = expert_observation(street="flop", features=post_features(has_two_pair=True), legal=("check", "bet"))
    before = observation.as_dict()
    bot = ExpertRuleBot(); action = bot.decide_decision(observation); explanation = bot.last_explanation
    assert observation.as_dict() == before and explanation.chosen_action == action.type and explanation.target_total == action.amount
    assert explanation.hand_strength_category and isfinite(explanation.required_equity)
    rendered = json.dumps(explanation.__dict__).lower()
    assert '"as"' not in rendered and '"ah"' not in rendered and "future_board" not in rendered
