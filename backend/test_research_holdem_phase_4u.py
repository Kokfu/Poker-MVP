"""Deterministic Phase 4U reply and strategy controls."""
from dataclasses import replace

import numpy as np
import pytest

from coach.service import _replay
from research.holdem.decoupled_replay import CFRWorkingSet, DecoupledReplay
from research.holdem.phase_4q import cases
from research.holdem.reply_forecast import (
    ResponseAssumptions, forecast, gate, holding_values, posterior_models, prepare_evaluation,
    proposed_mix, reply_geometry, scenario_values,
)
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree


@pytest.mark.parametrize(("wager", "price", "expected"), [
    ("bet_200", 200, [1/4, 1/2, 3/4]),
    ("bet_400", 400, [2/11, 2/5, 2/3]),
    ("all_in", 1500, [19/154, 19/64, 19/34]),
])
def test_price_and_hand_dependent_normalized_forecast(wager, price, expected):
    tree = StreetTree(StreetState("river", 0, (0, 0), (1500, 1500), (200, 200),
                                  100, (False, True)), POSTFLOP_MENU)
    root = tree.nodes[tree.root]
    reply = tree.nodes[root.children[root.labels.index(wager)]]
    geometry = reply_geometry(reply.state)
    assert (geometry.cost, geometry.pot_before_call) == (price, 400 + price)
    sigma = forecast(reply, np.array([0, 1, 2]), ResponseAssumptions.from_counts(0, 0, 0))
    np.testing.assert_allclose(1 - sigma[reply.labels.index("fold")], expected, rtol=0, atol=1e-12)
    assert sigma.sum(axis=0) == pytest.approx(np.ones(3))
    if wager == "all_in":
        assert reply.labels == ["fold", "call"]
    else:
        aggression = sigma[2:].sum(axis=0)
        # Anchor Beta(1, 7), strength odds multiplier and stack discount.
        tilt = np.array([1/3, 1, 3]) / (1 + price / 1500)
        np.testing.assert_allclose(aggression, np.array(expected) * tilt / (7 + tilt), rtol=0, atol=1e-12)
        assert "all_in" in reply.labels


def test_short_call_refund_and_contested_payoffs():
    # Opponent's already observed shove exceeds our stack by 300. Both
    # independent showdown accounting and the tree must return the excess.
    state = StreetState("river", 0, (0, 600), (300, 0), (200, 200), 600, (False, True), 1)
    tree = StreetTree(state, POSTFLOP_MENU)
    root = tree.nodes[tree.root]
    geometry = reply_geometry(state)
    assert (geometry.cost, geometry.refundable, geometry.pot_before_call) == (300, 300, 700)
    assert root.labels == ["fold", "call"]
    assert sum(tree.nodes[root.children[1]].contribution) == 1000
    np.testing.assert_array_equal(holding_values(tree, root, np.array([-1, 0, 1]), {}, {}, False),
                                  [[0, 0, 0], [-300, 200, 700]])
    sigma = forecast(root, np.array([0, 1, 2]), ResponseAssumptions.from_counts(0, 0, 0))
    # Equivalent collectible price has identical replies without the overhang.
    capped = replace(state, commit=(0, 300))
    capped_tree = StreetTree(capped, POSTFLOP_MENU)
    np.testing.assert_array_equal(sigma, forecast(capped_tree.nodes[0], np.array([0, 1, 2]),
                                                 ResponseAssumptions.from_counts(0, 0, 0)))


@pytest.mark.parametrize(("p_win", "call_ev"), [(.5, 200), (.1, -200)])
def test_closing_reference_and_paired_gate(p_win, call_ev):
    win = frozenset(("Qh", "Jd"))
    lose = frozenset(("Kh", "Kd"))
    exact = ExactRiverEV(("Ac", "Ad"), ("Ks", "7h", "3d", "2s", "9c"),
                         lambda pair, _: p_win if frozenset(pair) == win else
                         1 - p_win if frozenset(pair) == lose else 0.)
    state = RiverState(1000, 0, 600, 300, 0, 600)
    values = np.array([exact.action_ev(state, Action("fold")), exact.action_ev(state, Action("all_in"))])
    assert values == pytest.approx([0, call_ev])
    incumbent = np.array([.2, .8])
    proposal = proposed_mix(incumbent, values)
    accepted_mix, bounds, accepted = gate(incumbent, proposal, np.stack((values, values * .5)))
    assert accepted and bounds[0] > 0
    np.testing.assert_array_equal(accepted_mix, proposal)
    kept, bounds, accepted = gate(incumbent, proposal, np.stack((values, -values)))
    assert not accepted and bounds[0] < 0 < bounds[1]
    np.testing.assert_array_equal(kept, incumbent)


