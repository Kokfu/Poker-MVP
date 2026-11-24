"""Phase 5G checks for exact opportunities, allocation and wager audit categories."""
from dataclasses import replace
from random import Random

import pytest

from research.holdem import phase_5e as prior, phase_5g as study
from research.holdem.opponent_profile_v2 import extract
from research.holdem.phase_5g_audit import slices
from research.holdem.phase_5g_summary import size
from research.holdem.profile_v2_hybrid import Evidence, EvidenceProfile, hybrid_forecast
from test_research_holdem_phase_5f import observed


@pytest.mark.parametrize(("price", "band", "closing"),
                         [(125, "small", False), (250, "half-pot band", False),
                          (500, "pot band", False), (625, "overbet", False), (1250, "overbet", True)])
def test_scheduled_wagers_match_engine_and_tree(price, band, closing):
    deal = Random(550).sample(prior.FULL_DECK, 9)
    history = study.replay(deal, price, "call")
    observations, unknown = extract(history, "b")
    preflop, live = [row for row in observations if row.offered]
    assert preflop.situation.street == "preflop" and preflop.collectible == 150
    assert unknown == 0
    assert len(observations) > 1
    assert live.situation.closing is closing
    assert (live.collectible, live.matched_pot) == (price, 500)
    assert size(live.collectible, live.matched_pot) == band
    tree = study.checked_tree(False)
    tree_contexts = [tree[4][node] for node in tree[5].values()]
    assert ((live.situation, price, 500) in tree_contexts) == (price != 625)
    if price == 625:
        short = study.replay(deal, price, "call", bounded_overbet=True)
        limited = prior.target(short, 1)
        assert limited.effective_stack == 1200 and limited.situation.legal == ("fold", "call", "shove")
        assert (limited.situation, price, 500) in tree_contexts


def test_missing_reply_and_retry_have_distinct_denominators():
    hand, row = observed(None, "all_in", villain_stack=650)
    events = list(hand.events)
    events[row.event_index] = replace(events[row.event_index], fallback_used=True, requested_action="invalid")
    missing = replace(hand, events=events)
    result = slices([("0", hand, "b"), ("0", hand, "b"), ("1", missing, "b")])
    assert (result["hands_logged"], result["accepted"], result["duplicate_ids"]) == (3, 2, 1)
    assert result["live_wagers"]["opportunities"] == 4
    assert result["live_wagers"]["observed"] == 3
    assert result["slices"]["short_all_in_call"]["responses"] == {"call": 1}
    river, = [entry for entry in result["exact"] if entry["context"]["street"] == "river"]
    assert river["exact_evidence"] == Evidence("sparse", 2, 1)._asdict()
    assert river["forecast_source"] == "incumbent"


def test_independent_supplement_activates_only_matching_menu():
    original, additional, *_ = study.DEVELOPMENT
    tree = study.checked_tree(False)
    targets = {tree[4][node][1]: tree[4][node] for node in tree[5].values()}
    found = {}
    for n, profile, _, allocation, _ in study.train(0, 0, 4, original + 4, additional + 4, 500):
        found[n] = profile.evidence(*targets[125])
        if n == 500:
            assert all(allocation["additional", price] == 40 for price in study.PRICES if price != 625)
            assert allocation["additional", 625] == allocation["additional_bounded", 625] == 20
            assert profile.evidence(*targets[625]) == Evidence("supported", 20, 20)
            assert profile.v2.hands_observed == 500
            assert sum(profile._opportunities.values()) == sum(profile._replies.values()) == 1000
            context, price, pot = targets[125]
            base = {"fold": .2, "call": .5, "raise": .2, "shove": .1}
            forecast, evidence = hybrid_forecast(profile, context, price + 1, pot, lambda: base)
            assert evidence == Evidence("unsupported", 0, 0)
            assert forecast is base
    assert found[300] == Evidence("unsupported", 0, 0)
    assert found[500] == Evidence("supported", 40, 40)
