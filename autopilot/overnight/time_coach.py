"""Time the Coach API in-process with generated spots and an isolated SQLite database."""
import argparse
from contextlib import ExitStack
import gc
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi.testclient import TestClient
from coach.service import spot_to_dict
from coach.store import HandStore
from main import app
from test_coach_learning import simulated_spots


def action(actor, kind, amount=None):
    return {"actor": actor, "action": kind, "amount": amount}


def cases():
    preflop = [action("villain", "raise", 250), action("hero", "call")]
    checks = [action("hero", "check"), action("villain", "check")]
    for i, (cards, board) in enumerate([
        (["As", "Kd"], ["7h", "8d", "2c", "Jd", "3h"]),
        (["Jc", "9d"], ["Qh", "7s", "2d", "Tc", "3h"]),
        (["5h", "5d"], ["Ad", "Kc", "4c", "6s", "9d"]),
        (["Ac", "Qc"], ["Jc", "Tc", "2h", "3c", "Kd"]),
    ]):
        base = {"hero_cards": cards, "opponent": "Synthetic" if i % 2 else None}
        yield f"preflop-{i}", base
        yield f"flop-{i}", dict(base, hero_position="big_blind", actions=preflop, board=board[:3])
        yield f"turn-{i}", dict(base, hero_position="big_blind", actions=preflop + checks, board=board[:4])
        yield f"river-{i}", dict(base, hero_position="big_blind", actions=preflop + 2 * checks, board=board)


def measure(repeats):
    measurements = []
    with TemporaryDirectory() as scratch, ExitStack() as stack:
        # SQLite connection cycles can retain Windows file handles until GC.
        stack.callback(gc.collect)
        client = stack.enter_context(TestClient(app))
        os.environ["COACH_DB_PATH"] = str(Path(scratch) / "timing.sqlite")
        store = HandStore()
        for spot in simulated_spots("tight", 150):
            store.add("Synthetic", spot_to_dict(spot))
        for label, payload in cases():
            for repeat in range(repeats):
                start = perf_counter()
                response = client.post("/api/coach/advise", json=payload)
                ms = 1000 * (perf_counter() - start)
                response.raise_for_status()
                result = response.json()
                assert result["status"] == "hero_to_act", result
                explanation = result["explanation"]
                # Runtime metadata may change without any change to the advice.
                explanation.pop("solve_seconds", None)
                explanation.get("instrumentation", {}).pop("cache_hit", None)
                encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
                measurements.append({"spot": label, "repeat": repeat,
                                     "ms": round(ms, 2), "action": result["advice"],
                                     "source": explanation["source"],
                                     "advice_sha256": hashlib.sha256(encoded).hexdigest()})
    summary = {}
    for cohort in ("preflop", "postflop"):
        for phase in ("all", "first", "repeat"):
            ms = sorted(row["ms"] for row in measurements
                        if (row["spot"].startswith("preflop") == (cohort == "preflop"))
                        and (phase == "all" or (row["repeat"] == 0) == (phase == "first")))
            if ms:
                summary[f"{cohort}_{phase}"] = {"n": len(ms), "median_ms": median(ms),
                                               "p95_ms": ms[math.ceil(.95 * len(ms)) - 1]}
    return {"summary": summary, "measurements": measurements}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    print(json.dumps(measure(args.repeats), indent=2))
