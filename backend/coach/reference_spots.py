"""Verify fixed heads-up Coach advice using only synthetic history.

From backend, run python -m coach.reference_spots. To update expectations
after an approved advice change, pass --record to review the resulting diff.
"""

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

REFERENCE = Path(__file__).with_suffix(".json")


def fingerprint(body):
    explanation = body["explanation"] or {}
    # These report how the answer was obtained and vary across otherwise exact solves.
    explanation.pop("solve_seconds", None)
    explanation.get("instrumentation", {}).pop("cache_hit", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        **body["advice"],
        "probabilities": dict(zip(explanation.get("labels") or [], explanation.get("probabilities") or [], strict=True)),
        "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
    }


def run(fixture, *, progress=False):
    from fastapi.testclient import TestClient

    from coach.store import HandStore
    from main import app

    results = []
    with TemporaryDirectory(prefix="coach-reference-") as scratch:
        with patch.dict(os.environ, {
            "COACH_DB_PATH": str(Path(scratch) / "reference.sqlite"),
            "POKER_COACH_WARMUP": "0",
            "POKER_COACH_RIVER_SHADOW": "0",
            "POKER_COACH_PERSISTENT_RANGES": "0",
            "POKER_COACH_SOLVE_CACHE": "1",
        }):
            store = HandStore()
            for opponent, hands in fixture["histories"].items():
                for hand in hands:
                    store.add(opponent, hand)
            with TestClient(app) as client:
                for index, spot in enumerate(fixture["spots"], start=1):
                    start = perf_counter()
                    response = client.post("/api/coach/advise", json=spot["request"])
                    elapsed = 1_000 * (perf_counter() - start)
                    response.raise_for_status()
                    body = response.json()
                    street = spot["id"].split("-", 1)[0]
                    if body["status"] != "hero_to_act" or body["state"]["street"] != street:
                        raise ValueError(f"{spot['id']} did not reach the expected hero decision")
                    advice = fingerprint(body)
                    quick = None
                    if street != "preflop":
                        preview = client.post("/api/coach/advise/quick", json=spot["request"])
                        preview.raise_for_status()
                        quick = preview.json()["advice"]
                    results.append((spot, street, advice, quick, elapsed))
                    if progress and index % 48 == 0:
                        print(f"Evaluated {index}/{len(fixture['spots'])} reference spots", file=sys.stderr, flush=True)
    return results


def summarize(results):
    timings = defaultdict(list)
    agreement = defaultdict(lambda: {"spots": 0, "same_action": 0, "same_action_and_size": 0})
    for _, street, advice, quick, ms in results:
        timings[street].append(ms)
        if quick is not None:
            for group in (street, "postflop"):
                counts = agreement[group]
                counts["spots"] += 1
                counts["same_action"] += advice["action"] == quick["action"]
                counts["same_action_and_size"] += (
                    advice["action"] == quick["action"] and advice["amount"] == quick["amount"]
                )
            timings["postflop"].append(ms)
    return {
        "spots": len(results),
        "milliseconds": {
            street: {"median": round(median(values), 2), "p95": round(sorted(values)[math.ceil(.95 * len(values)) - 1], 2)}
            for street, values in timings.items()
        },
        "preview_agreement": dict(agreement),
    }


def write_reference(path, fixture):
    # Keep each request and its expectation together for review, while staying
    # under the repository's size limit.
    def rows(items):
        return ",\n".join("    " + json.dumps(item, separators=(",", ":")) for item in items)

    histories = ",\n".join(
        f"  {json.dumps(name)}: [\n{rows(hands)}\n  ]" for name, hands in fixture["histories"].items()
    )
    path.write_text(f'{{"histories":{{\n{histories}\n}},\n"spots":[\n{rows(fixture["spots"])}\n]}}\n', encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="explicitly replace the checked-in expectations")
    parser.add_argument("--progress", action="store_true", help="log checkpoints to stderr")
    args = parser.parse_args()
    # Set before importing FastAPI's Coach modules, which can load NumPy.
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    fixture = json.loads(REFERENCE.read_text(encoding="utf-8"))
    ids = [spot["id"] for spot in fixture["spots"]]
    if len(ids) != 192 or len(set(ids)) != len(ids):
        parser.exit(1, "Expected 192 distinct reference spot IDs\n")
    results = run(fixture, progress=args.progress)
    summary = summarize(results)
    if args.record:
        for spot, _, advice, _, _ in results:
            spot["expected"] = advice
        write_reference(REFERENCE, fixture)
        print(json.dumps(summary, indent=2))
        return 0
    differences = [spot["id"] for spot, _, advice, _, _ in results if spot["expected"] != advice]
    if differences:
        parser.exit(1, f"Coach advice changed at {len(differences)} spots: {', '.join(differences)}\n")
    print(json.dumps({**summary, "exact_matches": len(results)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
