"""Independent evidence and exact incumbent fallback regressions."""
from dataclasses import replace

import pytest

from coach import service as coach
from research.holdem.opponent_profile_v2 import extract, forecast
from research.holdem.phase_4k import river_spot
from research.holdem.phase_5e import incumbent
from research.holdem.profile_v2_hybrid import Evidence, EvidenceProfile, hybrid_forecast
from simulation.history_service import hand_history_from_dict
from simulation.opponent_model import OpponentModel


def observed(price, reply, *, hero_stack=1500, villain_stack=2500, hidden=("As", "Ad")):
    spot = replace(river_spot("9h 9d", "Kc 9s 3d 5h Js", 0),
                   villain_cards=list(hidden), hero_stack=hero_stack, villain_stack=villain_stack)
    offer = coach.SpotAction("hero", "all_in") if price is None else coach.SpotAction("hero", "bet", price)
    spot.actions.extend([offer, coach.SpotAction("villain", reply)])
    status, payload, _ = coach._replay(spot)
    assert status == "hand_complete"
    history = payload["result"]["history"]
    row = extract(history, "b")[0][-1]
    return history, row


def learn(history, n):
    p, old = EvidenceProfile("test:opponent"), OpponentModel("b")
    for i in range(n):
        assert p.update(str(i), history, "b")
        old.update(history)
    return p, old.snapshot()


def predict(profile, row, fallback):
    return hybrid_forecast(profile, row.situation, row.collectible, row.matched_pot, fallback)


@pytest.mark.parametrize("price", [None, 125, 625])
def test_supported_uses_v2_with_legal_probability_classes(price):
    hand, row = observed(price, "fold")
    p, _ = learn(hand, 20)

    def fail():
        pytest.fail("incumbent called despite supported evidence")

    mix, evidence = predict(p, row, fail)
    assert evidence == Evidence("supported", 20, 20)
    assert mix == forecast(p.v2, row.situation, True)
    assert tuple(mix) == row.situation.legal
    assert len(mix) == (2 if price is None else 4)
    assert mix["fold"] == pytest.approx((20 + 2 / len(mix)) / 22)
    assert sum(mix.values()) == pytest.approx(1)
    assert min(mix.values()) >= 0


@pytest.mark.parametrize("price", [None, 160, 640])
def test_unseen_closing_small_and_overbet_retain_exact_incumbent(price):
    known, _ = observed(125 if price != 640 else 625, "fold")
    _, unseen = observed(price, "call")
    p, snapshot = learn(known, 300)
    baseline = incumbent(snapshot, unseen.situation)
    mix, evidence = predict(p, unseen, lambda: baseline)
    assert evidence == Evidence("unsupported", 0, 0)
    assert mix is baseline
    if price is not None:
        assert p.v2.conditional[unseen.situation].observed == 300


@pytest.mark.parametrize("count, coverage", [(1, "sparse"), (19, "sparse"), (20, "supported")])
def test_sparse_and_mature_use_relevant_replies(count, coverage):
    small, _ = observed(125, "fold")
    shove, row = observed(None, "call")
    p, snapshot = learn(small, 300)
    for i in range(count):
        p.update(f"shove:{i}", shove, "b")
    baseline = incumbent(snapshot, row.situation)
    mix, evidence = predict(p, row, lambda: baseline)
    assert evidence == Evidence(coverage, count, count)
    assert (mix is baseline) == (coverage == "sparse")


def test_legacy_and_missing_replies_preserve_fallback():
    hand, row = observed(None, "fold")
    _, snapshot = learn(hand, 20)
    baseline = incumbent(snapshot, row.situation)
    assert predict(None, row, lambda: baseline)[0] is baseline
    p = EvidenceProfile("missing")
    events = list(hand.events)
    events[row.event_index] = replace(events[row.event_index], fallback_used=True, requested_action="invalid")
    missing = replace(hand, events=events)
    for i in range(20):
        assert p.update(str(i), missing, "b")
    mix, evidence = predict(p, row, lambda: baseline)
    assert evidence == Evidence("unsupported", 20, 0)
    assert mix is baseline


def test_position_depth_and_spr_are_part_of_support():
    hand, row = observed(125, "fold")
    p, _ = learn(hand, 20)
    for context in (replace(row.situation, position="button"),
                    replace(row.situation, depth_bucket=2),
                    replace(row.situation, spr_bucket=3),
                    replace(row.situation, aggression_depth=2),
                    replace(row.situation, legal=("fold", "call"))):
        baseline = dict.fromkeys(context.legal, 1 / len(context.legal))
        mix, evidence = hybrid_forecast(p, context, row.collectible, row.matched_pot, lambda: baseline)
        assert evidence.coverage == "unsupported"
        assert mix is baseline


def test_short_all_in_uses_collectible_price_and_never_reraises():
    hand, row = observed(None, "all_in", villain_stack=650)
    p, _ = learn(hand, 20)
    assert (row.offered, row.collectible, row.matched_pot) == (1250, 400, 500)
    refund, = [event for event in hand.events if event.event_type == "unmatched_excess_returned"]
    assert refund.returned_amount == 850
    mix, evidence = predict(p, row, lambda: None)
    assert evidence.coverage == "supported"
    assert mix == {"fold": 1 / 22, "call": 21 / 22}


def test_import_replay_and_hidden_cards_keep_evidence_identical():
    hand, row = observed(None, "call")
    alternate, _ = observed(None, "call", hidden=("Ah", "Ac"))
    profile = EvidenceProfile("identity")
    for i in range(20):
        assert profile.update(str(i), hand, "b")
        assert not profile.update(str(i), hand_history_from_dict(hand.as_dict()), "b")
        assert not profile.update(str(i), alternate, "b")
    assert profile.v2.hands_observed == 20
    assert predict(profile, row, lambda: None)[1] == Evidence("supported", 20, 20)
    conflicting, _ = observed(None, "fold")
    with pytest.raises(ValueError, match="conflicting"):
        profile.update("0", conflicting, "b")
    assert predict(profile, row, lambda: None)[1] == Evidence("supported", 20, 20)
