"""Phase 5H: showdown-learned strength correlation for node locks."""
import numpy as np
import pytest

from simulation.actions import Action
from simulation.bots import BOT_TYPES, PokerBot
from simulation.engine import HandEngine
from solver.cfr import RangeSolver
from solver.showdown import ShowdownModel, hand_percentile
from solver.tree import SizeMenu, StreetState, StreetTree


class CallingStation(PokerBot):
    def decide(self, o):
        return Action("check") if "check" in o.legal_actions else Action("call") if "call" in o.legal_actions else Action("fold")


def observe(opponent_bot: str, hands: int) -> ShowdownModel:
    model = ShowdownModel()
    for seed in range(hands):
        engine = HandEngine(CallingStation(seed=seed), BOT_TYPES[opponent_bot](seed=seed), starting_stacks={"a": 10_000, "b": 10_000},
                            bb=100, seed=77_000 + seed, button="a" if seed % 2 else "b")
        model.observe(engine.play()["history"], "b")
    return model


def test_hand_percentiles():
    assert hand_percentile(("As", "Ah"), ()) > 0.99
    assert hand_percentile(("7d", "2c"), ()) < 0.05
    assert hand_percentile(("Ks", "Qs"), ("As", "Js", "Ts", "2d", "3c")) > 0.99
    assert hand_percentile(("4d", "5h"), ("As", "Js", "Ts", "2d", "9c")) < 0.1


def test_maniac_is_uncorrelated_and_tight_player_is_ordered():
    maniac = observe("aggressive", 120)
    tight = observe("tight", 120)
    assert maniac.percentiles["aggressive"] and tight.percentiles["aggressive"]
    assert maniac.correlation("aggressive") < 0.5
    assert tight.correlation("aggressive") > 0.7
    assert ShowdownModel().correlation("aggressive") == 1.0  # default: strength-ordered


def test_fold_ended_hands_reveal_nothing():
    model = ShowdownModel()
    engine = HandEngine(BOT_TYPES["tight"](seed=1), BOT_TYPES["aggressive"](seed=1), starting_stacks={"a": 10_000, "b": 10_000}, bb=100, seed=5, button="a")
    history = engine.play()["history"]
    model.observe(history, "b")
    if not history.showdown:
        assert model.percentiles == {"aggressive": [], "call": []}
    assert model.hands == 1


def test_uncorrelated_lock_makes_every_combo_take_the_observed_mix():
    root = StreetState("river", 0, (0, 0), (100, 100), (50, 50), 10)
    tree = StreetTree(root, SizeMenu(by_depth=((1.0,),), all_in_merge=1.01))
    root_node = tree.nodes[tree.root]
    bet = root_node.labels.index("all_in")
    check = root_node.labels.index("check")
    solver = RangeSolver(tree, (np.array([0.5, 0.5]), np.array([1.0])), np.array([[1.0], [-1.0]]), np.ones((2, 1), bool),
                         locks={tree.root: (1.0, (((bet,), 0.6), ((check,), 0.4)), 0.0)})
    policy = solver.solve(50).average
    assert policy[tree.root][bet] == pytest.approx([0.6, 0.6], abs=0.01)  # nuts and air bet equally often
