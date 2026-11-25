"""Measure the quick Coach response and verify full advice on real loopback HTTP."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import gc
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx

from time_coach import action, advice_hash, http_client, populate_profiles, representative_scenarios, scenarios
from poker_analyzer import FULL_DECK


def facing_rivers():
    rng = Random(77261126)
    earlier = [action("villain", "raise", 250), action("hero", "call")]
    earlier += [action("hero", "check"), action("villain", "check")] * 2
    earlier.append(action("hero", "check"))
    for index in range(48):
        cards = rng.sample(FULL_DECK, 7)
        yield f"river-facing-{index}", {
            "hero_cards": cards[:2], "board": cards[2:], "hero_position": "big_blind",
            "hero_stack": (500, 2_500, 6_000, 10_000)[index % 4],
            "actions": earlier + [action("villain", "bet", (100, 250, 900, 2_200)[index // 4 % 4])],
        }


def p95(values):
    return sorted(values)[math.ceil(.95 * len(values)) - 1]


def measure(workload, parallel):
    fixture, reference_path = {
        "original": (scenarios(3), "coach-quiet-off-1.json"),
        "representative": (representative_scenarios(), "coach-representative-off.json"),
        "river": (facing_rivers(), None),
    }[workload]
    expected = {}
    if reference_path:
        path = Path(__file__).with_name("jobs") / reference_path
        expected = {row["spot"]: row["advice_sha256"] for row in json.loads(path.read_text(encoding="utf-8-sig"))["measurements"]}

    quick_times, full_times, choices = [], [], Counter()
    with TemporaryDirectory() as scratch, ExitStack() as stack:
        stack.callback(gc.collect)
        os.environ["COACH_DB_PATH"] = str(Path(scratch) / "quick.sqlite")
        populate_profiles(workload == "representative")
        preview = http_client(stack, scratch)
        final = stack.enter_context(httpx.Client(base_url=preview.base_url, timeout=60, trust_env=False))
        worker = stack.enter_context(ThreadPoolExecutor(max_workers=1))

        def request_preview(body, started):
            response = preview.post("/api/coach/advise/quick", json=body)
            elapsed = (perf_counter() - started) * 1000
            response.raise_for_status()
            return response.json(), elapsed

        for label, body in fixture:
            started = perf_counter()
            pending = worker.submit(request_preview, body, started) if body.get("board") else None
            if pending is not None and not parallel:
                try:
                    pending.result(timeout=.05)
                except TimeoutError:
                    pass
            response = final.post("/api/coach/advise", json=body)
            full_times.append((perf_counter() - started) * 1000)
            response.raise_for_status()
            result = response.json()
            assert result["status"] == "hero_to_act", label
            if expected:
                assert advice_hash(result) == expected[label], label
            if pending is not None:
                quick, elapsed = pending.result()
                assert quick["status"] == "quick" and quick["advice"]["action"] in quick["state"]["legal_actions"], label
                choices[quick["advice"]["action"]] += 1
                quick_times.append(elapsed)

    assert len(full_times) == 48 and len(quick_times) == (48 if workload == "river" else 36)
    if expected:
        print(f"{workload}: all 48 full advice hashes matched.")
    print(f"{workload}: {len(quick_times)} previews, median {median(quick_times):.2f} ms, "
          f"p95 {p95(quick_times):.2f} ms, max {max(quick_times):.2f} ms; "
          f"full p95 {p95(full_times):.2f} ms; legal actions {dict(choices)}.")
    return max(quick_times)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workload", choices=("original", "representative", "river"))
    parser.add_argument("--parallel", action="store_true", help="start the full request without a 50 ms preview head start")
    args = parser.parse_args()
    if measure(args.workload, args.parallel) >= 300:
        parser.exit(1, "At least one quick response took 300 ms or longer.\n")
