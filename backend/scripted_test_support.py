"""Test-only helpers for deterministic heads-up betting acceptance tests."""

from dataclasses import dataclass
from typing import Callable

from simulation.actions import Action
from simulation.engine import HandEngine
from simulation.game_state import GameState, Observation


AssertionCallback = Callable[[Observation | GameState], None]


@dataclass(frozen=True)
class ScriptedStep:
    action: Action
    before: AssertionCallback | None = None
    after: AssertionCallback | None = None


class ScriptedBot:
    def __init__(self, actions: list[Action | ScriptedStep]):
        self._steps = [
            action if isinstance(action, ScriptedStep) else ScriptedStep(action)
            for action in actions
        ]
        self.observations: list[Observation] = []
        self.consumed_action_count = 0
        self._pending_after: AssertionCallback | None = None

    def decide(self, observation: Observation) -> Action:
        if not self._steps:
            raise AssertionError("unexpected extra decision")
        step = self._steps.pop(0)
        self.observations.append(observation)
        if step.before:
            step.before(observation)
        self._pending_after = step.after
        self.consumed_action_count += 1
        return step.action

    def assert_after_action(self, state: GameState) -> None:
        if self._pending_after:
            callback, self._pending_after = self._pending_after, None
            callback(state)

    def assert_consumed(self) -> None:
        if self._steps:
            raise AssertionError(f"{len(self._steps)} scripted action(s) remain unused")
        if self._pending_after:
            raise AssertionError("the final after-action assertion was not called")


def act(engine: HandEngine, player: str, action: Action) -> str:
    """Apply an action and run the ScriptedBot after-action callback, if present."""
    result = engine._action(player, action)
    bot = engine.bots[player]
    if isinstance(bot, ScriptedBot):
        bot.assert_after_action(engine.state)
    return result


def run_round(engine: HandEngine, first: str):
    """Run a betting round and support ScriptedBot after-action callbacks."""
    original = engine._action

    def wrapped(player: str, action: Action):
        result = original(player, action)
        bot = engine.bots[player]
        if isinstance(bot, ScriptedBot):
            bot.assert_after_action(engine.state)
        return result

    engine._action = wrapped
    try:
        return engine._round(first)
    finally:
        engine._action = original


def set_postflop(engine: HandEngine, street: str = "flop") -> None:
    while engine.state.street != street:
        engine._next_street()


def assert_conserved(engine: HandEngine) -> None:
    assert sum(engine.state.stacks.values()) + engine.state.pot == engine.total
    assert all(stack >= 0 for stack in engine.state.stacks.values())
    assert all(committed >= 0 for committed in engine.state.current_bets.values())


def assert_settled(engine: HandEngine) -> None:
    assert engine.state.street == "complete"
    assert engine.state.pot == 0
    assert engine.state.current_bets == {"a": 0, "b": 0}
    assert engine.state.pending_players == set()
    assert engine.settlement_count == 1
    assert sum(engine.state.stacks.values()) == engine.total
