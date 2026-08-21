"""Short-stack normal-target legality and distinct all-in contracts."""
from __future__ import annotations

import pytest

from simulation.actions import Action
from simulation.bots import (
    AggressiveBot,
    EquityBot,
    RandomBot,
    TightBot,
)
from simulation.adaptive_bot import ExpertAdaptiveBot
from simulation.decision_state import build_decision_observation
from simulation.engine import HandEngine
from simulation.evaluation import EvaluationConfig, run_raw_evaluation
from simulation.expert_bot import ExpertRuleBot
from simulation.match import MatchConfig, run_match


def engine_with_free_action(*, stack: int, street: str = "flop") -> HandEngine:
    engine = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, bb=100, seed=9)
    engine.state.street = street
    engine.state.stacks = {"a": stack, "b": 2_000 - stack}
    engine.state.current_bets = {"a": 0, "b": 0}
    engine.state.current_highest_bet = 0
    engine.state.last_full_raise_size = 100
    engine.state.pending_players = {"a"}
    engine.state.acted_since_full_raise = {"a": False, "b": False}
    engine.state.raising_reopened = {"a": True, "b": True}
    engine.state.pot = 200
    engine.total = 2_200
    return engine


def assert_normal_target_invariant(engine: HandEngine, player: str) -> None:
    observation = engine.observe(player)
    for action in ("bet", "raise"):
        if action in observation.legal_actions:
            assert observation.minimum_target_to is not None
            assert observation.minimum_target_to <= observation.maximum_target_to


def test_short_stack_cannot_normal_bet_but_retains_under_minimum_all_in():
    engine = engine_with_free_action(stack=50)
    observation = engine.observe("a")
    assert observation.legal_actions == ["check", "all_in"]
    assert observation.minimum_target_to == 100
    assert observation.maximum_target_to == observation.all_in_target_to == 50
    assert engine._action("a", Action("all_in")) == "all_in"
    assert engine.illegal == 0
    assert engine.state.stacks["a"] == 0
    assert engine.state.current_bets["a"] == 50


def test_exact_minimum_stack_has_one_valid_normal_total_target():
    engine = engine_with_free_action(stack=100)
    observation = engine.observe("a")
    assert {"check", "bet", "all_in"} == set(observation.legal_actions)
    assert observation.minimum_target_to == observation.maximum_target_to == 100
    assert engine._action("a", Action("bet", 100)) == "bet"
    assert engine.illegal == 0
    assert engine.state.current_bets["a"] == 100
    assert engine.state.stacks["a"] == 0


def test_maximum_below_minimum_removes_only_normal_target_action():
    engine = engine_with_free_action(stack=99)
    observation = engine.observe("a")
    assert observation.maximum_target_to < observation.minimum_target_to
    assert "bet" not in observation.legal_actions
    assert "all_in" in observation.legal_actions
    assert_normal_target_invariant(engine, "a")


def test_ordinary_normal_bet_uses_total_target_and_stays_in_stack_bounds():
    engine = engine_with_free_action(stack=500)
    observation = engine.observe("a")
    assert "bet" in observation.legal_actions
    assert (observation.minimum_target_to, observation.maximum_target_to) == (100, 500)
    assert engine._action("a", Action("bet", 300)) == "bet"
    assert engine.state.current_bets["a"] == 300
    assert engine.state.stacks["a"] == 200
    assert engine.illegal == 0


def test_ordinary_raise_uses_total_target_and_has_nonempty_interval():
    engine = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, bb=100, seed=10)
    engine._action("a", Action("raise", 300))
    observation = engine.observe("b")
    assert "raise" in observation.legal_actions
    assert (observation.minimum_target_to, observation.maximum_target_to) == (500, 1_000)
    assert_normal_target_invariant(engine, "b")
    assert engine._action("b", Action("raise", 500)) == "raise"
    assert engine.state.current_bets["b"] == 500
    assert engine.state.stacks["b"] == 500
    assert engine.illegal == 0


def test_short_all_in_raise_does_not_reopen_but_full_raise_does():
    short = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, seed=11)
    short._action("a", Action("raise", 300))
    short.state.stacks["b"] = 250
    short.total = sum(short.state.stacks.values()) + short.state.pot
    before = short.observe("b")
    assert "raise" not in before.legal_actions and "all_in" in before.legal_actions
    assert before.all_in_target_to == 350 < before.minimum_target_to == 500
    short._action("b", Action("all_in"))
    assert short.state.last_full_raise_size == 200
    assert short.state.raising_reopened["a"] is False
    assert "raise" not in short.legal("a")

    full = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, seed=12)
    full._action("a", Action("raise", 200))
    full._action("b", Action("raise", 300))
    assert full.state.last_full_raise_size == 100
    assert full.state.raising_reopened == {"a": True, "b": True}
    assert "raise" in full.legal("a")


