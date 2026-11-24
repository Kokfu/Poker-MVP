"""Deterministic Phase 4T inference and Coach replay controls."""
from dataclasses import replace

import numpy as np
import pytest

from coach.service import _replay
from research.holdem.decoupled_replay import (
    CFRWorkingSet, DecoupledReplay, OpponentActionLikelihood, PersistentRange, hand_tiers,
)
from research.holdem.phase_4k import train
from research.holdem.phase_4r import RangeSupportError, failed_case
from research.holdem.range_support import closing_bounds
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action
from solver.bot import ReplayError, Step
from solver.combos import COMBO_COUNT, card_mask, combo_index
from solver.tree import StreetState


def test_manual_bayes_then_blocker_and_impossible_observation_are_atomic():
    ids = [combo_index(pair) for pair in (("2c", "2d"), ("6s", "7s"), ("Ac", "Ad"))]
    model = PersistentRange()
    initial = np.zeros(COMBO_COUNT)
    initial[ids] = [1., .5, .5]
    evidence = model.observe(initial)
    assert evidence == pytest.approx(2 / COMBO_COUNT)
    likelihood = np.zeros(COMBO_COUNT)
    likelihood[ids] = [.5, .25, .75]
    assert model.observe(likelihood) == pytest.approx(.5)
    assert model.weights[ids] == pytest.approx([.5, .125, .375])
    model.reveal(("Qs", "6s", "Kh"))
    assert model.weights[ids] == pytest.approx([4 / 7, 0, 3 / 7])
    before = model.weights
    with pytest.raises(RangeSupportError, match="zero model probability"):
        model.observe(np.zeros(COMBO_COUNT))
    with pytest.raises(RangeSupportError, match="blocked"):
        model.conditioned(("2c", "Ac"))
    with pytest.raises(ValueError, match="extend"):
        model.reveal(("Qs", "6s", "Ah", "3s"))
    assert model.weights is before
    assert np.count_nonzero(before) == 2
    with pytest.raises(RangeSupportError, match="required CFR holding is blocked"):
        CFRWorkingSet().select(before, model.blocked, ids[1])


def test_full_legal_law_matches_manual_open_and_closing_reply():
    board = ("2s", "5d", "9h", "Js", "Kc")
    model = PersistentRange()
    model.reveal(board)
    likelihood = OpponentActionLikelihood()
    state = StreetState("river", 1, (0, 0), (600, 600), (200, 200), 100)
    law = likelihood.distribution(state, board, model.weights)
    assert law.actions == (("check", None), ("bet", 200), ("bet", 400), ("all_in", 600))
    assert len(law.live) == 1081
    np.testing.assert_allclose(law.probabilities.sum(axis=0), 1, rtol=0, atol=1e-12)
    step = Step("river", state, 1, "all_in", 600)
    ids = [combo_index(pair) for pair in (("3c", "4c"), ("Ac", "Ad"), ("9c", "Kd"))]
    row = law.observed(step)
    assert row[ids] == pytest.approx([.25 * .18, .40 * .08, .68 * .30])
    assert (row[card_mask(board)] == 0).all()
    with pytest.raises(ValueError, match="prefix"):
        likelihood.distribution(replace(state, street="turn"), board, model.weights)

    # Opponent shoved for more than Actor's remaining stack. The all-in is a
    # short call, and there is no probability column for a raise.
    facing = replace(state, commit=(600, 0), stack=(0, 300))
    reply = likelihood.distribution(facing, board, model.weights)
    assert reply.actions == (("fold", None), ("call", None))
    np.testing.assert_allclose(reply.probabilities.sum(axis=0), 1, rtol=0, atol=1e-12)
    cover = Step("river", facing, 1, "all_in", 300)
    # The 1,000 chips already in the pot include 300 of refundable overhang.
    # The 300-chip call restores that amount in the contested pot.
    assert reply.observed(cover)[ids] == pytest.approx([.17, .54, .77])
    with pytest.raises(ReplayError, match="aggression unavailable"):
        reply.observed(Step("river", facing, 1, "raise", 1200))


