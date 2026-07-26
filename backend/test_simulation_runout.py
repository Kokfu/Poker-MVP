import pytest

from scripted_test_support import ScriptedBot, assert_settled
from simulation.actions import Action
from simulation.engine import HandEngine


def adjust_stack(engine, player, remaining):
    engine.state.stacks[player] = remaining
    engine.total = sum(engine.state.stacks.values()) + engine.state.pot


def preflop_all_in():
    return HandEngine(
        ScriptedBot([Action("all_in")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=40,
    )


def flop_all_in():
    return HandEngine(
        ScriptedBot([Action("call"), Action("all_in")]),
        ScriptedBot([Action("check"), Action("all_in")]),
        stack=1000,
        seed=41,
    )


def turn_all_in():
    return HandEngine(
        ScriptedBot([Action("call"), Action("check"), Action("all_in")]),
        ScriptedBot([Action("check"), Action("check"), Action("all_in")]),
        stack=1000,
        seed=42,
    )


def exact_all_in_call():
    engine = HandEngine(
        ScriptedBot([Action("raise", 500)]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=43,
    )
    adjust_stack(engine, "b", 400)
    return engine


def short_all_in_call():
    engine = HandEngine(
        ScriptedBot([Action("raise", 500)]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=44,
    )
    adjust_stack(engine, "b", 200)
    return engine


def short_all_in_raise_then_call():
    engine = HandEngine(
        ScriptedBot([Action("raise", 300), Action("call")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=45,
    )
    adjust_stack(engine, "b", 250)
    return engine


def full_all_in_raise_then_call():
    engine = HandEngine(
        ScriptedBot([Action("raise", 200), Action("call")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=46,
    )
    adjust_stack(engine, "b", 400)
    return engine


@pytest.mark.parametrize(
    "factory",
    [
        preflop_all_in,
        flop_all_in,
        turn_all_in,
        exact_all_in_call,
        short_all_in_call,
        short_all_in_raise_then_call,
        full_all_in_raise_then_call,
    ],
    ids=[
        "preflop",
        "flop",
        "turn",
        "exact-call",
        "short-call",
        "short-raise-call",
        "full-raise-call",
    ],
)
def test_automatic_all_in_runout_matrix(factory):
    engine = factory()
    result = engine.play()
    for bot in engine.bots.values():
        bot.assert_consumed()
    all_cards = engine.holes["a"] + engine.holes["b"] + engine.state.community_cards
    assert len(engine.state.community_cards) == 5
    assert len(all_cards) == len(set(all_cards)) == 9
    assert result["showdown"] is True
    assert engine.showdown_count == 1
    assert engine.illegal == 0
    assert_settled(engine)
    assert (
        result["stacks"]["a"] + result["stacks"]["b"] == engine.total
    )


def test_scripted_observations_hide_all_unrevealed_information():
    engine = turn_all_in()
    engine.play()
    final_board = engine.state.community_cards
    for player, bot in engine.bots.items():
        opponent = engine.other(player)
        for observation in bot.observations:
            assert observation.hole_cards == engine.holes[player]
            assert not set(engine.holes[opponent]) & set(observation.hole_cards)
            assert observation.community_cards == final_board[
                : len(observation.community_cards)
            ]
            assert not hasattr(observation, "opponent_hole_cards")
            assert not hasattr(observation, "deck")
            assert set(observation.community_cards).isdisjoint(
                set(engine.holes["a"] + engine.holes["b"])
            )
