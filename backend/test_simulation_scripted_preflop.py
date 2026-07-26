import pytest

from scripted_test_support import (
    ScriptedBot,
    ScriptedStep,
    assert_conserved,
    assert_settled,
    run_round,
)
from simulation.actions import Action
from simulation.engine import HandEngine


def test_scripted_bot_contract_and_callbacks():
    seen = []
    bot = ScriptedBot(
        [
            ScriptedStep(
                Action("call"),
                before=lambda observation: seen.append(("before", observation.street)),
                after=lambda state: seen.append(("after", state.pot)),
            )
        ]
    )
    engine = HandEngine(bot, ScriptedBot([Action("check")]), seed=1)
    run_round(engine, "a")
    bot.assert_consumed()
    engine.bots["b"].assert_consumed()
    assert bot.consumed_action_count == 1
    assert seen == [("before", "preflop"), ("after", 200)]
    with pytest.raises(AssertionError, match="unexpected extra decision"):
        bot.decide(engine.observe("a"))
    with pytest.raises(AssertionError, match="remain unused"):
        ScriptedBot([Action("check")]).assert_consumed()


@pytest.mark.parametrize(
    "a_actions,b_actions,expected_highest,expected_last_raise",
    [
        ([Action("raise", 200)], [Action("call")], 200, 100),
        ([Action("raise", 200), Action("call")], [Action("raise", 300)], 300, 100),
        ([Action("call"), Action("call")], [Action("raise", 200)], 200, 100),
        (
            [Action("raise", 200), Action("raise", 400)],
            [Action("raise", 300), Action("call")],
            400,
            100,
        ),
        (
            [Action("raise", 200), Action("raise", 400), Action("raise", 600)],
            [Action("raise", 300), Action("raise", 500), Action("call")],
            600,
            100,
        ),
    ],
)
def test_preflop_full_raise_call_matrix(
    a_actions, b_actions, expected_highest, expected_last_raise
):
    a = ScriptedBot(a_actions)
    b = ScriptedBot(b_actions)
    engine = HandEngine(a, b, seed=2)
    run_round(engine, "a")
    a.assert_consumed()
    b.assert_consumed()
    assert engine.state.pending_players == set()
    assert engine.state.current_highest_bet == expected_highest
    assert engine.state.last_full_raise_size == expected_last_raise
    assert engine.state.current_bets == {"a": expected_highest, "b": expected_highest}
    assert engine.state.pot == expected_highest * 2
    assert engine.illegal == 0
    assert_conserved(engine)
    engine._next_street()
    assert engine.state.street == "flop"
    assert engine.state.current_bets == {"a": 0, "b": 0}
    assert engine.state.current_highest_bet == 0
    assert engine.state.last_full_raise_size == engine.bb
    assert engine.state.acted_since_full_raise == {"a": False, "b": False}
    assert engine.state.raising_reopened == {"a": True, "b": True}
    assert engine.state.acting_player == "b"


def test_limp_does_not_close_preflop_and_big_blind_keeps_option():
    a = ScriptedBot([Action("call"), Action("call")])
    b = ScriptedBot([Action("raise", 200)])
    engine = HandEngine(a, b, seed=3)
    first = engine.observe("a")
    assert first.amount_to_call == 50
    run_round(engine, "a")
    assert b.observations[0].amount_to_call == 0
    assert set(b.observations[0].legal_actions) == {"check", "raise", "all_in"}
    assert a.observations[1].amount_to_call == 100
    assert set(a.observations[1].legal_actions) >= {"fold", "call", "raise"}
    assert engine.state.pending_players == set()
    assert engine.illegal == 0


@pytest.mark.parametrize(
    "a_actions,b_actions,expected_board",
    [
        ([Action("raise", 200), Action("fold")], [Action("raise", 300)], 0),
        ([Action("call"), Action("fold")], [Action("raise", 200)], 0),
        (
            [Action("raise", 200), Action("raise", 400), Action("fold")],
            [Action("raise", 300), Action("raise", 500)],
            0,
        ),
    ],
)
def test_preflop_raise_and_limp_fold_settlement(a_actions, b_actions, expected_board):
    engine = HandEngine(ScriptedBot(a_actions), ScriptedBot(b_actions), seed=4)
    result = engine.play()
    assert len(engine.state.community_cards) == expected_board
    assert result["showdown"] is False
    assert engine.showdown_count == 0
    assert_settled(engine)
    assert engine.illegal == 0


def test_full_raise_total_target_semantics_and_boundaries():
    engine = HandEngine(ScriptedBot([]), ScriptedBot([]), seed=5)
    engine._next_street()
    assert engine._action("b", Action("bet", 100)) == "bet"
    assert engine.state.current_highest_bet == 100
    assert engine.state.last_full_raise_size == 100
    assert engine.observe("a").minimum_target_to == 200

    assert engine._action("a", Action("raise", 300)) == "raise"
    assert engine.state.current_highest_bet == 300
    assert engine.state.last_full_raise_size == 200
    assert engine.observe("b").minimum_target_to == 500
    assert engine.observe("b").amount_to_call == 200
    assert engine.state.pending_players == {"b"}
    assert engine.state.raising_reopened == {"a": True, "b": True}

    before = dict(engine.state.current_bets)
    assert engine._action("b", Action("raise", 499)) == "fold"
    assert engine.illegal == 1
    assert engine.state.current_bets == before

    engine = HandEngine(ScriptedBot([]), ScriptedBot([]), seed=5)
    engine._next_street()
    engine._action("b", Action("bet", 100))
    engine._action("a", Action("raise", 300))
    assert engine._action("b", Action("raise", 500)) == "raise"
    assert engine.state.last_full_raise_size == 200
    assert engine._action("a", Action("raise", 700)) == "raise"
    assert engine.state.last_full_raise_size == 200
    assert engine.observe("b").minimum_target_to == 900

    # A 100 -> 300 -> 700 sequence has increments 200 and 400.
    engine = HandEngine(ScriptedBot([]), ScriptedBot([]), seed=5)
    engine._next_street()
    engine._action("b", Action("bet", 100))
    engine._action("a", Action("raise", 300))
    engine._action("b", Action("raise", 700))
    assert engine.state.last_full_raise_size == 400
    assert engine.observe("a").minimum_target_to == 1100
