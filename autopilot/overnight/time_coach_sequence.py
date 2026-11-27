"""Time fixed postflop decisions with the earlier advice a player would request."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

CARD_COUNT = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}


def earlier_requests(payload, request_type, replay):
    for count in range(len(payload["actions"])):
        prefix = {**payload, "actions": payload["actions"][:count]}
        status, result, _ = replay(request_type(**prefix).to_spot())
        if status == "hero_to_act":
            needed = CARD_COUNT[result["state"]["street"]]
            if needed < len(payload["board"]):
                yield {**prefix, "board": payload["board"][:needed]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("first-use", "sequence"))
    args = parser.parse_args()
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    for setting in ("POKER_COACH_WARMUP", "POKER_COACH_RIVER_SHADOW", "POKER_COACH_PERSISTENT_RANGES"):
        os.environ[setting] = "0"
    os.environ["POKER_COACH_SOLVE_CACHE"] = "1"
    os.environ["POKER_COACH_SOLVE_DISK_CACHE"] = "1"

    from fastapi.testclient import TestClient
    from coach.reference_spots import REFERENCE, fingerprint
    from coach.service import _replay
    from coach.store import HandStore
    from main import CoachAdviseRequest, app

    fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
    rng = Random(20261127)
    chosen = set()
    for street in ("flop", "turn", "river"):
        chosen.update(rng.sample([spot["id"] for spot in fixture["spots"] if spot["id"].startswith(street + "-")], 16))

    samples = defaultdict(list)
    earlier_count = 0
    with TemporaryDirectory(prefix="coach-sequence-") as temp:
        os.environ["COACH_DB_PATH"] = str(Path(temp) / "synthetic.sqlite")
        store = HandStore()
        for opponent, hands in fixture["histories"].items():
            for hand in hands:
                store.add(opponent, hand)
        with TestClient(app) as client:
            for spot in fixture["spots"]:
                if spot["id"] not in chosen:
                    continue
                payload = spot["request"]
                prefixes = earlier_requests(payload, CoachAdviseRequest, _replay)
                for prefix in prefixes if args.mode == "sequence" else ():
                    client.post("/api/coach/advise", json=prefix).raise_for_status()
                    earlier_count += 1
                start = perf_counter()
                response = client.post("/api/coach/advise", json=payload)
                elapsed = 1_000 * (perf_counter() - start)
                response.raise_for_status()
                if fingerprint(response.json()) != spot["expected"]:
                    raise ValueError(f"advice changed at {spot['id']}")
                samples[spot["id"].split("-", 1)[0]].append(elapsed)
                samples["postflop"].append(elapsed)
    for street, times in samples.items():
        print(json.dumps({
            "mode": args.mode, "street": street, "requests": len(times),
            "median_ms": round(median(times), 2), "p95_ms": round(sorted(times)[math.ceil(.95 * len(times)) - 1], 2),
        }))
    print(f"Matched {len(chosen)} full fingerprints after {earlier_count} earlier requests.")


if __name__ == "__main__":
    main()
