"""Regression coverage for the opt-in live belief owner."""
from dataclasses import replace

import numpy as np
import pytest

from coach.service import _replay, advise
from research.holdem.decoupled_replay import CFRWorkingSet
from research.holdem.live_persistent import ReplayBeliefs
from research.holdem.phase_4r import RangeSupportError
from research.holdem.phase_4v import FixtureStore, coach_prefixes, coach_spot, stable, verify_history
from simulation.history_service import hand_history_from_dict, run_builtin_match_history
from simulation.match_service import build_match_bot
from solver.bot import SolverBot
from solver.combos import COMBO_COUNT, combo_index


def test_sparse_updates_are_atomic_and_solve_inputs_are_detached():
    beliefs = ReplayBeliefs(0, ("As", "Kd"))
    hero = combo_index(beliefs.hero_cards)
    ids = [combo_index(pair) for pair in (("2c", "2d"), ("6s", "7s"), ("Ac", "Ad"), ("As", "Ah"))]
    likelihood = np.zeros(COMBO_COUNT)
    likelihood[ids] = [.5, .2, .3, .7]
    beliefs.observe(1, likelihood)
    assert beliefs.opponent[ids] == pytest.approx([.5, .2, .3, 0.])
    beliefs.reveal(("Qh", "Jh", "8d"))
    prior = beliefs.opponent
    for selector in (CFRWorkingSet(1), CFRWorkingSet(2, 17), CFRWorkingSet()):
        working = beliefs.project(hero, selector)
        assert len(working.ids[1]) <= selector.limit
        assert 0 <= working.omitted_opponent_mass <= 1
        assert not np.shares_memory(working.reaches[1], beliefs.public_reaches[1].weights)
        working.reaches[1].fill(0.)
        assert beliefs.opponent is prior
    beliefs.reveal(("Qh", "Jh", "8d", "6s"))
    beliefs.reveal(("Qh", "Jh", "8d", "6s", "2c"))
    assert beliefs.opponent[ids].tolist() == [0., 0., 1., 0.]
    snapshot = beliefs.public_reaches, beliefs.opponent
    only_blocked_by_hero = np.zeros(COMBO_COUNT)
    only_blocked_by_hero[ids[-1]] = 1.
    with pytest.raises(RangeSupportError, match="blocked"):
        beliefs.observe(1, only_blocked_by_hero)
    with pytest.raises(RangeSupportError, match="zero model probability"):
        beliefs.observe(1, np.zeros(COMBO_COUNT))
    assert beliefs.public_reaches is snapshot[0] and beliefs.opponent is snapshot[1]


def test_profiled_coach_collapse_repaired_and_flag_disabled_matches(monkeypatch):
    monkeypatch.delenv("POKER_COACH_PERSISTENT_RANGES", raising=False)
    spot = coach_spot("collapse-profiled")
    name = "tight_aggressive"
    store = FixtureStore(name, 131, 3)
    prefixes = coach_prefixes(spot)
    river = prefixes[-2]
    disabled = advise(river, name, store=store, seed=917)
    assert disabled["explanation"]["source"] == "fallback"
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", "0")
    assert stable(advise(river, name, store=store, seed=917)) == stable(disabled)
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", "1")

    def destructive_writeback(*args):
        pytest.fail("enabled replay used the legacy CFR writeback")

    monkeypatch.setattr(SolverBot, "_apply_strategy", destructive_writeback)
    for prefix in prefixes[:-1]:
        result = advise(prefix, name, store=store, seed=917)
        info = result["explanation"]
        assert info["source"] != "fallback"
        assert info["range_ownership"]["opponent_total"] == pytest.approx(1., abs=1e-12)
        assert result["advice"]["action"] in result["state"]["legal_actions"]
        assert sum(info["probabilities"]) == pytest.approx(1., abs=.001)
    assert info["range_ownership"]["opponent_positive"] == 990
    assert stable(advise(river, name, store=store, seed=917)) == stable(result)
    assert advise(spot, name, store=store)["status"] == "hand_complete"


def test_live_range_zero_support_uses_explicit_fallback(monkeypatch):
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", "1")
    spot = next(p for p in coach_prefixes(coach_spot("tight_passive")) if len(p.board) == 3)
    original = ReplayBeliefs.observe

    def zero_opponent(beliefs, player, likelihood):
        return original(beliefs, player, np.zeros_like(likelihood) if player == beliefs.villain else likelihood)

    monkeypatch.setattr(ReplayBeliefs, "observe", zero_opponent)
    result = advise(spot)
    assert result["explanation"]["source"] == "fallback"
    assert "zero model probability" in result["explanation"]["reason"]
    assert result["advice"]["action"] in result["state"]["legal_actions"]


def test_short_all_in_is_replayed_and_refunded(monkeypatch):
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", "1")
    spot = coach_spot("tight_aggressive")
    before_call = replace(spot, actions=spot.actions[:-1])
    advice = advise(before_call)
    assert advice["explanation"]["source"] == "postflop_solve"
    assert advice["advice"]["action"] in {"fold", "all_in"}
    status, payload, _ = _replay(spot)
    assert status == "hand_complete"
    timeline = verify_history(payload["result"]["history"])
    assert [row["amount_paid"] for row in timeline if row["all_in_classification"] == "short_call"] == [500]
    assert [row["returned_amount"] for row in timeline if row["event_type"] == "unmatched_excess_returned"] == [1500]


def test_match_flags_are_independent_and_histories_replay(monkeypatch):
    options = dict(bot_a="solver", bot_b="tight", seed=42, max_hands=2, starting_stack=1500,
                   equity_iterations=500)
    monkeypatch.delenv("POKER_MATCH_PERSISTENT_RANGES", raising=False)
    baseline = run_builtin_match_history(**options)
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", "1")
    assert run_builtin_match_history(**options) == baseline
    monkeypatch.setenv("POKER_MATCH_PERSISTENT_RANGES", "1")
    for name in ("solver", "solver_adaptive", "solver_adaptive_gated", "solver_adaptive_sized"):
        assert build_match_bot(name, 0, 500).persistent_ranges
    repaired = run_builtin_match_history(**options)
    assert repaired == run_builtin_match_history(**options)
    assert repaired["aggregate_validation"]["valid"]
    assert not repaired["aggregate_fallback_count"]
    for record in repaired["histories"]:
        verify_history(hand_history_from_dict(record))
