"""Complete-case diagnostics after a Phase 4Q integrity abort.

The frozen runner still aborts on any unexpected fallback. This reader keeps
the same holdout keys, model, truth and inputs. It enumerates failed keys and
summarizes only pairs that could be evaluated, with no second promotion gate.
"""
from argparse import ArgumentParser
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np

from research.holdem import phase_4q as frozen
from solver.bot import ReplayError


class Fallback(RuntimeError):
    def __init__(self, reason, solve):
        self.reason = reason
        self.solve = solve


class FailureTrace(frozen.PriorTrace):
    """Read the failed solve's inputs without perturbing the solver."""
    failed_solve = None

    def _solve(self, state, board, ranges, hero_combo, hero, profile=None):
        try:
            return super()._solve(state, board, ranges, hero_combo, hero, profile)
        except ReplayError:
            self.failed_solve = {
                "state": asdict(state), "board": board, "hero": hero,
                "positive_reach": [int(np.count_nonzero(weights > 0)) for weights in ranges],
                "weighted_reach": [float(weights.sum()) for weights in ranges],
            }
            raise

    def trace(self, spot, profile=None):
        try:
            return super().trace(spot, profile)
        except RuntimeError as error:
            if not self.fallback_count:
                raise
            raise Fallback(str(error), self.failed_solve) from error


def verify_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    repo = Path(__file__).resolve().parents[3]
    for name, digest in manifest.items():
        if sha256((repo / name).read_bytes()).hexdigest() != digest.lower():
            raise ValueError(f"frozen input changed: {name}")
    return len(manifest)


def run():
    seed, size, streams = frozen.PANELS["holdout"]
    population = frozen.population_counts()
    keys = [(stream, name) for stream in streams for name in frozen.STYLES]
    profiles = {(s, n): frozen.train(n, s, frozen.PROFILES[1:]) for s, n in keys}
    counts = {(s, n): frozen.profile_counts(n, s) for s, n in keys}
    cases = {stream: list(frozen.cases(seed, size, orientation))
             for orientation, stream in enumerate(streams)}
    rows, failures = [], []
    original = frozen.PriorTrace
    frozen.PriorTrace = FailureTrace
    try:
        # Group by board to reuse the exact same production equity matrices.
        for index in range(size):
            for orientation, stream in enumerate(streams):
                case = cases[stream][index]
                hands = frozen.PROFILES[(index // 4 + index + orientation) % len(frozen.PROFILES)]
                for name in frozen.STYLES:
                    profile = profiles[stream, name].get(hands)
                    try:
                        rows.append(frozen.evaluate(case, name, stream, hands, profile,
                                                    counts[stream, name][hands], population))
                    except Fallback as error:
                        failures.append({
                            "case": asdict(case), "opponent": name, "stream": stream, "hands": hands,
                            "observed": case.observed, "failure": error.reason, "failed_solve": error.solve,
                            "history": [asdict(action) for action in case.spot().actions],
                        })
            print(f"Board {index + 1}/{size}: {len(rows)} scored, {len(failures)} failed", flush=True)
    finally:
        frozen.PriorTrace = original
    order = lambda r: (r["stream"], tuple(frozen.STYLES).index(r["opponent"]), r["case"]["index"])
    rows.sort(key=order)
    failures.sort(key=order)
    if len(rows) + len(failures) != size * len(keys):
        raise AssertionError("missing holdout key")

    extractors = {
        "opponent": lambda r: r["opponent"], "profile": lambda r: r["hands"],
        "depth": lambda r: r["case"]["depth"], "spr": lambda r: r["spr_band"],
        "wager": lambda r: r["observed"][2], "stream": lambda r: r["stream"],
        "turn_pressure": lambda r: r["opening"]["turn_pressure"],
        "effective_remaining_bb": lambda r: (
            0 if r["opening"]["bettor_stack"] <= 800 else 1 if r["opening"]["bettor_stack"] <= 1600 else 2
        ),
    }
    strata = {k: {str(value): frozen.summarize([r for r in rows if fn(r) == value])
                  for value in sorted({fn(r) for r in rows})} for k, fn in extractors.items()}
    # Bootstrap the incomplete matrix only as a descriptive sensitivity.
    # If an entire board-stream cell is absent there is no justified cell mean.
    intervals = None
    if len({(r["case"]["index"], r["stream"]) for r in rows}) == size * len(streams):
        intervals = {s: {a: frozen.interval(rows, s, a) for a in frozen.ARMS[1:]} for s in frozen.SETTINGS}
    summary = frozen.summarize(rows)
    return {
        "panel": "holdout-diagnostic", "rows": rows, "failures": failures, "summary": summary,
        "strata": strata, "intervals": intervals, "gate": {"pass": False, "reason": "frozen run aborted"},
        "unchanged_fallback_delta_sensitivity": {
            s: {a: mean([*(frozen.old.delta(r, s, a) for r in rows), *([0.] * len(failures))])
                for a in frozen.ARMS[1:]} for s in frozen.SETTINGS
        },
    }


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("manifest", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.output.exists():
        cli.error("output already exists")
    inputs = verify_manifest(args.manifest)
    start = perf_counter()
    result = run()
    if not result["failures"]:
        raise AssertionError("the frozen fallback was not reproduced")
    result.update(frozen_inputs_verified=inputs, wall_seconds=perf_counter() - start,
                  process_peak_resident_bytes=frozen.peak_resident_bytes())
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
