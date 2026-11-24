"""Phase 4V controls using real Coach and Match entry points."""
import json

import numpy as np
import pytest

from coach import service as coach
from research.holdem.decoupled_replay import CFRWorkingSet, PersistentRange
from research.holdem.phase_4r import RangeSupportError
from research.holdem.phase_4v import (
    FixtureStore, coach_prefixes, coach_spot, compare_arms, research_matrix,
    run_coach, run_match, verify_history,
)
from simulation.history_service import hand_history_from_dict
from solver.combos import COMBO_COUNT, combo_index


def test_live_coach_multiple_streets_preserve_raw_policy_and_profile():
    name = "tight_passive"
    spot = coach_spot(name)
    prefixes = coach_prefixes(spot)
    store = FixtureStore(name)
    baseline, _ = run_coach(prefixes, name, store, False)
    traced, contexts = run_coach(prefixes, name, store, True)
    compare_arms(baseline, traced)
    assert [row["input"]["street"] for row in traced["decisions"]] == ["preflop", "flop", "turn", "river"]
    assert all(row["source"] != "fallback" for row in traced["decisions"])
    assert all(profile.hands_observed == 3 for _, profile, _ in contexts)
    assert "hole_cards" not in json.dumps(traced)
    assert traced["responses"][-1]["status"] == "hand_complete"


def test_closing_short_call_refunds_excess_and_settles():
    status, payload, _ = coach._replay(coach_spot("tight_aggressive"))
    assert status == "hand_complete"
    timeline = verify_history(payload["result"]["history"])
    short_call = [row for row in timeline if row["all_in_classification"] == "short_call"]
    refund = [row for row in timeline if row["event_type"] == "unmatched_excess_returned"]
    assert len(short_call) == len(refund) == 1
    assert short_call[0]["amount_paid"] == 500
    assert refund[0]["returned_amount"] == 1500 and refund[0]["returned_to"] == "b"
    assert refund[0]["pot_after"] == 3000


def test_sparse_observation_blockers_and_projection_are_independent():
    reach = PersistentRange()
    ids = [combo_index(pair) for pair in (("2c", "2d"), ("6s", "7s"), ("Ac", "Ad"))]
    likelihood = np.zeros(COMBO_COUNT)
    likelihood[ids] = [.5, .2, .3]
    reach.observe(likelihood)
    reach.reveal(("Qh", "Jh", "8d"))
    initial = reach.weights.copy()
    for selection in (CFRWorkingSet(1), CFRWorkingSet(2, 17), CFRWorkingSet()):
        selected = selection.select(reach.weights, reach.blocked, None)
        assert len(selected.ids) <= selection.limit
        np.testing.assert_array_equal(reach.weights, initial)
    reach.reveal(("Qh", "Jh", "8d", "6s"))
    reach.reveal(("Qh", "Jh", "8d", "6s", "2c"))
    assert reach.weights[ids].tolist() == [0., 0., 1.]
    with pytest.raises(RangeSupportError, match="zero model probability"):
        reach.observe(1 - (reach.weights > 0))
    with pytest.raises(RangeSupportError):
        reach.reveal((*reach.board, "Ac"))
    assert reach.weights[ids].tolist() == [0., 0., 1.]


def test_projection_invariance_at_successive_street_decisions():
    prefixes = coach_prefixes(coach_spot("collapse"))
    for prefix in (prefix for prefix in prefixes if len(prefix.board) >= 4):
        status, _, engine = coach._replay(prefix)
        if status != "hero_to_act":
            continue
        context = engine.decision_observation("a").decision_state
        rows = research_matrix(context, None, None, True)
        assert len(rows) == 12
        assert len({tuple(seat["board"]["columns"] for seat in row["seats"]) for row in rows}) > 1


def test_match_trace_preserves_history_and_settlement():
    options = dict(bot_a="solver", bot_b="tight", seed=42, max_hands=1, starting_stack=1500,
                   equity_iterations=500)
    baseline, _ = run_match(options, False)
    traced, _ = run_match(options, True)
    compare_arms(baseline, traced)
    document = traced["responses"]
    assert len(document["histories"]) == 1 and traced["decisions"]
    for history in document["histories"]:
        verify_history(hand_history_from_dict(history))
