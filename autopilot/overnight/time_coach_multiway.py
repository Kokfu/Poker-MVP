"""Measure the flagged public-action range path on two and three opponents."""

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


def main():
    for setting in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[setting] = "1"
    os.environ["POKER_COACH_MULTIWAY_RANGES"] = "1"
    os.environ["POKER_COACH_WARMUP"] = "0"
    from fastapi.testclient import TestClient
    from main import app

    timings = defaultdict(list)
    with TemporaryDirectory(prefix="coach-multiway-") as temp:
        os.environ["COACH_DB_PATH"] = str(Path(temp) / "synthetic.sqlite")
        with TestClient(app) as client:
            assert client.get("/api/coach/multiway/settings").json() == {"opponent_actions": True}
            for (opponents, street, index), payload in requests():
                start = perf_counter()
                response = client.post("/api/coach/multiway", json=payload)
                elapsed = 1_000 * (perf_counter() - start)
                response.raise_for_status()
                assert len(response.json()["opponent_ranges"]) == opponents
                timings[opponents, street].append(elapsed)
                timings[opponents, "all"].append(elapsed)
                if index == 7:
                    print(f"{opponents} opponents, {street} complete", flush=True)
    for (opponents, street), values in timings.items():
        print(json.dumps({
            "opponents": opponents, "street": street, "requests": len(values),
            "median_ms": round(median(values), 2), "p95_ms": round(sorted(values)[math.ceil(.95 * len(values)) - 1], 2),
        }))


if __name__ == "__main__":
    main()
