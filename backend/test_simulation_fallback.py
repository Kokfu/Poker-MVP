import pytest

from scripted_test_support import ScriptedBot, assert_settled
from simulation.actions import Action
from simulation.engine import HandEngine


class MalformedBot(ScriptedBot):
    """A deliberately invalid custom bot used only to verify engine fallback."""


def malformed_check_facing_wager():
    return HandEngine(
        MalformedBot([Action("check")]), ScriptedBot([]), seed=50
    )


def malformed_raise_below_minimum():
    return HandEngine(
        MalformedBot([Action("raise", 199)]), ScriptedBot([]), seed=51
    )


def malformed_raise_above_maximum():
    return HandEngine(
        MalformedBot([Action("raise", 10001)]), ScriptedBot([]), seed=52
    )


def malformed_increasing_all_in_with_closed_rights():
    engine = HandEngine(
        MalformedBot([Action("raise", 300), Action("all_in")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=53,
    )
    engine.state.stacks["b"] = 250
    engine.total = sum(engine.state.stacks.values()) + engine.state.pot
    return engine


def malformed_call_when_only_short_all_in_is_legal():
    engine = HandEngine(
        ScriptedBot([Action("raise", 500)]),
        MalformedBot([Action("call")]),
        stack=1000,
        seed=54,
    )
    engine.state.stacks["b"] = 200
    engine.total = sum(engine.state.stacks.values()) + engine.state.pot
    return engine


@pytest.mark.parametrize(
    "factory",
    [
        malformed_check_facing_wager,
        malformed_raise_below_minimum,
        malformed_raise_above_maximum,
        malformed_increasing_all_in_with_closed_rights,
        malformed_call_when_only_short_all_in_is_legal,
    ],
    ids=[
        "check-facing-wager",
        "raise-below-minimum",
        "raise-above-maximum",
        "closed-rights-all-in",
        "call-when-short-all-in-required",
    ],
)
def test_malformed_custom_bot_fallback_matrix(factory):
    engine = factory()
    result = engine.play()
    assert result["illegal_actions"] == 1
    assert len(result["illegal_diagnostics"]) == 1
    assert result["showdown"] is False
    assert all(stack >= 0 for stack in result["stacks"].values())
    assert all(
        commitment >= 0
        for commitment in engine.state.current_bets.values()
    )
    assert sum(result["stacks"].values()) == engine.total
    assert_settled(engine)
