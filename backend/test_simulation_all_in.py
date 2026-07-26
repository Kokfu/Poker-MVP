import pytest

from scripted_test_support import ScriptedBot, assert_conserved, assert_settled
from simulation.actions import Action
from simulation.bots import RandomBot
from simulation.engine import HandEngine


def set_remaining_stack(engine, player, stack):
    engine.state.stacks[player] = stack
    engine.total = sum(engine.state.stacks.values()) + engine.state.pot


def test_short_all_in_call_contract_and_uncalled_excess():
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=30)
    engine.state.current_bets = {"a": 500, "b": 100}
    engine.state.current_highest_bet = 500
    engine.state.last_full_raise_size = 300
    engine.state.stacks = {"a": 500, "b": 200}
    engine.state.pot = 1300
    engine.total = 2000
    engine.state.pending_players = {"b"}
    engine.state.acted_since_full_raise = {"a": True, "b": False}
    engine.state.raising_reopened = {"a": True, "b": True}

    observation = engine.observe("b")
    assert observation.amount_to_call == 400
    assert observation.all_in_target_to == 300
    assert observation.all_in_target_to < engine.state.current_highest_bet
    assert observation.legal_actions == ["fold", "all_in"]
    last_raise = engine.state.last_full_raise_size
    assert engine._action("b", Action("all_in")) == "all_in"
    assert engine.state.current_bets == {"a": 300, "b": 300}
    assert engine.state.current_highest_bet == 300
    assert engine.state.stacks == {"a": 700, "b": 0}
    assert engine.state.last_full_raise_size == last_raise
    assert engine.state.pending_players == set()
    assert engine.state.raising_reopened["a"] is True
    assert_conserved(engine)


def test_exact_all_in_call_uses_all_in_not_normal_call():
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=31)
    engine._action("a", Action("raise", 500))
    set_remaining_stack(engine, "b", 400)
    observation = engine.observe("b")
    assert observation.amount_to_call == 400
    assert observation.all_in_target_to == 500
    assert observation.legal_actions == ["fold", "all_in"]
    engine._action("b", Action("all_in"))
    assert engine.state.current_bets == {"a": 500, "b": 500}
    assert engine.state.pending_players == set()
    assert engine.state.last_full_raise_size == 400


def test_short_all_in_raise_requires_response_without_reopening_prior_actor():
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=32)
    engine._action("a", Action("raise", 300))
    set_remaining_stack(engine, "b", 250)
    before = engine.observe("b")
    assert before.minimum_target_to == 500
    assert before.maximum_target_to == 350
    assert before.all_in_target_to == 350
    assert "raise" not in before.legal_actions
    assert "all_in" in before.legal_actions
    last_raise = engine.state.last_full_raise_size

    engine._action("b", Action("all_in"))
    assert engine.state.current_highest_bet == 350
    assert engine.state.last_full_raise_size == last_raise
    assert engine.state.pending_players == {"a"}
    assert engine.state.raising_reopened["a"] is False
    response = engine.observe("a")
    assert response.amount_to_call == 50
    assert set(response.legal_actions) == {"fold", "call"}
    assert "raise" not in response.legal_actions
    assert "all_in" not in response.legal_actions
    engine._action("a", Action("call"))
    assert engine.state.pending_players == set()
    assert_conserved(engine)


def test_closed_rights_prevent_increasing_all_in():
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=33)
    engine.state.current_bets = {"a": 300, "b": 350}
    engine.state.current_highest_bet = 350
    engine.state.stacks = {"a": 700, "b": 0}
    engine.state.pot = 650
    engine.total = 1350
    engine.state.pending_players = {"a"}
    engine.state.acted_since_full_raise = {"a": True, "b": True}
    engine.state.raising_reopened = {"a": False, "b": True}
    observation = engine.observe("a")
    assert set(observation.legal_actions) == {"fold", "call"}
    assert observation.minimum_target_to is None
    engine._action("a", Action("all_in"))
    assert engine.illegal == 1
    assert engine.folded == "a"
    assert engine.state.current_highest_bet == 350


