from types import SimpleNamespace

import numpy as np
import pytest

from research.holdem.action_ev_reference import Ledger, evaluate_tree
from research.holdem.phase_5a import (
    RiverField, branch_values, concrete_keys, cfr_values, exact_subset, project, validate_reply,
)
from research.holdem.river_ev import ExactRiverEV, RiverState
from solver.tree import SizeMenu, StreetState, StreetTree


@pytest.mark.parametrize("fold_rate", [.2, .4])
def test_known_pure_bluff_price_grid(fold_rate):
    board = ("2c", "4d", "7h", "9s", "Jc")
    hero, villain = ("3c", "5c"), {"Ah", "Ad"}
    # The second nonzero input collides with Hero, so its mass must disappear.
    hands = ExactRiverEV(hero, board, lambda combo, _: 2 if set(combo) == villain else
                         200 if set(combo) == {"3c", "As"} else 0)
    assert len(hands.holdings) == 990 and hands.equity == 0
    assert [(set(h.combo), h.weight) for h in hands.holdings if h.weight] == [(villain, 1)]
    weights = np.array([h.weight for h in hands.holdings])
    outcomes = np.array([h.result for h in hands.holdings])
    menu = SizeMenu(((.25, .5, 1., 1.5),), all_in_merge=1.)
    tree = StreetTree(StreetState("river", 0, (0, 0), (200, 200), (50, 50), 10, (False, True)), menu)
    root = tree.nodes[0]
    ds = SimpleNamespace(legal_actions=("check", "bet", "all_in"), minimum_legal_target=10,
                         maximum_legal_target=200)
    keys = concrete_keys(ds, root)
    replies, tail = {}, {}
    for node in tree.nodes[1:]:
        if node.kind != "decision":
            continue
        if node.player == 0:
            tail[node.index] = np.array([float(k == "call") for k in node.labels])
            continue
        probs = [fold_rate if k == "fold" else 1 - fold_rate if k == "call" else 0 for k in node.labels]
        replies[node.index] = np.tile(probs, (len(weights), 1)).T
        validate_reply(node, replies[node.index], len(weights))
    expected = [0] + [fold_rate * 100 - (1 - fold_rate) * price for price in (25, 50, 100, 150, 200)]
    g = Ledger(100, (0, 0), (200, 200), 0, True)
    full = branch_values(tree, root, g, outcomes, replies, tail) @ weights
    exact = exact_subset(tree, root, RiverState(100, 0, 0, 200, 200, 10, checked_to=True),
                         keys, RiverField(hero, board, hands.holdings), weights, replies)
    # A live re-raise subtree exists even with zero probability of reaching it.
    # The candidate accepts complete conditional laws for those unreachable nodes.
    assert list(exact.values()) == pytest.approx(expected)
    raw, mix = cfr_values(tree, weights, outcomes, replies, tail, project(weights, 896), 80)
    np.testing.assert_allclose(raw, expected, atol=1e-5, rtol=0)
    np.testing.assert_allclose(full, expected, atol=1e-10, rtol=0)
    assert keys[np.argmax(mix)] == ("check" if fold_rate == .2 else "bet_25")


@pytest.mark.parametrize("win_probability,net", [(.1, -28), (.4, 8)])
def test_short_shove_call_with_refund(win_probability, net):
    tree = StreetTree(StreetState("river", 1, (60, 0), (0, 40), (20, 20), 60, (True, False)),
                      SizeMenu(((),)))
    root = tree.nodes[0]
    weights = np.array([win_probability, 1 - win_probability])
    outcomes = np.array([1, -1])
    g = Ledger(40, (60, 0), (0, 40), 1, True)
    reference = evaluate_tree(tree, root, g, outcomes, {}, {}) @ weights
    cfr, _ = cfr_values(tree, weights, outcomes, {}, {}, project(weights, 896), 80)
    np.testing.assert_allclose(reference, [0, net], rtol=0, atol=1e-12)
    np.testing.assert_allclose(cfr, reference, rtol=0, atol=1e-5)


def test_reraise_tree_and_tie():
    state = StreetState("river", 0, (0, 0), (500, 500), (50, 50), 10, (False, True))
    tree = StreetTree(state, SizeMenu(((.25,), (.5,), (.5,), (.5,)), all_in_merge=1.))
    root, replies, tail = tree.nodes[0], {}, {}
    for node in tree.nodes[1:]:
        if node.kind != "decision":
            continue
        # Bet 25, raise to 100, reraise to 250, call. Hero's tie nets 50.
        key = next((key for key in node.labels if key.startswith("raise_")), "call") if node.state.depth < 3 else "call"
        probs = np.array([float(k == key) for k in node.labels])
        (tail if node.player == 0 else replies)[node.index] = probs if node.player == 0 else probs[:, None]
    g = Ledger(100, (0, 0), (500, 500), 0, True)
    predicted = branch_values(tree, root, g, np.array([0]), replies, tail)
    assert predicted[:, 0].tolist() == [50, 50, 50]
    assert any(node.kind == "leaf" and node.state.commit == (250, 250) for node in tree.nodes)


def test_invalid_reply_and_projection_are_deterministic():
    node = SimpleNamespace(actions=(("fold", None), ("call", None)))
    with pytest.raises(AssertionError, match="invalid concrete reply law"):
        validate_reply(node, np.array([[.9], [.2]]), 1)
    assert project(np.array([.2, .4, .4, 0]), 2).tolist() == [1, 2]
