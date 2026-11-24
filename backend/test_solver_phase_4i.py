"""Deterministic live Coach controls and the offline Phase 4I replay.

From backend: python -m test_solver_phase_4i OUTPUT.json
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import numpy as np
import pytest

from coach import explain
from coach.service import Spot, SpotAction, advise, spot_to_dict
from coach.store import HandStore
from simulation.opponent_model import OpponentModel, OpponentStats
from solver import bot as solver
from solver.combos import COMBOS, card_mask
from solver.exploit import node_lock
from solver.preflop import load_charts
from test_coach_learning import FACING_BET, simulated_spots


SEED = 917
HISTORIES = {"tight": 150, "equity": 120, "aggressive": 120}
AGGRESSIVE_PREFIXES = (4, 12, 40)
CURRENT_TREE_LOCKS = solver.tree_locks


def seed_store(store, counts, prefixes=()):
    for opponent, count in counts.items():
        for index, spot in enumerate(simulated_spots(opponent, count)):
            entry = spot_to_dict(spot)
            store.add(opponent, entry)
            if opponent == "aggressive":
                for prefix in prefixes:
                    if index < prefix:
                        store.add(f"aggressive-{prefix}", entry)


def legacy_tree_locks(tree, opponent, street, profile, correlation=None, *args, **kwargs):
    """Phase 4H control. Only the unopened SB strength coefficient differed."""
    locks = CURRENT_TREE_LOCKS(tree, opponent, street, profile, correlation, *args, **kwargs)
    if street == "preflop" and opponent == 0 and tree.root in locks:
        weight, groups, _ = locks[tree.root]
        correlation = correlation or {}
        mean = (correlation.get("aggressive", 1.0) + correlation.get("call", 1.0)) / 2
        locks[tree.root] = weight, groups, round(mean, 2)
    return locks


def concrete_label(action):
    return action.type if action.amount is None else f"{action.type}_{action.amount}"


def check_legal(label, state):
    kind, target = split_label(label)
    assert kind in state["legal_actions"]
    if target is not None:
        assert state["minimum_target"] <= target <= state["maximum_target"]


def split_label(label):
    kind, _, target = label.rpartition("_")
    return (kind, int(target)) if target.isdecimal() else (label, None)


def decision(spot, store, opponent, arm):
    """Record the full-precision policy and posterior at the live decision boundary."""
    captured = {}
    lock_counts = Counter()

    def locks(tree, player, street, *args, **kwargs):
        if (arm == "preflop-only" and street != "preflop") or (arm == "postflop-only" and street == "preflop"):
            return {}
        factory = legacy_tree_locks if arm == "control" else CURRENT_TREE_LOCKS
        result = factory(tree, player, street, *args, **kwargs)
        lock_counts[street] += len(result)
        if street == "preflop" and player == 0 and tree.root in result:
            captured["root_lock"] = result[tree.root][2]
        return result

    original_report = solver.SolverBot._range_report
    original_sample = solver.SolverBot._sample
    original_concretize = explain.concretize

    def report(bot, board, hero_combo, villain):
        weights = np.where(card_mask(tuple(COMBOS[hero_combo]) + board), 0.0, villain)
        if weights.sum() > 0:
            captured["range"] = weights / weights.sum()
        return original_report(bot, board, hero_combo, villain)

    def sample(bot, ds, probabilities):
        captured["state"] = ds
        captured["probabilities"] = probabilities.copy()
        return original_sample(bot, ds, probabilities)

    def concretize(explanation):
        captured["labels"] = explanation.get("concrete_labels", explanation.get("labels"))
        return original_concretize(explanation)

    solver._PREFLOP_CACHE.clear()
    with patch.object(solver, "tree_locks", locks), patch.object(solver.SolverBot, "_range_report", report), patch.object(
        solver.SolverBot, "_sample", sample
    ), patch.object(explain, "concretize", concretize):
        start = perf_counter()
        result = advise(spot, opponent=opponent, exploit=arm != "off", store=store, seed=SEED)
        wall = perf_counter() - start

    assert result["status"] == "hero_to_act"
    state, explanation, advice = result["state"], result["explanation"], result["advice"]
    label = advice["action"] if advice.get("amount") is None else f"{advice['action']}_{advice['amount']}"
    check_legal(label, state)
    mix = defaultdict(float)
    if explanation["source"] != "fallback":
        probabilities = captured["probabilities"]
        assert np.isfinite(probabilities).all() and (probabilities >= 0).all()
        assert probabilities.sum() == pytest.approx(1, abs=1e-6, rel=0)
        for raw, probability in zip(captured["labels"], probabilities, strict=True):
            kind, target = split_label(raw)
            action = solver.SolverBot._legalize(captured["state"], kind, target)
            concrete = concrete_label(action)
            check_legal(concrete, state)
            mix[concrete] += float(probability)
    row = {
        "recommendation": label, "mix": dict(mix), "modal": max(mix, key=mix.get) if mix else None,
        "range_equity": explanation.get("hero_equity_vs_range"),
        "effective_combos": explanation.get("villain_effective_combos"),
        "action_ev": dict(zip(explanation.get("labels", ()), explanation.get("action_ev", ()))),
        "source": explanation["source"], "reason": result["explain"]["reason"], "lock_counts": dict(lock_counts),
        "root_lock": captured.get("root_lock"), "profile": result["opponent_profile"],
        "showdown": explanation.get("exploit"), "adjusted": result["adjusted"],
        "pot_odds": state["to_call"] / (state["pot"] + state["to_call"]),
        "pot": state["pot"], "to_call": state["to_call"], "wall_seconds": wall,
    }
    return row, captured.get("range")


def river_shove(hero_cards, board, stack):
    return Spot(
        hero_cards=hero_cards, board=board, hero_stack=stack, villain_stack=stack,
        actions=[
            SpotAction("hero", "raise", 250), SpotAction("villain", "call"),
            SpotAction("villain", "check"), SpotAction("hero", "check"),
            SpotAction("villain", "check"), SpotAction("hero", "check"), SpotAction("villain", "all_in"),
        ],
    )


REFERENCES = {
    "river_nuts": (river_shove(["As", "Ks"], ["Qs", "Js", "Ts", "2d", "3c"], 500), 1.0),
    "river_board_royal": (river_shove(["2d", "3c"], ["As", "Ks", "Qs", "Js", "Ts"], 1500), 0.5),
}


def test_sparse_profile_lock_weight_matches_observation_count():
    node = load_charts().trees[30].nodes[0]
    for n, expected in ((4, 0), (5, 0.3), (19, 0.3), (20, 0.55), (49, 0.55), (50, 0.75)):
        model = OpponentModel("b", hands_observed=n)
        model.stats["preflop_raise"] = OpponentStats(n, n)
        model.stats["limp"] = OpponentStats(n, 0)
        result = node_lock(node, "preflop", model.snapshot())
        if not expected:
            assert result is None
        else:
            assert result is not None and result[0] == expected


def check_reference(spot, equity, store, opponent, arm):
    row, _ = decision(spot, store, opponent, arm)
    assert row["source"] == "postflop_solve"
    assert row["range_equity"] == equity
    # Preflop contributions are 250 each. Turn and flop checked through.
    wager = spot.hero_stack - 250
    assert row["pot"] == 500 + wager and row["to_call"] == wager
    assert row["recommendation"] == "all_in"
    assert row["action_ev"] == {"fold": 0.0, "call": equity * (500 + 2 * wager) - wager}
    return row


@pytest.mark.parametrize("name", REFERENCES)
def test_river_shove_ev_matches_terminal_chip_payoffs(name, tmp_path):
    spot, equity = REFERENCES[name]
    check_reference(spot, equity, HandStore(tmp_path / "coach.sqlite"), None, "off")


def total_variation(left, right):
    return sum(abs(left.get(label, 0) - right.get(label, 0)) for label in left.keys() | right.keys()) / 2


def compare_rows(rows, ranges, left, right):
    first, second = rows[left], rows[right]
    return {
        "range_tv": float(np.abs(ranges[left] - ranges[right]).sum() / 2),
        "equity_delta": second["range_equity"] - first["range_equity"],
        "action_tv": total_variation(first["mix"], second["mix"]),
        "modal_changed": first["modal"] != second["modal"],
        "recommendation_changed": first["recommendation"] != second["recommendation"],
        "action_ev_delta": {label: second["action_ev"][label] - value for label, value in first["action_ev"].items()
                            if label in second["action_ev"]},
    }


def with_depth(spot, depth):
    return replace(spot, hero_stack=100 * depth, villain_stack=100 * depth)


def test_corrected_tight_open_changes_range_with_same_concrete_call(tmp_path):
    store = HandStore(tmp_path / "coach.sqlite")
    seed_store(store, {"tight": HISTORIES["tight"]})
    spot = with_depth(replace(FACING_BET, board=[], actions=FACING_BET.actions[:1]), 30)
    control, before = decision(spot, store, "tight", "control")
    corrected, after = decision(spot, store, "tight", "corrected")
    assert control["source"] == corrected["source"] == "preflop_exploit"
    assert np.abs(before - after).sum() / 2 > 0.30
    assert corrected["effective_combos"] < control["effective_combos"]
    assert corrected["range_equity"] < control["range_equity"]
    assert total_variation(control["mix"], corrected["mix"]) < 0.01
    assert corrected["recommendation"] == control["recommendation"] == "call"


def test_passive_big_blind_read_changes_button_policy_without_equity_change(tmp_path):
    store = HandStore(tmp_path / "coach.sqlite")
    seed_store(store, {"equity": HISTORIES["equity"]})
    spot = Spot(hero_cards=["7c", "2d"])
    off, before = decision(spot, store, "equity", "off")
    corrected, after = decision(spot, store, "equity", "corrected")
    np.testing.assert_array_equal(before, after)
    assert off["range_equity"] == corrected["range_equity"]
    assert off["mix"]["fold"] > 0.9
    assert corrected["mix"]["call"] > 0.9
    assert off["recommendation"] == "fold"
    assert corrected["recommendation"] == "call"


def targeted(store):
    seed_store(store, HISTORIES, AGGRESSIVE_PREFIXES)
    bb_open = replace(FACING_BET, board=[], actions=FACING_BET.actions[:1])
    button = Spot(hero_cards=["7c", "2d"])
    flop_large = replace(FACING_BET, actions=[*FACING_BET.actions[:-1], SpotAction("villain", "bet", 500)])
    turn = replace(FACING_BET, board=[*FACING_BET.board, "Js"], actions=[
        *FACING_BET.actions[:3], SpotAction("villain", "check"), SpotAction("hero", "check"),
        SpotAction("villain", "bet", 250),
    ])
    cases = [
        *((f"tight_bb_{depth}", "tight", with_depth(bb_open, depth)) for depth in (15, 30, 60, 100, 200)),
        ("tight_bb_30_ace", "tight", replace(with_depth(bb_open, 30), hero_cards=["As", "8d"])),
        ("loose_passive_button", "equity", button),
        ("loose_aggressive_button", "aggressive", button),
        ("tight_flop", "tight", FACING_BET),
        ("loose_passive_flop", "equity", FACING_BET),
        ("loose_aggressive_flop", "aggressive", FACING_BET),
        ("loose_aggressive_flop_large", "aggressive", flop_large),
        ("loose_aggressive_turn", "aggressive", turn),
        *((f"aggressive_prefix_{n}", f"aggressive-{n}", FACING_BET) for n in AGGRESSIVE_PREFIXES),
    ]
    results = {}
    for name, opponent, spot in cases:
        arms = ["off", "control", "corrected"]
        if name == "loose_aggressive_flop":
            arms.extend(("preflop-only", "postflop-only"))
        rows, ranges = {}, {}
        for arm in arms:
            rows[arm], ranges[arm] = decision(spot, store, opponent, arm)
            assert rows[arm]["source"] != "fallback", (name, arm, rows[arm]["reason"])
        results[name] = {
            "rows": rows, "opponent": opponent, "spot": spot_to_dict(spot),
            "correction": compare_rows(rows, ranges, "control", "corrected"),
            "adaptation": compare_rows(rows, ranges, "off", "corrected"),
        }
        if len(arms) > 3:
            results[name]["mediation"] = {arm: compare_rows(rows, ranges, "off", arm) for arm in arms[3:]}
    reference_rows = {
        name: {arm: check_reference(spot, equity, store, "aggressive", arm) for arm in ("off", "control", "corrected")}
        for name, (spot, equity) in REFERENCES.items()
    }
    material = [entry["correction"] for entry in results.values() if entry["correction"]["action_tv"] >= 0.05]
    trigger = len(material) >= 2 or any(delta["modal_changed"] for delta in material)
    return {"cases": results, "terminal_references": reference_rows, "run_paired": trigger}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    with TemporaryDirectory() as directory:
        store = HandStore(Path(directory) / "coach.sqlite")
        report = targeted(store)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
