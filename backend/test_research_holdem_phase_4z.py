from math import fsum
from random import Random
from types import SimpleNamespace
from hashlib import sha256

import numpy as np
import pytest

from coach.explain import build, concretize
from coach.service import Spot, SpotAction, hand_result
from research.holdem.action_ev_reference import Ledger, evaluate_tree
from simulation.actions import Action
from solver.bot import SolverBot
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree


@pytest.mark.parametrize("outcome", [-1, 0, 1])
def test_short_call_returns_unmatched_chips(outcome):
    ledger = Ledger(501, (0, 600), (400, 0), 0, True)
    after = ledger.advance(0, "call", None)
    expected = {-1: -400, 0: 251, 1: 901}
    assert after.terminal(np.array([outcome]), 400)[0] == expected[outcome]
    assert ledger.terminal(np.array([outcome]), 400, folder=0)[0] == 0


def test_check_bet_raise_reraise_uses_actual_engine_settlement():
    # Hero plays in position. The royal board makes every showdown a tie.
    state = StreetState("river", 0, (0, 0), (2750, 2750), (250, 250), 100, acted=(False, True))
    tree = StreetTree(state, POSTFLOP_MENU)
    root = tree.nodes[tree.root]
    reply, tail = {}, {}
    for node in tree.nodes:
        if node.kind != "decision" or node is root:
            continue
        table = tail if node.player == 0 else reply
        choice = ("all_in" if "all_in" in node.labels and node.state.depth == 1
                  else "call")
        table[node.index] = np.array([float(label == choice) for label in node.labels])
    values = evaluate_tree(tree, root, Ledger(500, (0, 0), (2750, 2750), 0, False),
                           np.array([0]), reply, tail)
    prefix = [SpotAction("hero", "raise", 250), SpotAction("villain", "call")]
    prefix += [SpotAction("villain", "check"), SpotAction("hero", "check")] * 2
    prefix += [SpotAction("villain", "check")]
    for i, (kind, amount) in enumerate(root.actions):
        actions = prefix + [SpotAction("hero", kind, None if kind == "all_in" else amount)]
        if kind == "bet":
            actions += [SpotAction("villain", "all_in"), SpotAction("hero", "all_in")]
        elif kind == "all_in":
            actions += [SpotAction("villain", "all_in")]
        spot = Spot(["2c", "3c"], ["As", "Ks", "Qs", "Js", "Ts"], villain_cards=["4c", "5c"],
                    hero_stack=3000, villain_stack=3000, actions=actions)
        assert values[i, 0] == hand_result(spot)["hero_net"] + 250


def test_recommendation_draw_precedes_legalization_and_display():
    bot = SolverBot(seed=917)
    ds = SimpleNamespace(match_id="coach", hand_id="one", hand_number=1, street="river",
                         hand_actions=[None], legal_actions=["fold", "all_in"], hero_stack=400,
                         amount_to_call=600)
    token = "solver|917|coach|one|1|river|1"
    draw = Random(int.from_bytes(sha256(token.encode()).digest()[:8], "big")).random()
    p = [draw / 2, 1 - draw / 2]
    choice = bot._pick(ds, p)
    assert choice == 1 and fsum(p) == 1
    assert bot._legalize(ds, "call", None) == Action("all_in")
    raw = {"labels": ["fold", "call"], "concrete_labels": ["fold", "all_in"],
           "probabilities": p, "action_ev": [0., 3.7], "chosen": "call"}
    shown = build({"action": "all_in"}, concretize(raw))
    assert shown["chosen"] == shown["action"] == "all_in"
    assert shown["ev"] == 3.7
