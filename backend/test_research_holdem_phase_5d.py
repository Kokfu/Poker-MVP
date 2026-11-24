"""Deterministic controls for the Phase 5D offline measurement."""
import numpy as np

from research.holdem import phase_5d as study
from research.holdem.action_ev_reference import Ledger
from research.holdem.live_persistent import ReplayBeliefs
from research.holdem.phase_4k import STYLES
from solver.combos import card_mask, combo_index
from solver.tree import StreetState, StreetTree


def test_range_scores_missing_mass_and_calibration():
    q, p = np.array([.5, .3, .2]), np.array([.75, .25, 0])
    report = study.range_metrics(p, q, np.array([0, 1, 2]), np.array([-1, 0, 1]))
    assert report["tv"] == .25
    assert report["missing_mass"] == .2
    assert report["effective"][0] == 1.6
    np.testing.assert_allclose(report["brier"], 1 + p @ p - 2 * p @ q)
    assert report["excess_log_loss"] > 4
    assert sum(row[1] for row in report["reliability"]) == 1


def test_persistent_projection_preserves_all_beliefs_and_excludes_blockers():
    cards = ("Ac", "Ad")
    beliefs = ReplayBeliefs(0, cards)
    beliefs.reveal(("2c", "3c", "4c"))
    villain = beliefs.opponent.copy()
    small = beliefs.project(combo_index(cards), study.CFRWorkingSet(64))
    large = beliefs.project(combo_index(cards), study.CFRWorkingSet(384))
    assert small.omitted_opponent_mass > large.omitted_opponent_mass > 0
    np.testing.assert_array_equal(villain, beliefs.opponent)
    assert not np.any(villain[card_mask((*cards, *beliefs.board))])
    assert not beliefs.opponent.flags.writeable


def test_reply_forecast_at_shared_anchor_and_closing_refund():
    ranks = np.array([0, 1, 2])
    style = STYLES["tight_aggressive"]
    np.testing.assert_array_equal(study.continues(ranks, style, .5, 1, False),
                                  study.continues(ranks, style, .5, -1, False))
    state = StreetState("river", 1, (900, 0), (0, 400), (500, 500), 900, (True, False), 1)
    tree = StreetTree(state, study.PROBE_MENU)
    node = tree.nodes[tree.root]
    assert node.labels == ["fold", "call"]
    assert study.price(state, 1) == (400, 1000, 500)
    p = study.reference_replies(node, ranks, style, 1)
    q = study.reference_replies(node, ranks, style, -1)
    assert np.all(p[0] > q[0])
    np.testing.assert_allclose(p.sum(axis=0), 1)
    assert study.reply_class(node, "call", 400) == "closing_call"
    cash = Ledger(1000, (900, 0), (0, 400), 0, False)
    called = cash.advance(1, "call", None)
    np.testing.assert_array_equal(called.terminal(np.array([1, 0, -1]), 0), [2300, 1400, 500])


def test_reference_replies_assign_mass_to_legal_raises_reraises_and_checks():
    state = StreetState("river", 0, (0, 0), (5000, 5000), (500, 500), 100)
    tree = StreetTree(state, study.PROBE_MENU)
    tiers = np.array([0, 1, 2])
    kinds = set()
    for node in tree.nodes:
        if node.kind != "decision":
            continue
        reply = study.reference_replies(node, tiers, STYLES["loose_aggressive"], -1)
        np.testing.assert_allclose(reply.sum(axis=0), 1)
        assert np.all(reply > 0)
        for kind, _ in node.actions:
            kinds.add(study.reply_class(node, kind, study.price(node.state, node.player)[0]))
    assert {"check", "fold", "call", "raise", "reraise", "all_in"} <= kinds
