"""Run the frozen Phase 4J panel from backend with the local Phase 4I fixtures.

python -m research.holdem.phase_4j OUTPUT.json
"""
import argparse
import json
from math import fsum, isclose
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import numpy as np
from treys import Evaluator

from coach.service import Spot, SpotAction, spot_to_dict
from coach.store import HandStore
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action
from solver.combos import combo_index
from test_coach_learning import FACING_BET
from test_solver_phase_4i import decision, seed_store, split_label


SIZES = (3, 12, 30, 100, 500)
PRIORS = (10, 30, 100)
CASES = (
    ("cal_high_card_facing", "calibration", "Jc 9d", "Qh 7s 2d 4c 8h", 250),
    ("cal_top_pair_checked", "calibration", "Ah Qd", "Qs 7h 2d 4c 8h", 0),
    ("set_facing", "holdout", "8c 8d", "Kh 8s 2d 4c Jh", 500),
    ("pair_facing", "holdout", "7c 6c", "Kh 7s 2d 4c Jh", 500),
    ("ace_high_checked", "holdout", "Ac 5c", "Qh 7s 2d 4c 8h", 0),
    ("top_pair_checked", "holdout", "Qc Tc", "Qh 7s 2d 4c 8h", 0),
)
REFERENCES = {
    "loose_aggressive": ((.70, .75, .95), (.30, .75, 1.00), (.15, .55, .95)),
    "selective": ((.05, .25, .90), (.05, .45, .98), (.01, .25, .90)),
}
HARM_TOLERANCE_BB = 1e-6
_RANKER = Evaluator()


def strength_class(rank):
    return 9 - max(7, _RANKER.get_rank_class(rank))


def river_spot(hero, board, bet):
    actions = [SpotAction("hero", "raise", 250), SpotAction("villain", "call")]
    actions += [SpotAction("villain", "check"), SpotAction("hero", "check")] * 2
    actions.append(SpotAction("villain", "bet", bet) if bet else SpotAction("villain", "check"))
    return Spot(hero_cards=hero.split(), board=board.split(), hero_stack=1500, villain_stack=1500, actions=actions)


def supported_mix(row):
    assert row["source"] == "postflop_solve", row
    mix = row["mix"]
    total = fsum(mix.values())
    assert isclose(total, 1, abs_tol=1e-6, rel_tol=0)
    row["mix"] = {label: weight / total for label, weight in sorted(mix.items())}
    return row["mix"]


def assess_reference(spot, bet, labels, inferred_ranges, frequencies):
    opening, small, large = frequencies

    def range_weight(_, rank):
        chance = opening[strength_class(rank)]
        return chance if bet else 1 - chance

    def response(_, rank, cost, pot):
        return (small if 2 * cost <= pot else large)[strength_class(rank)]

    exact = ExactRiverEV(tuple(spot.hero_cards), tuple(spot.board), range_weight)
    state = RiverState(500 + bet, 0, bet, 1250, 1250 - bet, bet or 100, checked_to=not bet)
    action_ev = {label: exact.action_ev(state, Action(*split_label(label)), response) / spot.big_blind
                 for label in sorted(labels)}
    indices = np.array([combo_index(hand.combo) for hand in exact.holdings])
    truth = np.array([hand.weight for hand in exact.holdings])
    scores = np.array([(hand.result + 1) / 2 for hand in exact.holdings])
    diagnostics = {}
    for arm, estimates in inferred_ranges.items():
        diagnostics[arm] = {}
        for hands, estimate in estimates.items():
            weights = estimate[indices]
            assert isclose(weights.sum(), 1, abs_tol=1e-12, rel_tol=0)
            equity = float(weights @ scores)
            diagnostics[arm][hands] = {
                "posterior_tv": float(np.abs(weights - truth).sum() / 2),
                "estimated_equity": equity,
                "absolute_equity_error": abs(equity - exact.equity),
            }
    return {"action_ev_bb": action_ev, "reference_equity": exact.equity, "range_diagnostics": diagnostics}


def weighted_ev(mix, action_ev):
    return fsum(probability * action_ev[label] for label, probability in mix.items())


def score(mix, action_ev, off_ev):
    ev = weighted_ev(mix, action_ev)
    return {"ev_bb": ev, "delta_vs_off_bb": ev - off_ev, "regret_bb": max(action_ev.values()) - ev}


def mix_policies(off, on, adaptive_share):
    return {label: (1 - adaptive_share) * off.get(label, 0) + adaptive_share * on.get(label, 0)
            for label in sorted(off.keys() | on.keys())}


def action_distance(left, right):
    labels = sorted(left.keys() | right.keys())
    return fsum(abs(left.get(label, 0) - right.get(label, 0)) for label in labels) / 2


