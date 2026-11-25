"""Compare isolated turn and river advice with requests that followed earlier streets."""
from collections import defaultdict
import gc
import json
import math
import os
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from time_coach import advice_hash, populate_profiles, representative_scenarios
from coach.advisor import _SOLVES
from coach.service import _replay
from main import CoachAdviseRequest, coach_advise
from solver import bot
from solver.cfr import RangeSolver


def ask(body):
    result = coach_advise(CoachAdviseRequest(**body))
    assert result["status"] == "hero_to_act", result
    return result


def prior_spots(body):
    board_sizes = {"flop": 3, "turn": 4}
    for count in range(len(body["actions"])):
        prefix = {**body, "actions": body["actions"][:count]}
        status, payload, _ = _replay(CoachAdviseRequest(**prefix).to_spot())
        if status == "hero_to_act":
            size = board_sizes.get(payload["state"]["street"], 0)
            if 0 < size < len(body["board"]):
                yield {**prefix, "board": body["board"][:size]}


def run_profile(request_times):
    cases = list(representative_scenarios())
    for label, body in cases:
        if label.startswith("preflop-"):
            ask(body)

    rows = defaultdict(list)
    for index, (label, body) in enumerate(cases):
        street = label.split("-", 1)[0]
        if street not in ("turn", "river"):
            continue
        earlier = list(prior_spots(body))
        assert earlier, label
        hashes, comparison = {}, {}
        order = ("isolated", "sequential") if index % 2 == 0 else ("sequential", "isolated")
        for mode in order:
            bot._EQUITY_CACHE.clear()
            _SOLVES.clear()
            earlier_ms = 0.0
            if mode == "sequential":
                start = perf_counter()
                for spot in earlier:
                    ask(spot)
                earlier_ms = 1000 * (perf_counter() - start)

            request_times.clear()
            start = perf_counter()
            answer = ask(body)
            elapsed_ms = 1000 * (perf_counter() - start)
            assert answer["state"]["street"] == street
            prior_cfr = sum(request_times[f"{prior}_cfr_ms"] for prior in ("flop", "turn") if prior != street)
            sample = {
                "elapsed_ms": round(elapsed_ms, 2),
                "earlier_ms": round(earlier_ms, 2),
                "prior_cfr_ms": round(prior_cfr, 2),
                "new_cfr_ms": round(request_times[f"{street}_cfr_ms"], 2),
                "equity_ms": round(request_times["equity_ms"], 2),
                "other_ms": round(elapsed_ms - sum(request_times.values()), 2),
            }
            hashes[mode] = advice_hash(answer)
            comparison[mode] = sample
            rows[street, mode].append(sample)
        assert hashes["isolated"] == hashes["sequential"], label
        print(label, f"earlier_requests={len(earlier)}", json.dumps(comparison), flush=True)

    for (street, mode), results in rows.items():
        timings = sorted(item["elapsed_ms"] for item in results)
        medians = {key: round(median(item[key] for item in results), 2) for key in results[0]}
        p95 = timings[math.ceil(.95 * len(timings)) - 1]
        print("SUMMARY", street, mode, f"n={len(results)} p95={p95}", json.dumps(medians))
    print("Matched all 24 later-street advice hashes.")


def main():
    request_times = defaultdict(float)
    original_matrix, original_solve = bot.equity_matrix, RangeSolver.solve

    def timed_matrix(*args, **kwargs):
        start = perf_counter()
        result = original_matrix(*args, **kwargs)
        request_times["equity_ms"] += 1000 * (perf_counter() - start)
        return result

    def timed_solve(solver, *args, **kwargs):
        start = perf_counter()
        result = original_solve(solver, *args, **kwargs)
        street = solver.tree.nodes[solver.tree.root].state.street
        request_times[f"{street}_cfr_ms"] += 1000 * (perf_counter() - start)
        return result

    bot.equity_matrix, RangeSolver.solve = timed_matrix, timed_solve
    try:
        with TemporaryDirectory() as scratch:
            os.environ["COACH_DB_PATH"] = str(Path(scratch) / "timing.sqlite")
            os.environ["POKER_COACH_SOLVE_CACHE"] = "1"
            populate_profiles(representative=True)
            run_profile(request_times)
            gc.collect()
    finally:
        bot.equity_matrix, RangeSolver.solve = original_matrix, original_solve


if __name__ == "__main__":
    main()
