import pytest

from scripted_test_support import (
    ScriptedBot,
    assert_conserved,
    assert_settled,
    run_round,
    set_postflop,
)
from simulation.actions import Action
from simulation.engine import HandEngine


@pytest.mark.parametrize(
    "b_actions,a_actions,highest,last_raise",
    [
        ([Action("check")], [Action("check")], 0, 100),
        ([Action("check"), Action("call")], [Action("bet", 100)], 100, 100),
        (
            [Action("check"), Action("raise", 300)],
            [Action("bet", 100), Action("call")],
            300,
            200,
        ),
        ([Action("bet", 100), Action("call")], [Action("raise", 300)], 300, 200),
        (
            [Action("bet", 100), Action("raise", 700)],
            [Action("raise", 300), Action("call")],
            700,
            400,
        ),
        (
            [Action("bet", 100), Action("raise", 700), Action("call")],
            [Action("raise", 300), Action("raise", 1100)],
            1100,
            400,
        ),
    ],
)
def test_postflop_check_bet_and_full_raise_call_matrix(
    b_actions, a_actions, highest, last_raise
):
    b = ScriptedBot(b_actions)
    a = ScriptedBot(a_actions)
    engine = HandEngine(a, b, seed=20)
    set_postflop(engine, "flop")
    run_round(engine, "b")
    a.assert_consumed()
    b.assert_consumed()
    assert b.observations[0].player == "b"
    assert engine.state.pending_players == set()
    assert engine.state.current_highest_bet == highest
    assert engine.state.last_full_raise_size == last_raise
    assert engine.state.current_bets["a"] == engine.state.current_bets["b"] == highest
    assert engine.illegal == 0
    assert_conserved(engine)
    engine._next_street()
    assert engine.state.street == "turn"
    assert engine.state.current_highest_bet == 0
    assert engine.state.current_bets == {"a": 0, "b": 0}
    assert engine.state.last_full_raise_size == 100
    assert engine.state.pending_players == {"a", "b"}
    assert engine.state.acted_since_full_raise == {"a": False, "b": False}
    assert engine.state.raising_reopened == {"a": True, "b": True}


@pytest.mark.parametrize(
    "b_actions,a_actions",
    [
        ([Action("check"), Action("fold")], [Action("bet", 100)]),
        (
            [Action("check"), Action("raise", 300)],
            [Action("bet", 100), Action("fold")],
        ),
        ([Action("bet", 100), Action("fold")], [Action("raise", 300)]),
        (
            [Action("bet", 100), Action("raise", 700)],
            [Action("raise", 300), Action("fold")],
        ),
        (
            [Action("bet", 100), Action("raise", 700), Action("fold")],
            [Action("raise", 300), Action("raise", 1100)],
        ),
    ],
)
def test_postflop_bet_raise_and_multiple_raise_fold_matrix(b_actions, a_actions):
    engine = HandEngine(ScriptedBot(a_actions), ScriptedBot(b_actions), seed=21)
    set_postflop(engine, "flop")
    board_before = list(engine.state.community_cards)
    run_round(engine, "b")
    assert engine.folded is not None
    assert engine.state.pending_players == set()
    assert engine.state.community_cards == board_before
    assert engine.illegal == 0
    assert_conserved(engine)


def test_one_check_does_not_close_postflop_street():
    engine = HandEngine(ScriptedBot([]), ScriptedBot([]), seed=22)
    set_postflop(engine)
    engine._action("b", Action("check"))
    assert engine.state.street == "flop"
    assert engine.state.pending_players == {"a"}
    assert engine.state.acted_since_full_raise == {"a": False, "b": True}
    assert engine.state.acting_player == "b"


@pytest.mark.parametrize(
    "street,a_actions,b_actions,board_count",
    [
        ("preflop", [Action("fold")], [], 0),
        (
            "flop",
            [Action("call"), Action("fold")],
            [Action("check"), Action("bet", 100)],
            3,
        ),
        (
            "turn",
            [Action("call"), Action("check"), Action("fold")],
            [Action("check"), Action("check"), Action("bet", 100)],
            4,
        ),
        (
            "river",
            [Action("call"), Action("check"), Action("check"), Action("fold")],
            [
                Action("check"),
                Action("check"),
                Action("check"),
                Action("bet", 100),
            ],
            5,
        ),
    ],
)
def test_fold_settlement_by_street(
    street, a_actions, b_actions, board_count
):
    engine = HandEngine(
        ScriptedBot(a_actions), ScriptedBot(b_actions), seed=23
    )
    result = engine.play()
    assert result["showdown"] is False
    assert engine.showdown_count == 0
    assert len(engine.state.community_cards) == board_count
    assert_settled(engine)
    assert engine.illegal == 0


@pytest.mark.parametrize(
    "a_actions,b_actions,board_count",
    [
        (
            [Action("call"), Action("fold")],
            [Action("check"), Action("bet", 100)],
            3,
        ),
        (
            [Action("call"), Action("raise", 300)],
            [Action("check"), Action("bet", 100), Action("fold")],
            3,
        ),
        (
            [Action("call"), Action("raise", 300), Action("fold")],
            [Action("check"), Action("bet", 100), Action("raise", 700)],
            3,
        ),
    ],
)
def test_fold_after_opening_bet_raise_and_reraise(
    a_actions, b_actions, board_count
):
    engine = HandEngine(ScriptedBot(a_actions), ScriptedBot(b_actions), seed=24)
    result = engine.play()
    assert result["showdown"] is False
    assert len(engine.state.community_cards) == board_count
    assert_settled(engine)
    assert engine.illegal == 0