@pytest.fixture(scope="module")
def varied_replays():
    case = failed_case()
    profile = train("tight_aggressive", 131, (3,))[3]
    items = []
    for selection in (CFRWorkingSet(), CFRWorkingSet(32), CFRWorkingSet(32, 17), CFRWorkingSet(32, 29)):
        bot = DecoupledReplay(selection)
        node, ds, advice = bot.trace(case.spot(), profile)
        items.append((bot, node, ds, advice))
    return items


def test_historical_replay_posterior_is_bit_identical_across_real_solves(varied_replays):
    first, *_ = varied_replays[0]
    assert first.estimate[combo_index(("6s", "7s"))] == 0
    assert np.count_nonzero(first.estimate) == 990
    assert first.solve_count == 1
    assert first.observations[-2].step.street == "turn"
    assert first.observations[-1].step.kind == "all_in"
    assert tuple(first.observations[-2].board) == tuple(first.observations[-1].board[:4])
    working_ids = []
    for bot, node, ds, advice in varied_replays:
        assert len(bot.projections) == 1
        working_ids.append(tuple(bot.projections[-1][1][1 - node.player].ids))
        assert max(len(seat.ids) for seat in bot.projections[-1][1]) <= bot.selection.limit
        np.testing.assert_array_equal(bot.estimate, first.estimate)
        assert len(bot.observations) == len(first.observations)
        for obs, other in zip(bot.observations, first.observations, strict=True):
            np.testing.assert_array_equal(obs.law.probabilities, other.law.probabilities)
            np.testing.assert_array_equal(obs.posterior, other.posterior)
            assert obs.evidence == other.evidence
            assert obs.posterior.sum() == pytest.approx(1)
            assert (obs.posterior[card_mask(obs.board)] == 0).all()
            assert np.array_equal(obs.posterior > 0, obs.prior > 0)
        assert advice["action"] in ds.legal_actions
        assert node.labels == ["fold", "call"]
        assert bot.fallback_count == 0
        assert bot.probabilities.sum() == pytest.approx(1.)
    assert len(set(working_ids)) == 4


def test_public_model_is_independent_of_villain_cards_and_repeated_edits():
    spot = failed_case().spot()
    bot = DecoupledReplay()
    _, first, _ = _replay(spot, bot)
    initial = bot.estimate.copy()
    hidden = [card for card in ("Ac", "Ad", "Kd", "Qd") if card not in (*spot.hero_cards, *spot.board)][:2]
    assert len(hidden) == 2
    _, replayed, _ = _replay(replace(spot, villain_cards=hidden), bot)
    np.testing.assert_array_equal(bot.estimate, initial)
    assert first["advice"] == replayed["advice"]
    edited = replace(spot, board=[*spot.board[:4], "2d"])
    _, actual, _ = _replay(edited, bot)
    separate = DecoupledReplay()
    _, expected, _ = _replay(edited, separate)
    assert actual["advice"] == expected["advice"]
    np.testing.assert_array_equal(bot.estimate, separate.estimate)


@pytest.mark.parametrize(("winning", "expected"), [(.5, 100), (.1, -60)])
def test_independent_closing_controls_with_exact_terminal_ev(winning, expected):
    hero, board = ("Ac", "Ad"), ("Ks", "7h", "3d", "2s", "9c")
    loser = frozenset(("Qh", "Jd"))
    winner = frozenset(("Kh", "Kd"))
    prior = lambda pair: .5 if frozenset(pair) in (loser, winner) else 0.
    like = lambda pair: winning if frozenset(pair) == loser else 1 - winning
    truth = posterior(hero, board, prior, like)
    exact = ExactRiverEV(hero, board, lambda pair, _: truth[pair])
    state = RiverState(300, 0, 100, 100, 0, 100)
    assert exact.action_ev(state, Action("fold")) == 0
    assert exact.action_ev(state, Action("all_in")) == pytest.approx(expected)
    model = PersistentRange()
    model.reveal(board)
    row = np.zeros(COMBO_COUNT)
    row[[combo_index(loser), combo_index(winner)]] = [winning, 1 - winning]
    model.observe(row)
    conditional = model.conditioned(hero)
    np.testing.assert_allclose([conditional[combo_index(pair)] for pair in truth],
                               list(truth.values()), rtol=0, atol=1e-14)
    bounds = closing_bounds(np.array([1 - winning, 0., winning]), np.array([-100, 100, 300]))
    assert bounds[0] <= expected <= bounds[1]
    assert (bounds[0] > 0) == (expected > 0)