def test_full_all_in_raise_reopens_and_updates_raise_size():
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=34)
    engine._action("a", Action("raise", 200))
    set_remaining_stack(engine, "b", 400)
    before = engine.observe("b")
    assert before.minimum_target_to == 300
    assert before.all_in_target_to == 500
    assert "all_in" in before.legal_actions
    engine._action("b", Action("all_in"))
    assert engine.state.current_highest_bet == 500
    assert engine.state.last_full_raise_size == 300
    assert engine.state.acted_since_full_raise == {"a": False, "b": True}
    assert engine.state.raising_reopened == {"a": True, "b": True}
    assert engine.state.pending_players == {"a"}
    assert set(engine.observe("a").legal_actions) >= {"fold", "call", "raise"}


@pytest.mark.parametrize(
    "remaining,raise_expected,all_in_expected,min_target,max_target",
    [
        (250, False, True, 500, 350),
        (400, True, True, 500, 500),
        (700, True, True, 500, 800),
    ],
)
def test_affordable_raise_boundaries(
    remaining, raise_expected, all_in_expected, min_target, max_target
):
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=35)
    engine._action("a", Action("raise", 300))
    set_remaining_stack(engine, "b", remaining)
    observation = engine.observe("b")
    assert observation.minimum_target_to == min_target
    assert observation.maximum_target_to == max_target
    assert ("raise" in observation.legal_actions) is raise_expected
    assert ("all_in" in observation.legal_actions) is all_in_expected

    if min_target == max_target:
        assert engine._action("b", Action("raise", min_target)) == "raise"
        assert engine.illegal == 0
        for target in (min_target - 1, min_target + 1):
            other = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=35)
            other._action("a", Action("raise", 300))
            set_remaining_stack(other, "b", remaining)
            other._action("b", Action("raise", target))
            assert other.illegal == 1
    elif min_target < max_target:
        assert engine._action("b", Action("raise", min_target)) == "raise"
        assert engine.illegal == 0
    else:
        assert engine._action("b", Action("all_in")) == "all_in"
        assert engine.illegal == 0


@pytest.mark.parametrize(
    "call,stack,reopened,expected",
    [
        (0, 500, True, {"check", "raise", "all_in"}),
        (100, 500, True, {"fold", "call", "raise", "all_in"}),
        (100, 100, True, {"fold", "all_in"}),
        (100, 500, False, {"fold", "call"}),
    ],
)
def test_raising_rights_legal_generation_matches_validation(
    call, stack, reopened, expected
):
    engine = HandEngine(RandomBot(), RandomBot(), stack=1000, seed=36)
    engine.state.current_bets = {"a": 300 - call, "b": 300}
    engine.state.current_highest_bet = 300
    engine.state.stacks["a"] = stack
    engine.state.pending_players = {"a"}
    engine.state.raising_reopened["a"] = reopened
    engine.total = sum(engine.state.stacks.values()) + engine.state.pot
    legal = set(engine.legal("a"))
    assert legal == expected
    if "check" in legal:
        assert engine._action("a", Action("check")) == "check"
    elif "call" in legal:
        assert engine._action("a", Action("call")) == "call"
    else:
        assert engine._action("a", Action("all_in")) == "all_in"
    assert engine.illegal == 0


def test_short_and_full_all_in_raises_receive_opponent_action_in_play():
    short = HandEngine(
        ScriptedBot([Action("raise", 300), Action("call")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=37,
    )
    set_remaining_stack(short, "b", 250)
    short.play()
    assert short.bots["a"].consumed_action_count == 2
    assert short.bots["b"].consumed_action_count == 1
    assert short.illegal == 0
    assert short.showdown_count == 1
    assert_settled(short)

    full = HandEngine(
        ScriptedBot([Action("raise", 200), Action("call")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=38,
    )
    set_remaining_stack(full, "b", 400)
    full.play()
    assert full.bots["a"].consumed_action_count == 2
    assert full.bots["b"].consumed_action_count == 1
    assert full.illegal == 0
    assert full.showdown_count == 1
    assert_settled(full)


# Cumulative multiway reopening rules require three or more players and are
# intentionally outside this heads-up engine.
