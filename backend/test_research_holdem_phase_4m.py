from dataclasses import replace

import numpy as np
import pytest

from coach.service import SpotAction, _replay
from research.holdem.phase_4k import STYLES
from research.holdem.phase_4l import Case, payoff_values
from research.holdem.phase_4m import (
    Reply, ResponseCounts, adjust, calibration, oracle_response, reply_context, reply_nodes,
    train_responses,
)
from research.holdem.river_ev import ExactRiverEV
from simulation.decision_state import build_decision_state
from solver.bot import replay_hand
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree


def test_effective_context_excludes_uncallable_overage_and_disallows_raise():
    # A 500-chip all-in faces a responder with 150 behind and 100 invested.
    state = StreetState("river", 1, (500, 100), (0, 150), (200, 200), 400,
                        (True, True), 2)
    tree = StreetTree(state, POSTFLOP_MENU)
    node = tree.nodes[tree.root]
    assert node.labels == ["fold", "call"]
    assert reply_context(node) == Reply(150, 600, 150, False, True)
    counts = ResponseCounts()
    counts.observe(reply_context(node), np.array([12, 12, 0]))
    baseline = np.array([[.8, .5], [.2, .5]])
    weights = np.array([.75, .25])
    forecast = adjust(node, baseline, weights, counts, True)
    assert forecast.shape == (2, 2)
    assert forecast.sum(axis=0) == pytest.approx([1, 1])
    metrics = calibration(node, {"conditioned": forecast}, forecast, weights)
    assert metrics["conditioned"]["predicted"]["raise"] == 0
    with pytest.raises(ValueError, match="illegal"):
        counts.observe(reply_context(node), np.array([0, 0, 1]))


def test_sparse_context_backs_off_and_never_borrows_across_legality():
    small = Reply(250, 500, 1250, True, False)
    large = Reply(750, 500, 1250, True, False)
    counts = ResponseCounts()
    live = np.array([.3, .4, .3])
    assert counts.target(small, live, True) is None
    counts.observe(small, np.array([10, 30, 0]))
    expected = (np.array([10, 30, 0]) + 32 * live) / 72
    assert counts.target(large, live, True) == pytest.approx(expected)
    assert counts.target(replace(large, raise_legal=False), live, True) is None
    counts.observe(large, np.array([30, 9, 1]))
    assert counts.target(large, live, True)[0] > counts.target(large, live, False)[0]
    assert counts.target(small, live, True)[0] < counts.target(small, live, False)[0]


def test_raise_fit_preserves_within_group_sizing_and_inputs():
    state = StreetState("river", 1, (150, 0), (1850, 2000), (250, 250), 150,
                        (True, True), 1)
    tree = StreetTree(state, POSTFLOP_MENU)
    node = tree.nodes[tree.root]
    assert node.labels == ["fold", "call", "raise_950", "all_in"]
    sigma = np.array([[.3, .6], [.25, .2], [.15, .05], [.3, .15]])
    weights = np.array([.6, .4])
    original = sigma.copy()
    weights.setflags(write=False)
    counts = ResponseCounts()
    assert adjust(node, sigma, weights, counts, True) is sigma
    counts.observe(reply_context(node), np.array([50, 35, 15]))
    fitted = adjust(node, sigma, weights, counts, True)
    assert np.array_equal(sigma, original)
    assert fitted.sum(axis=0) == pytest.approx([1, 1])
    assert fitted[2] / fitted[3] == pytest.approx(sigma[2] / sigma[3])


def test_training_is_seeded_and_counts_only_legal_observations():
    one = train_responses("loose_aggressive", 97, True)
    two = train_responses("loose_aggressive", 97, True)
    assert one.cells.keys() == two.cells.keys()
    assert all(np.array_equal(cell, two.cells[key]) for key, cell in one.cells.items())
    assert one.cells[(True,)][2] > 0
    assert one.cells[(False,)][2] == 0


def test_raising_reference_receipts_match_engine_at_historical_geometry():
    case = Case("test", "Kd Td", "Kh 7d 4s Qc 3h", 0)
    spot = case.spot(15)
    spot.villain_cards = ["Js", "9s"]
    status, _, engine = _replay(spot)
    assert status == "hero_to_act"
    state = replay_hand(build_decision_state(engine, "a")).current
    tree = StreetTree(state, POSTFLOP_MENU)
    root = tree.nodes[tree.root]
    first = tree.nodes[root.children[root.labels.index("bet_250")]]
    assert first.labels == ["fold", "call", "all_in"]
    after_shove = tree.nodes[first.children[first.labels.index("all_in")]]
    assert after_shove.labels == ["fold", "call"]
    exact = ExactRiverEV(tuple(spot.hero_cards), tuple(spot.board),
                        lambda cards, _: set(cards) == set(spot.villain_cards))
    weights = np.array([h.weight for h in exact.holdings])
    style = STYLES["loose_aggressive"]
    responses = {n.index: oracle_response(n, exact.holdings, style, True)
                 for n in reply_nodes(tree, root)}
    # Hero calls the shove 60% of the time. Compute each branch independently through settlement.
    values = payoff_values(tree, root, exact.holdings, weights, responses,
                           {after_shove.index: np.array([.4, .6]),
                            **{tree.nodes[n.children[n.labels.index("all_in")]].index: np.array([.4, .6])
                               for n in reply_nodes(tree, root)
                               if "all_in" in n.labels and n.labels == ["fold", "call", "all_in"]}})
    receipts = []
    lines = ((("villain", "fold"),), (("villain", "call"),),
             (("villain", "all_in"), ("hero", "fold")),
             (("villain", "all_in"), ("hero", "all_in")))
    for line in lines:
        action_line = [SpotAction("hero", "bet", 250), *(SpotAction(*step) for step in line)]
        settled, payload, _ = _replay(replace(spot, actions=spot.actions + action_line))
        assert settled == "hand_complete"
        result = payload["result"]
        assert result["illegal_actions"] == 0
        assert sum(result["stacks"].values()) == 3000
        receipts.append(result["stacks"]["a"] - 1250)
    # Js9s has high card, so it raises .02 and calls .28 conditional on declining to raise.
    expected = np.dot([.98 * .72, .98 * .28, .02 * .4, .02 * .6], receipts)
    assert values[root.labels.index("bet_250")] == pytest.approx(expected, abs=1e-10)
