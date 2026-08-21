"""Contracts for the separate public-range-aware Expert strategy."""
from dataclasses import replace
from math import isfinite

from simulation.actions import Action
from simulation.bots import BOT_TYPES, RandomBot
from simulation.decision_state import DecisionObservation, DecisionState, PokerFeatureSet
from simulation.engine import HandEngine
from simulation.expert_bot import ExpertRuleBot
from simulation.range_expert_bot import RangeAwareExpertBot
from simulation.range_intelligence import RangeEquityEstimate, RangeSummary
from simulation.range_intelligence import PublicRangeTracker
from simulation.range_strategy import RangeStrategyAdjustmentEngine


def observation(*, call=100, legal=("fold", "call", "raise", "all_in"), entropy=.50, street="flop", equity=.70):
    state = DecisionState("range-unit", "match-1", 2, "a", "b", street, "a", "a", "b", "in_position", ("Qs", "9h"), ("2c", "7d", "Jh") if street != "preflop" else (), 900, 900, 900, 300, 50, 100, 9.0, 0, call, call, call, 200, 900, legal, 100, "raise" in legal, (), (), None, None, 0, False)
    features = PokerFeatureSet(
        pot_odds=call / (300 + call) if call else 0, call_price=call, required_equity=call / (300 + call) if call else 0,
        stack_to_pot_ratio=3.0, effective_stack_bb=9.0, bet_faced_fraction_of_pot=call / 300 if call else 0,
        is_button=True, position="in_position", is_preflop=street == "preflop", is_postflop=street != "preflop", made_hand="high_card",
        has_pair=False, has_two_pair=False, has_trips=False, has_straight=False, has_flush=False, has_full_house=False, has_quads=False, has_straight_flush=False,
        flush_draw=False, open_ended_straight_draw=False, gutshot=False, overcards=False, pair_plus_draw=False,
        paired_board=False, monotone_board=False, two_tone_board=False, rainbow_board=True, connected_board=False,
        board_high_card_rank="J", board_distinct_ranks=3, board_distinct_suits=3,
    )
    summary = RangeSummary(20, 20, 4.0, entropy, .1, .1, .2, .1, .5, .1, .3, .4)
    estimate = RangeEquityEstimate(equity, 0.0, 1-equity, 20, "exact" if street == "river" else "monte_carlo", 20, 4.0)
    return DecisionObservation(state, features, opponent_range_summary=summary, range_equity=estimate)


def test_registered_and_no_range_or_equity_is_exact_expert_fallback():
    base = observation(); no_range = replace(base, opponent_range_summary=None); no_equity = replace(base, range_equity=None)
    assert BOT_TYPES["range_expert"] is RangeAwareExpertBot
    assert RangeAwareExpertBot().decide_decision(no_range) == ExpertRuleBot().decide_decision(no_range)
    assert RangeAwareExpertBot().decide_decision(no_equity) == ExpertRuleBot().decide_decision(no_equity)


def test_clear_range_price_can_flip_fold_to_call_and_call_to_fold_but_broad_or_tiny_cannot():
    engine = RangeStrategyAdjustmentEngine()
    high = observation(equity=.70)
    action, explanation = engine.apply(high, Action("fold"))
    assert action.type == "call" and explanation.adjustment_category == "equity_call"
    low = observation(equity=.05)
    action, explanation = engine.apply(low, Action("call"))
    assert action.type == "fold" and explanation.adjustment_category == "equity_fold"
    broad = replace(high, opponent_range_summary=replace(high.opponent_range_summary, normalized_entropy=.999))
    assert engine.apply(broad, Action("fold"))[0] == Action("fold")
    tiny = replace(high, range_equity=replace(high.range_equity, hero_equity=.36))
    assert engine.apply(tiny, Action("fold"))[0] == Action("fold")


def test_river_is_exact_and_seeded_engine_path_is_private_deterministic_and_legal():
    first = HandEngine(RangeAwareExpertBot(1, range_equity_iterations=50), RandomBot(2), seed=42)
    second = HandEngine(RangeAwareExpertBot(1, range_equity_iterations=50), RandomBot(2), seed=42)
    a, b = first.bots["a"].decide_decision(first.decision_observation("a")), second.bots["a"].decide_decision(second.decision_observation("a"))
    assert a == b and first.bots["a"].last_explanation == second.bots["a"].last_explanation
    assert "deck" not in str(first.bots["a"].last_explanation).lower()
    result = HandEngine(RangeAwareExpertBot(3, range_equity_iterations=30), RandomBot(4), seed=9).play()
    assert result["illegal_actions"] == 0


def test_seed_is_stable_without_consuming_bot_rng_and_explanation_is_finite():
    bot = RangeAwareExpertBot(8); o = observation()
    assert bot.range_equity_seed(o.decision_state) == bot.range_equity_seed(o.decision_state)
    bot.decide_decision(o)
    assert all(isfinite(value) for value in (bot.last_explanation.range_equity, bot.last_explanation.required_equity, bot.last_explanation.equity_margin, bot.last_explanation.normalized_entropy, bot.last_explanation.effective_combo_count))


def test_every_board_transition_removes_new_public_cards_and_stays_normalized():
    tracker = PublicRangeTracker.uniform(("As", "Kd"))
    transitions = (("2c", "7d", "Jh"), ("2c", "7d", "Jh", "Tc"), ("2c", "7d", "Jh", "Tc", "3s"))
    expected = (1081, 1035, 990)
    for board, count in zip(transitions, expected):
        tracker.sync_board(board)
        tracker.assert_invariants(board)
        assert tracker.weighted_range.active_combos == count
        assert all(not (set(combo.cards) & set(board)) for combo, _ in tracker.weighted_range.weights)
