"""Compare continuity of a saved profile against matched development sessions."""

import argparse
import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from simulation.evaluation import bootstrap_interval


def rate(session, blind):
    hands = 2 * session["hands_per_seat"]
    return 100 * (session["net_seat_a"] + session["net_seat_b"]) / (hands * blind)


def analyze(learning, control_header, control):
    config = learning["header"]["configuration"]
    header = learning["header"]
    if config["seed_set"] != "development" or config != control_header["configuration"]:
        raise ValueError("both arms must use the same development configuration")
    if any(header[field] != control_header[field] for field in ("agent", "opponent")):
        raise ValueError("recorded matchups differ")
    cases = learning["sessions"]
    if len(cases) != config["pairs"] or len(control) != len(cases):
        raise ValueError("both arms must contain the full session schedule")
    if len(cases) < 2 or any(learning["initial_profile_hands"].values()):
        raise ValueError("the comparison requires multiple sessions and an initially empty saved profile")

    paired = []
    for case, baseline in zip(cases, control, strict=True):
        if case["seed"] != baseline["seed"] or not all(
            row["hands_per_seat"] == config["session_hands"] for row in (case, baseline)
        ):
            raise ValueError("recorded session deals differ")
        if not all(row["deal_verified"] for row in (case, baseline)):
            raise ValueError("a duplicate deal failed verification")
        paired.append((rate(case, config["big_blind"]), rate(baseline, config["big_blind"])))

    if cases[0] != {key: value for key, value in control[0].items() if key != "session"}:
        raise ValueError("first-session parity failed with both profiles initially empty")

    half = len(paired) // 2
    result = {
        "diagnostics": {
            arm: {
                field: sum(row[field] for row in sessions)
                for field in ("illegal_actions", "fallback_actions", "solver_fallback_actions")
            }
            for arm, sessions in (("carry", cases), ("reset", control))
        }
    }
    for group, rows in (("all", paired), ("early", paired[:half]), ("late", paired[half:])):
        carry, reset = zip(*rows, strict=True)
        effects = [saved - fresh for saved, fresh in rows]
        result[group] = {
            "pairs": len(rows),
            "carry_bb_per_100": mean(carry),
            "reset_bb_per_100": mean(reset),
            "carry_minus_reset_bb_per_100": mean(effects),
            "interval": bootstrap_interval(
                effects, resamples=config["bootstrap_resamples"], statistics_seed=config["statistics_seed"],
                confidence_level=config["confidence_level"],
            ),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("opponent", choices=("expert", "range_expert"))
    args = parser.parse_args()
    jobs = ROOT / "autopilot" / "overnight" / "jobs"
    saved = jobs / "profiles" / f"{args.opponent}.profile.json"
    profile = json.loads(saved.read_text(encoding="utf-8"))
    control = jobs / f"nov27-carry-control-{args.opponent}.jsonl"
    with control.open(encoding="utf-8") as source:
        header = json.loads(next(source))
        rows = [json.loads(line) for line in source if line.strip()]
    print(json.dumps(analyze(profile["runs"][f"nov27-{args.opponent}"], header, rows), indent=2))


if __name__ == "__main__":
    main()