def collect(store, split):
    rows = []
    for name, partition, hero, board, bet in CASES:
        if partition != split:
            continue
        spot = river_spot(hero, board, bet)
        mixes, ranges = {}, {arm: {} for arm in ("off", "on")}
        labels = set()
        for hands in SIZES:
            entry = mixes[hands] = {}
            for arm, control in (("off", "off"), ("on", "corrected")):
                row, estimated_range = decision(spot, store, f"aggressive-{hands}", control)
                assert (row["pot"], row["to_call"]) == (500 + bet, bet)
                assert row["profile"]["hands_observed"] == hands
                labels.update(supported_mix(row))
                entry[arm] = row
                ranges[arm][hands] = estimated_range
            assert entry["off"]["mix"] == mixes[SIZES[0]]["off"]["mix"]
            np.testing.assert_array_equal(ranges["off"][hands], ranges["off"][SIZES[0]])
        references = {key: assess_reference(spot, bet, labels, ranges, model) for key, model in REFERENCES.items()}
        rows.append({"case": name, "split": split, "spot": spot_to_dict(spot), "inputs": mixes,
                     "references": references})
        print(f"Collected {name}", flush=True)
    return rows


def calibrate(rows):
    calibration = {}
    for prior in PRIORS:
        calibration[prior] = mean(
            weighted_ev(mix_policies(entry["off"]["mix"], entry["on"]["mix"], hands / (hands + prior)),
                        reference["action_ev_bb"])
            for row in rows
            for reference in row["references"].values()
            for hands, entry in row["inputs"].items()
        )
    prior = max(PRIORS, key=lambda k: (calibration[k], k))
    return calibration, prior


def compare(rows, prior):
    for row in rows:
        for hands, entry in row["inputs"].items():
            off, on = entry["off"]["mix"], entry["on"]["mix"]
            candidate = mix_policies(off, on, hands / (hands + prior))
            entry["candidate_mix"] = candidate
            entry["action_tv_on"] = action_distance(on, off)
            entry["action_tv_candidate"] = action_distance(candidate, off)
            for reference in row["references"].values():
                action_ev = reference["action_ev_bb"]
                off_ev = weighted_ev(off, action_ev)
                reference.setdefault("scores", {})[hands] = {
                    arm: score(mix, action_ev, off_ev)
                    for arm, mix in (("off", off), ("on", on), ("candidate", candidate))
                }


def summary(rows, split, reference=None, sizes=SIZES):
    scores = [score for row in rows if row["split"] == split
              for name, model in row["references"].items() if reference in (None, name)
              for hands, score in model["scores"].items() if hands in sizes]
    result = {}
    for arm in ("off", "on", "candidate"):
        values = [row[arm] for row in scores]
        harm = [row["delta_vs_off_bb"] for row in values if row["delta_vs_off_bb"] < -HARM_TOLERANCE_BB]
        result[arm] = {
            "rows": len(values), "mean_ev_bb": mean(row["ev_bb"] for row in values),
            "mean_delta_vs_off_bb": mean(row["delta_vs_off_bb"] for row in values),
            "mean_regret_bb": mean(row["regret_bb"] for row in values),
            "harm_count": len(harm), "harm_cost_bb": -fsum(harm),
        }
    return result


def experiment(store):
    seed_store(store, {"aggressive": max(SIZES)}, SIZES)
    rows = collect(store, "calibration")
    calibration, prior = calibrate(rows)
    rows.extend(collect(store, "holdout"))
    compare(rows, prior)
    sparse = {arm: decision(FACING_BET, store, "aggressive-12", arm)[0]
              for arm in ("off", "corrected", "preflop-only", "postflop-only")}
    assert all(row["source"] == "postflop_solve" for row in sparse.values())
    assert round(sparse["corrected"]["mix"]["call"], 4) == .9941
    return {
        "cases": rows, "calibration_prior_mean_ev_bb": calibration, "chosen_prior": prior,
        "original_flop_12": sparse,
        "calibration": summary(rows, "calibration"), "holdout": summary(rows, "holdout"),
        "holdout_by_reference": {ref: summary(rows, "holdout", ref) for ref in REFERENCES},
        "holdout_by_size": {n: summary(rows, "holdout", sizes=(n,)) for n in SIZES},
        "holdout_sparse": summary(rows, "holdout", sizes=(3, 12, 30)),
        "holdout_mature": summary(rows, "holdout", sizes=(100, 500)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    with TemporaryDirectory() as directory:
        result = experiment(HandStore(Path(directory) / "coach.sqlite"))
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    main()
