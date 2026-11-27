"""Measure the flagged public-action range path on two and three opponents."""

import argparse
from collections import defaultdict
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))


def requests():
    from poker_analyzer import FULL_DECK

    rng = Random(20261127)
    for opponents in (2, 3):
        for street, board_length in (("preflop", 0), ("flop", 3), ("turn", 4), ("river", 5)):
            for index in range(8):
                cards = rng.sample(FULL_DECK, 2 + board_length)
                actions = [
                    {"seat": seat, "street": "preflop", "action": ("limp", "call", "raise")[(seat + index) % 3]}
                    for seat in range(1, opponents + 1)
                ]
                for prior, length in (("flop", 3), ("turn", 4), ("river", 5)):
                    if length <= board_length:
                        actions.extend({
                            "seat": seat, "street": prior,
                            "action": ("bet", "call", "check")[(seat + index + length) % 3],
                            "pot_fraction": (0.35, 0.5, 1.0)[index % 3],
                        } for seat in range(1, opponents + 1))
                yield (opponents, street, index), {
                    "hero_cards": cards[:2], "board": cards[2:], "opponents": opponents,
                    "pot": (300, 800, 1800)[index % 3], "to_call": (0, 100, 500, 900)[index % 4],
                    "actions": actions,
                }


def long_histories():
    from coach.multiway import MAX_PUBLIC_ACTIONS
    from poker_analyzer import FULL_DECK

    rng = Random(20261128)
    for opponents in (2, 3):
        for index in range(16):
            cards = rng.sample(FULL_DECK, 7)
            aggressive = index % 2 == 0
            actions = []
            for street in ("preflop", "flop", "turn", "river"):
                for count in range(MAX_PUBLIC_ACTIONS // 4):
                    action = "raise" if aggressive else ("raise", "call", "check")[count % 3]
                    actions.append({
                        "seat": count % opponents + 1, "street": street,
                        "action": action, "pot_fraction": (1.0 if aggressive else 0.5),
                    })
            yield (opponents, "river", index), {
                "hero_cards": cards[:2], "board": cards[2:], "opponents": opponents,
                "pot": 1_200, "to_call": 550, "actions": actions,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-history", action="store_true", help="measure 32 public actions per request")
    args = parser.parse_args()
    for setting in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[setting] = "1"
    os.environ["POKER_COACH_MULTIWAY_RANGES"] = "1"
    os.environ["POKER_COACH_WARMUP"] = "0"
    from fastapi.testclient import TestClient
    from main import app

    timings = defaultdict(list)
    rejected = []
    cohort = long_histories if args.max_history else requests
    with TemporaryDirectory(prefix="coach-multiway-") as temp:
        os.environ["COACH_DB_PATH"] = str(Path(temp) / "synthetic.sqlite")
        with TestClient(app) as client:
            assert client.get("/api/coach/multiway/settings").json() == {"opponent_actions": True}
            for (opponents, street, index), payload in cohort():
                start = perf_counter()
                response = client.post("/api/coach/multiway", json=payload)
                elapsed = 1_000 * (perf_counter() - start)
                if index == (15 if args.max_history else 7):
                    print(f"{opponents} opponents, {street} complete", flush=True)
                if args.max_history and response.status_code == 422:
                    rejected.append({"opponents": opponents, "street": street, "index": index,
                                     "ms": round(elapsed, 2), "detail": response.json()["detail"]})
                    continue
                response.raise_for_status()
                assert len(response.json()["opponent_ranges"]) == opponents
                timings[opponents, street].append(elapsed)
                timings[opponents, "all"].append(elapsed)
            if args.max_history:
                oversized = {**payload, "actions": [*payload["actions"], payload["actions"][-1]]}
                assert client.post("/api/coach/multiway", json=oversized).status_code == 422
    for (opponents, street), values in timings.items():
        print(json.dumps({
            "opponents": opponents, "street": street, "requests": len(values),
            "median_ms": round(median(values), 2), "p95_ms": round(sorted(values)[math.ceil(.95 * len(values)) - 1], 2),
        }))
    if args.max_history:
        print(json.dumps({"rejected": rejected}))


if __name__ == "__main__":
    main()