def test_amount_to_call_greater_than_stack_exposes_only_fold_and_all_in():
    engine = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, seed=13)
    engine._action("a", Action("raise", 500))
    engine.state.stacks["b"] = 200
    observation = engine.observe("b")
    assert observation.amount_to_call == 400 > observation.hero_stack
    assert observation.legal_actions == ["fold", "all_in"]
    assert "raise" not in observation.legal_actions
    assert observation.all_in_target_to == 300


def test_tiny_stack_check_state_and_river_state_never_advertise_empty_interval():
    for street in ("flop", "river"):
        engine = engine_with_free_action(stack=1, street=street)
        observation = engine.observe("a")
        assert observation.street == street
        assert observation.legal_actions == ["check", "all_in"]
        assert observation.maximum_target_to == 1
        assert_normal_target_invariant(engine, "a")


@pytest.mark.parametrize(
    ("starting_a", "starting_b"),
    [(25, 1_000), (1_000, 75)],
    ids=("short-small-blind", "short-big-blind"),
)
def test_short_blind_matches_have_no_negative_stack_or_empty_normal_interval(
    starting_a, starting_b
):
    result = run_match(
        RandomBot(1),
        RandomBot(2),
        MatchConfig(starting_a, starting_b, 50, 100, 3, 21),
    )
    assert all(stack >= 0 for stack in result.final_stacks.values())
    assert result.illegal_action_count == result.fallback_diagnostic_count == 0
    assert result.bot_a_net_chips + result.bot_b_net_chips == 0


def test_decision_observation_receives_corrected_actions_and_total_bounds():
    engine = engine_with_free_action(stack=50)
    state = build_decision_observation(engine, "a").decision_state
    assert state.legal_actions == ("check", "all_in")
    assert state.minimum_legal_target == 100
    assert state.maximum_legal_target == 50
    assert not ({"bet", "raise"} & set(state.legal_actions))


@pytest.mark.parametrize(
    "bot_type",
    [RandomBot, TightBot, AggressiveBot, EquityBot, ExpertRuleBot, ExpertAdaptiveBot],
)
def test_builtin_bots_need_no_short_stack_workaround(bot_type):
    result = run_match(
        bot_type(seed=31, equity_iterations=1),
        RandomBot(seed=32, equity_iterations=1),
        MatchConfig(250, 250, 50, 100, 8, 31),
    )
    assert result.illegal_action_count == 0
    assert result.fallback_diagnostic_count == 0
    assert result.bot_a_net_chips + result.bot_b_net_chips == 0
    assert all(stack >= 0 for stack in result.final_stacks.values())


@pytest.mark.parametrize(
    ("opponent", "seed", "strategy_as_a"),
    [
        ("random", 30_002, False),
        ("tight", 30_004, True),
        ("equity", 30_000, False),
    ],
)
def test_phase_3d1_observed_invalid_interval_seeds_now_have_no_fallback(
    opponent, seed, strategy_as_a
):
    config = EvaluationConfig(
        mode="persistent_match",
        bot_a="expert",
        bot_b=opponent,
        max_hands=50,
        sample_count=1,
        base_seed=seed,
        equity_iterations=1,
        seat_swap=True,
        bootstrap_resamples=10,
    )
    orientation = "strategy_as_a" if strategy_as_a else "strategy_as_b"
    selected = [unit for unit in run_raw_evaluation(config) if unit.orientation == orientation]
    assert len(selected) == 1
    assert selected[0].illegal_actions == 0
    assert selected[0].fallback_actions == 0
    assert selected[0].exceptions == 0


def test_representative_legal_states_never_advertise_empty_normal_intervals():
    free_short = engine_with_free_action(stack=50)
    free_exact = engine_with_free_action(stack=100)
    free_deep = engine_with_free_action(stack=1_000)
    facing = HandEngine(RandomBot(1), RandomBot(2), stack=1_000, seed=14)
    facing._action("a", Action("raise", 300))
    for engine, player in (
        (free_short, "a"),
        (free_exact, "a"),
        (free_deep, "a"),
        (facing, "b"),
    ):
        assert_normal_target_invariant(engine, player)
        observation = engine.observe(player)
        normal = [action for action in ("bet", "raise") if action in observation.legal_actions]
        if normal:
            before = engine.illegal
            assert engine._action(player, Action(normal[0], observation.minimum_target_to)) == normal[0]
            assert engine.illegal == before
            assert all(stack >= 0 for stack in engine.state.stacks.values())
