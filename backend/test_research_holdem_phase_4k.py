"""Regression checks for the matched-profile research boundaries."""
from copy import deepcopy

import pytest

from coach.service import Spot, SpotAction, advise, profile_for, spot_to_dict
from coach.store import HandStore
from research.holdem import phase_4k as study
from simulation.engine import HandEngine
from simulation.evaluation import _derived_seed
from solver.bot import AdaptiveSolverBot


def test_frozen_history_path_matches_logged_coach(tmp_path):
    name = "loose_passive"
    profile = study.train(name, 0, (3, 12))[12]
    store = HandStore(tmp_path / "coach.sqlite")
    for i in range(12):
        seed = 41_100_000 + i
        hero = study.AggressiveBot(_derived_seed(seed, "training-hero"))
        villain = study.make_opponent(name, _derived_seed(seed, "training-villain"))
        button = ("a", "b")[i % 2]
        engine = HandEngine(hero, villain, stack=study.STACK, seed=seed, button=button)
        result = engine.play()
        actions = [SpotAction("hero" if e.actor == "a" else "villain", e.applied_action,
                              e.target_total if e.applied_action in ("bet", "raise") else None)
                   for e in result["history"].events if e.event_type == "action_taken"]
        spot = Spot(engine.holes["a"], result["state"].community_cards,
                    "button" if button == "a" else "big_blind",
                    hero_stack=study.STACK, villain_stack=study.STACK, actions=actions,
                    villain_cards=engine.holes["b"] if result["showdown"] else None)
        store.add(name, spot_to_dict(spot))
    live_observer = AdaptiveSolverBot()
    assert profile_for(store, name, live_observer).snapshot() == profile.snapshot
    assert live_observer.showdown_model == profile.showdown

    spot = study.river_spot(*study.CASES[2][1:])
    frozen, _ = study.river_policy(spot, profile)
    live = advise(spot, name, store=store, seed=917)
    assert live["adjusted"] and frozen["locks"] > 0
    assert frozen["advice"] == live["advice"]
    probabilities = dict(zip(live["explanation"]["labels"], live["explanation"]["probabilities"], strict=True))
    assert frozen["mix"] == pytest.approx(probabilities, abs=5e-5, rel=0)


def test_synthetic_posterior_tracks_entire_path_and_call_size():
    spot = study.river_spot(*study.CASES[0][1:])
    style = study.STYLES["tight_aggressive"]
    exact, state = study.river_reference(spot, 500, style)
    hands = {frozenset(h.combo): h for h in exact.holdings}
    strong = hands[frozenset(("As", "Ac"))]
    weak = hands[frozenset(("As", "8c"))]
    # The strong hand has one pair on each street, the weak hand has high card.
    strong_likelihood = .85 * .35 * .35 * .35 * .65
    weak_likelihood = .09 * .35 * .60 * .60 * .40
    assert strong.weight / weak.weight == pytest.approx(strong_likelihood / weak_likelihood)
    assert style.call_probability(weak.combo, weak.rank, 400, 800) == .28
    assert style.call_probability(weak.combo, weak.rank, 401, 800) == .12
    assert len(exact.holdings) == 990 and state.pot == 1000


def test_gameplay_duplicate_is_deterministic_and_uses_frozen_profiles():
    name = "tight_passive"
    profile = study.train(name, 2, (30,))[30]
    before = deepcopy(profile)
    for seat in ("a", "b"):
        for enabled in (False, True):
            first, second = (study.play_arm(name, profile, 42_000_000, seat, enabled) for _ in range(2))
            for row in (first, second):
                row.pop("seconds")
                assert row["illegal_actions"] == row["solver_fallbacks"] == 0
            assert first == second
    assert profile == before


def test_paired_interval_uses_whole_profile_blocks():
    def result(net):
        return dict(net=net, decisions=1, solves=0, illegal_actions=0, solver_fallbacks=0, seconds=0)

    def block(gain):
        return {"opponent": "tight_passive", "hands": [
            {"off": result(0), "matched": result(value)}
            for value in (gain + 50, gain - 50, gain + 50, gain - 50)
        ]}

    summary = study.summarize_gameplay([block(-1), block(3)])["overall"]
    assert summary["hands_per_arm"] == 8 and summary["blocks"] == 2
    assert summary["delta_bb100"] == 1
    assert summary["paired_95"] == {"lower": -1, "upper": 3, "confidence_level": .95}
