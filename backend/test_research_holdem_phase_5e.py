import json
from dataclasses import replace

import pytest

from coach import service as coach
from research.holdem.opponent_profile_v2 import ProfileV2, extract, forecast, predict
from research.holdem.phase_4k import river_spot
from simulation.opponent_model import OpponentModel


def history(offer, reply, hero_stack=1500, villain_stack=2500):
    spot = replace(river_spot("9h 9d", "Kc 9s 3d 5h Js", 0),
                   villain_cards=["As", "Ad"], hero_stack=hero_stack, villain_stack=villain_stack)
    spot.actions.extend([coach.SpotAction("hero", *offer), coach.SpotAction("villain", reply)])
    status, payload, _ = coach._replay(spot)
    assert status == "hand_complete"
    return payload["result"]["history"]


@pytest.mark.parametrize("sizes, offer, reply, expected", [
    ((1500, 2500), ("bet", 125), "fold", (125, 125, 500, 1250, False, "fold")),
    ((1500, 2500), ("all_in",), "call", (1250, 1250, 500, 1250, True, "call")),
    ((1500, 650), ("all_in",), "all_in", (1250, 400, 500, 400, True, "call")),
    ((650, 1500), ("all_in",), "fold", (400, 400, 500, 400, True, "fold")),
])
def test_public_geometry(sizes, offer, reply, expected):
    hand = history(offer, reply, *sizes)
    row = extract(hand, "b")[0][-1]
    assert (row.offered, row.collectible, row.matched_pot, row.effective_stack,
            row.situation.closing, row.response) == expected
    assert row.wager_to_pot == expected[1] / 500
    assert row.stack_to_pot == expected[3] / 500
    assert row.situation.position == "big_blind"
    if row.situation.closing:
        assert row.situation.legal == ("fold", "call")
    if expected[0] > expected[1] and reply == "all_in":
        refund, = [event for event in hand.events if event.event_type == "unmatched_excess_returned"]
        assert refund.returned_amount == 850


def test_replay_identity_and_atomic_invalid_hand():
    profile = ProfileV2("local-store:opponent")
    hand = history(("bet", 125), "fold")
    assert profile.update("source:1", hand, "b")
    assert not profile.update("source:1", hand, "b")
    with pytest.raises(ValueError, match="conflicting"):
        profile.update("source:1", history(("bet", 125), "call"), "b")
    for broken in (replace(hand, settlement_complete=False),
                   replace(hand, events=hand.events[:3] + hand.events[2:]),
                   replace(hand, events=hand.events[:-1])):
        with pytest.raises(ValueError):
            profile.update("source:2", broken, "b")
    assert profile.hands_observed == 1
    assert sum(cell.opportunities for cell in profile.conditional.values()) == 5
    assert profile.update("source:2", hand, "a")
    assert any(s.position == "button" for s in profile.conditional)


def test_missing_and_invalid_response_accounting():
    hand = history(("bet", 125), "fold")
    index = extract(hand, "b")[0][-1].event_index
    events = list(hand.events)
    events[index] = replace(events[index], fallback_used=True, requested_action="invalid")
    profile = ProfileV2("fixture")
    profile.update("1", replace(hand, events=events), "b")
    row = extract(hand, "b")[0][-1]
    cell = profile.conditional[row.situation]
    assert (cell.opportunities, cell.observed, cell.responses["fold"]) == (1, 0, 0)
    assert forecast(profile, row.situation, True) == dict.fromkeys(row.situation.legal, .25)
    events[index] = replace(hand.events[index], legal_actions=None)
    profile.update("2", replace(hand, events=events), "b")
    assert profile.unknown == 1
    assert cell.opportunities == 1
    events[index] = replace(hand.events[index], applied_action="check")
    profile.update("3", replace(hand, events=events), "b")
    assert (cell.opportunities, cell.observed) == (2, 0)


def test_legacy_snapshot_and_history_are_read_only():
    hand = history(("all_in",), "call")
    encoded = json.dumps(hand.as_dict(), sort_keys=True)
    old = OpponentModel("b")
    old.update(hand)
    prior = old.snapshot().as_dict()
    profile = ProfileV2("b")
    profile.update("1", hand, "b")
    assert json.dumps(hand.as_dict(), sort_keys=True) == encoded
    assert old.snapshot().as_dict() == prior
    assert "version" not in prior and "sized_statistics" not in prior
    assert predict(("fold", "call"), {"fold": 8, "call": 2}, {"call": 2}) == {
        "fold": .375, "call": .625}


def test_reraise_and_limp_have_distinct_opportunities():
    spot = replace(river_spot("9h 9d", "Kc 9s 3d 5h Js", 0),
                   actions=[coach.SpotAction(*action) for action in [
                       ("hero", "call"), ("villain", "raise", 250), ("hero", "raise", 500),
                       ("villain", "all_in"), ("hero", "fold")]])
    status, payload, _ = coach._replay(spot)
    assert status == "hand_complete"
    rows, unknown = extract(payload["result"]["history"], "b")
    assert not unknown
    assert [(r.situation.previous, r.situation.aggression_depth, r.offered, r.response)
            for r in rows] == [("call", 0, 0, "raise"), ("raise", 2, 250, "shove")]
