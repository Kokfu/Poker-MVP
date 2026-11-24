from math import isclose

import numpy as np
import pytest

from coach.service import SpotAction, _replay
from research.holdem.phase_4k import STYLES, label, to_action
from research.holdem.phase_4l import Case, exact_values, fixed_value_mix, legal_optimum, score
from research.holdem.river_ev import ExactRiverEV, RiverState


def test_fixed_action_conversion_is_deterministic_and_preserves_ties():
    values = np.array([-2.0, 4.0, 4.0, 1.0])
    mix = fixed_value_mix(values, 80)
    assert np.array_equal(mix, fixed_value_mix(values, 80))
    assert mix.sum() == pytest.approx(1)
    assert mix[1] == mix[2]
    assert mix[0] + mix[3] < 1e-4


@pytest.mark.parametrize("kind,target", [("bet", 500), ("bet", 501), ("all_in", None)])
def test_exact_action_receipts_match_engine_on_both_sides_of_price_boundary(kind, target):
    case = Case("top_pair", "Kd Td", "Kh 7d 4s Qc 3h", 0)
    spot = case.spot(15)
    spot.villain_cards = ["Js", "9s"]
    exact = ExactRiverEV(tuple(spot.hero_cards), tuple(spot.board),
                        lambda cards, _: set(cards) == set(spot.villain_cards))
    state = RiverState(500, 0, 0, 1250, 1250, 100, checked_to=True)
    reference = STYLES["loose_aggressive"]
    action = SpotAction("hero", kind, target)
    results = {}
    for reply in ("fold", "call"):
        spot.actions += [action, SpotAction("villain", reply if kind != "all_in" or reply == "fold" else "all_in")]
        status, payload, _ = _replay(spot)
        spot.actions = spot.actions[:-2]
        assert status == "hand_complete"
        result = payload["result"]
        assert result["illegal_actions"] == 0
        assert sum(result["stacks"].values()) == 3000
        results[reply] = result["stacks"]["a"] - 1250
    # Js9s is high card. Facing 500, the pot is 1000, so the small-price rate applies.
    call = .28 if target == 500 else .12
    key = kind if target is None else f"{kind}_{target}"
    assert exact.action_ev(state, to_action(key), reference.call_probability) == pytest.approx(
        (1 - call) * results["fold"] + call * results["call"]
    )


def test_size_optimum_matches_exhaustive_integer_menu():
    from types import SimpleNamespace

    style = STYLES["tight_passive"]
    ds = SimpleNamespace(legal_actions=("check", "bet", "all_in"),
                         minimum_legal_target=100, maximum_legal_target=180)
    state = RiverState(150, 0, 0, 180, 180, 100, checked_to=True)
    exact = ExactRiverEV(("Kd", "Td"), ("Kh", "7d", "4s", "Qc", "3h"), lambda *_: 1)
    legal = ["check", "all_in", *(label(to_action(f"bet_{t}")) for t in range(100, 181))]
    ev = exact_values(exact, state, legal, style.call_probability)
    best, optimum = legal_optimum(exact, state, ds, ds.legal_actions, style.call_probability, ["check", "all_in"])
    assert ev[best] == optimum == max(ev.values())


def test_oracles_observe_the_same_reference_and_live_ev_matches_independent_receipts():
    case = Case("top_pair", "Kd Td", "Kh 7d 4s Qc 3h", 0)
    row = score(case, 15, "loose_aggressive", profile=None)
    assert row["live_payoff_max_error_chips"] < .002
    assert len(row["holdings"]["combos"]) == 990
    for combo in row["holdings"]["combos"]:
        assert not set(combo).intersection((*row["hero"], *row["board"]))
    for weights in (row["holdings"]["estimated"], row["holdings"]["true"]):
        assert isclose(sum(weights), 1.0, abs_tol=1e-12)
    assert row["arms"]["D"]["modeled_ev_bb"] == row["true_evs_bb"]
    assert row["arms"]["D"]["regret_bb"] < .001
    for arm in row["arms"].values():
        ev = sum(mass * row["true_evs_bb"][key] for key, mass in arm["mix"].items())
        assert arm["ev_bb"] == pytest.approx(ev)
        assert sum(arm["mix"].values()) == pytest.approx(1)
        for response in arm["responses"].values():
            if response:
                assert sum(response.values()) == pytest.approx(1)
    assert row["arms"]["B"]["modeled_ev_bb"] != row["arms"]["A"]["modeled_ev_bb"]
    assert row["arms"]["C"]["modeled_ev_bb"] != row["arms"]["D"]["modeled_ev_bb"]