def test_sparse_and_supported_uncertainty_from_known_counts():
    sparse = ResponseAssumptions.from_counts(0, 0, 0)
    supported = ResponseAssumptions.from_counts(50, 44, 6)
    assert sparse.continue_at_half_pot == pytest.approx([.0125, .5, .9875])
    assert sparse.raise_given_continue[1] == .125
    assert supported.continue_at_half_pot[1] == .5
    assert supported.raise_given_continue[1] == pytest.approx(7/58)
    for a, b in zip((sparse.continue_at_half_pot, sparse.raise_given_continue),
                    (supported.continue_at_half_pot, supported.raise_given_continue), strict=True):
        assert a[0] < b[0] < b[2] < a[2]


def test_exact_fold_call_replies_and_legal_raise_receipts():
    state = StreetState("river", 0, (0, 0), (1500, 1500), (200, 200), 100, (False, True))
    tree = StreetTree(state, POSTFLOP_MENU)
    root = tree.nodes[tree.root]
    bets = [tree.nodes[root.children[root.labels.index(wager)]] for wager in ("bet_200", "bet_400", "all_in")]
    replies, hero_policy = {}, {}
    for node in tree.nodes:
        if node.kind == "decision" and node.player == 1:
            replies[node.index] = np.eye(len(node.labels))[:, :1]  # fold by default
        elif node.kind == "decision" and node.index != root.index:
            hero_policy[node.index] = np.eye(len(node.labels))[:, node.labels.index("call")]
    for node, call in zip(bets, (.25, .75, .5), strict=True):
        replies[node.index][:2, 0] = [1 - call, call]
    # With a losing hand, a fold wins 400 and a call loses the wager.
    ev = holding_values(tree, root, np.array([-1]), replies, hero_policy, False)
    assert ev[:, 0] == pytest.approx([0, 250, -200, -550])
    # Route the small bet into a legal raise and call it with a winning hand.
    reply = bets[0]
    raise_index = next(i for i, label in enumerate(reply.labels) if label.startswith("raise_"))
    target = reply.actions[raise_index][1]
    replies[reply.index][:, 0] = np.eye(len(reply.labels))[:, raise_index]
    won = holding_values(tree, root, np.array([1]), replies, hero_policy, False)
    assert won[1, 0] == 400 + target


def test_reply_forecasts_ignore_hidden_cards_and_working_set():
    case = list(cases(441201, 4, 0))[1]
    spot = case.spot()
    hidden = [card for card in ("Ac", "Ad", "Kd", "Qd") if card not in (*spot.hero_cards, *spot.board)][:2]
    traces = []
    for selection, edited in ((CFRWorkingSet(), spot),
                              (CFRWorkingSet(32, 17), replace(spot, villain_cards=hidden)),
                              (CFRWorkingSet(32, 29), spot)):
        bot = DecoupledReplay(selection)
        status, _, _ = _replay(edited, bot)
        assert status == "hero_to_act" and not bot.fallback_count
        bot.live_node = bot.river.tree.nodes[bot.river.tree.root]
        evaluation = prepare_evaluation(bot, None)
        ranges = posterior_models(bot, evaluation.ids)
        replies = evaluation.forecasts()
        assert replies and len(evaluation.ids) == 990
        assert all(np.isclose(weights.sum(), 1) for weights in ranges.values())
        assert np.isfinite(scenario_values(evaluation, ranges, evaluation.values(replies))).all()
        traces.append((bot.observations, ranges, replies))
    for observations, ranges, replies in traces[1:]:
        for original, other in zip(traces[0][0], observations, strict=True):
            np.testing.assert_array_equal(original.law.probabilities, other.law.probabilities)
        for key, weights in ranges.items():
            np.testing.assert_array_equal(weights, traces[0][1][key])
        for key, probabilities in replies.items():
            np.testing.assert_array_equal(probabilities, traces[0][2][key])
