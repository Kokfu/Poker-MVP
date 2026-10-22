"""Reproducible Phase 5 solver performance benchmark.

Plays a fixed set of engine hands with fixed seeds to gather:

* ~30 solver decision "spots" spanning preflop/flop/turn/river, both an
  initial (cached) street solve and a re-solve forced by an off-tree
  opponent size, and both with and without a confident opponent profile
  (node locks).  Each spot records the exact mixed strategy the bot sampled
  from (full precision) and the action it chose.
* 200 fixed full hands of ``solver`` vs ``equity`` used to check that every
  chosen action stays identical after a performance change.

Nothing here changes RNG consumption or decision logic: ``_BenchSolver`` only
wraps ``SolverBot._sample`` to also stash the exact probability vector it was
given, so recorded decisions are byte-identical to what ``SolverBot`` would
have done unwrapped.

    python -m solver.benchmark                              # run, print report
    python -m solver.benchmark --save baseline.json          # also write a fixture
    python -m solver.benchmark --compare baseline.json       # run and diff

Baseline recorded at commit b3be891 (pre-optimization) lives at
``solver/data/benchmark_baseline.json`` and is also used by
``test_solver_benchmark.py`` (a smaller, faster configuration) to guard
against future behavior changes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine
from simulation.opponent_model import OpponentModel
from solver.bot import AdaptiveSolverBot, SolverBot

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_BASELINE = DATA_DIR / "benchmark_baseline.json"

STARTING_STACK = 10_000
BIG_BLIND = 100
EQUITY_ITERATIONS = 300  # only affects opponent bots' own decisions, not the solver

SPOT_OPPONENTS = ("equity", "aggressive", "tight", "random", "expert")
PROFILE_OPPONENT = "equity"
HAND_OPPONENT = "equity"

# Disjoint from development/holdout evaluation seed ranges (see
# simulation.duplicate_evaluation and ROADMAP.md); this benchmark never feeds
# acceptance evidence, only performance/equivalence evidence.
SPOT_SEED_BASE = 9_100_000
PROFILE_SEED_BASE = 9_200_000
HAND_SEED_BASE = 9_300_000


class _BenchSolver(SolverBot):
    """``SolverBot`` that also stashes the exact vector it samples from.

    ``_sample`` is called once per decision with the already-computed mixed
    strategy for the bot's own combo; recording it here does not add or skip
    any RNG draw, so play is identical to an unwrapped ``SolverBot``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_probabilities: list[np.ndarray] = []

    def _sample(self, ds, probabilities: np.ndarray) -> int:
        self.raw_probabilities.append(np.array(probabilities, dtype=float))
        return super()._sample(ds, probabilities)


class _BenchAdaptiveSolver(_BenchSolver):
    exploit = True
    pool_streets = True


class _Recorder:
    """Wraps a solver bot for ``HandEngine`` and records every decision."""

    def __init__(self, solver):
        self.solver = solver
        self.entries: list[dict[str, Any]] = []
        self.hand_seed: int | None = None

    def __getattr__(self, name):
        return getattr(self.solver, name)

    def decide(self, observation):
        return self.solver.decide(observation)

    def decide_decision(self, observation):
        started = time.perf_counter()
        action = self.solver.decide_decision(observation)
        elapsed = time.perf_counter() - started
        explanation = dict(self.solver.last_explanation or {})
        ds = observation.decision_state
        raw = getattr(self.solver, "raw_probabilities", None)
        probabilities = [round(float(p), 8) for p in raw[-1]] if raw else list(explanation.get("probabilities", []))
        entry = {
            "hand_seed": self.hand_seed,
            "hand_number": ds.hand_number,
            "street": ds.street,
            "action": action.type,
            "target": action.amount,
            "elapsed": elapsed,
            "source": explanation.get("source"),
            "resolved_from_current_state": explanation.get("resolved_from_current_state", False),
            "locked_nodes": explanation.get("exploit", {}).get("locked_nodes", 0),
            "probabilities": probabilities,
            "labels": list(explanation.get("labels", [])),
            "chosen": explanation.get("chosen"),
        }
        self.entries.append(entry)
        return action


def _play_hands(recorder: _Recorder, opponent, count: int, seed_base: int, profile_models: dict | None) -> None:
    for index in range(count):
        seed = seed_base + index
        recorder.hand_seed = seed
        engine = HandEngine(
            recorder, opponent,
            starting_stacks={"a": STARTING_STACK, "b": STARTING_STACK}, bb=BIG_BLIND,
            seed=seed, simulation_seed=seed_base, button="a" if index % 2 == 0 else "b",
            hand_id=f"bench-{seed_base}-{index}", hand_number=index + 1, match_id=f"bench-{seed_base}",
            opponent_profile_provider=(
                (lambda player, models=profile_models: models["b" if player == "a" else "a"].snapshot())
                if profile_models is not None else None
            ),
        )
        result = engine.play()
        if result["illegal_actions"]:
            raise RuntimeError(f"illegal action in benchmark hand seed={seed}")
        if profile_models is not None:
            profile_models["a"].update(result["history"])
            profile_models["b"].update(result["history"])


def _collect_spot_pool(hands_per_opponent: int, profile_warmup: int, profile_sample: int) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for offset, opponent_name in enumerate(SPOT_OPPONENTS):
        solver = _BenchSolver(seed=SPOT_SEED_BASE + offset * 1000)
        recorder = _Recorder(solver)
        opponent = BOT_TYPES[opponent_name](seed=SPOT_SEED_BASE + offset * 1000, equity_iterations=EQUITY_ITERATIONS)
        _play_hands(recorder, opponent, hands_per_opponent, SPOT_SEED_BASE + offset * 1000, None)
        for entry in recorder.entries:
            pool.append({**entry, "has_profile": False, "opponent": opponent_name})

    solver = _BenchAdaptiveSolver(seed=PROFILE_SEED_BASE)
    recorder = _Recorder(solver)
    opponent = BOT_TYPES[PROFILE_OPPONENT](seed=PROFILE_SEED_BASE, equity_iterations=EQUITY_ITERATIONS)
    models = {"a": OpponentModel("a"), "b": OpponentModel("b")}
    _play_hands(recorder, opponent, profile_warmup, PROFILE_SEED_BASE, models)
    recorder.entries.clear()  # discard the warm-up decisions themselves
    _play_hands(recorder, opponent, profile_sample, PROFILE_SEED_BASE + profile_warmup, models)
    for entry in recorder.entries:
        pool.append({**entry, "has_profile": True, "opponent": PROFILE_OPPONENT})
    return pool


def _select_spots(pool: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    def on_tree(entry: dict[str, Any]) -> bool:
        return not entry["resolved_from_current_state"]

    def bucket(entry: dict[str, Any]) -> tuple:
        return (entry["street"], on_tree(entry), entry["has_profile"])

    ordered = sorted(pool, key=lambda e: (e["hand_seed"], e["hand_number"], e["street"]))
    chosen: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for entry in ordered:
        b = bucket(entry)
        if b not in seen:
            seen.add(b)
            chosen.append(entry)
    for entry in ordered:
        if len(chosen) >= target:
            break
        if not any(entry is c for c in chosen):
            chosen.append(entry)
    return chosen[:target]


def _run_fixed_hands(count: int, seed_base: int) -> list[dict[str, Any]]:
    results = []
    for index in range(count):
        seed = seed_base + index
        solver = SolverBot(seed=seed_base)
        recorder = _Recorder(solver)
        recorder.hand_seed = seed
        opponent = BOT_TYPES[HAND_OPPONENT](seed=seed, equity_iterations=EQUITY_ITERATIONS)
        engine = HandEngine(
            recorder, opponent,
            starting_stacks={"a": STARTING_STACK, "b": STARTING_STACK}, bb=BIG_BLIND,
            seed=seed, simulation_seed=seed_base, button="a" if index % 2 == 0 else "b",
            hand_id=f"bench-hand-{seed}", hand_number=1, match_id=f"bench-hand-{seed}",
        )
        result = engine.play()
        if result["illegal_actions"]:
            raise RuntimeError(f"illegal action in fixed hand seed={seed}")
        results.append({
            "seed": seed,
            "winner": result["winner"],
            "showdown": result["showdown"],
            "net_chips_a": result["stacks"]["a"] - STARTING_STACK,
            "fallback_count": solver.fallback_count,
            "actions": [{"street": e["street"], "action": e["action"], "target": e["target"]} for e in recorder.entries],
            "decision_timings_ms": [{"street": e["street"], "elapsed_ms": e["elapsed"] * 1000} for e in recorder.entries],
        })
    return results


def _timing_summary(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"count": 0}
    ordered = sorted(samples_ms)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "count": len(samples_ms),
        "mean_ms": round(statistics.mean(samples_ms), 3),
        "median_ms": round(statistics.median(samples_ms), 3),
        "p95_ms": round(p95, 3),
        "total_ms": round(sum(samples_ms), 3),
    }


def run_benchmark(
    spot_count: int = 30,
    hands_per_opponent: int = 6,
    profile_warmup: int = 40,
    profile_sample: int = 20,
    fixed_hand_count: int = 200,
) -> dict[str, Any]:
    started = time.perf_counter()
    pool = _collect_spot_pool(hands_per_opponent, profile_warmup, profile_sample)
    spots = _select_spots(pool, spot_count)
    fixed_hands = _run_fixed_hands(fixed_hand_count, HAND_SEED_BASE)

    by_street: dict[str, list[float]] = {}
    for entry in pool:
        by_street.setdefault(entry["street"], []).append(entry["elapsed"] * 1000)
    all_ms: list[float] = [entry["elapsed"] * 1000 for entry in pool]
    for hand in fixed_hands:
        for timing in hand["decision_timings_ms"]:
            by_street.setdefault(timing["street"], []).append(timing["elapsed_ms"])
            all_ms.append(timing["elapsed_ms"])

    report = {
        "config": {
            "spot_count": spot_count,
            "hands_per_opponent": hands_per_opponent,
            "profile_warmup": profile_warmup,
            "profile_sample": profile_sample,
            "fixed_hand_count": fixed_hand_count,
        },
        "spots": [
            {k: v for k, v in spot.items()} for spot in spots
        ],
        "fixed_hands": fixed_hands,
        "timing": {
            "overall_ms": _timing_summary(all_ms),
            "by_street_ms": {street: _timing_summary(values) for street, values in sorted(by_street.items())},
        },
        "wall_seconds": round(time.perf_counter() - started, 2),
    }
    return report


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def compare(report: dict[str, Any], baseline: dict[str, Any], atol: float = 1e-5) -> list[str]:
    """Human-readable list of equivalence differences; empty means equivalent."""
    problems: list[str] = []
    base_spots = {(s["hand_seed"], s["hand_number"], s["street"]): s for s in baseline["spots"]}
    for spot in report["spots"]:
        key = (spot["hand_seed"], spot["hand_number"], spot["street"])
        base = base_spots.get(key)
        if base is None:
            continue
        if spot["chosen"] != base["chosen"]:
            problems.append(f"spot {key}: chosen action changed {base['chosen']!r} -> {spot['chosen']!r}")
        a, b = np.array(spot["probabilities"]), np.array(base["probabilities"])
        if a.shape != b.shape or not np.allclose(a, b, atol=atol):
            diff = float(np.max(np.abs(a - b))) if a.shape == b.shape else float("nan")
            problems.append(f"spot {key}: strategy differs by {diff} (> {atol})")
    base_hands = {h["seed"]: h for h in baseline["fixed_hands"]}
    for hand in report["fixed_hands"]:
        base = base_hands.get(hand["seed"])
        if base is None:
            continue
        if hand["actions"] != base["actions"]:
            problems.append(f"hand seed={hand['seed']}: actions changed {base['actions']} -> {hand['actions']}")
        if hand["winner"] != base["winner"] or hand["net_chips_a"] != base["net_chips_a"]:
            problems.append(f"hand seed={hand['seed']}: result changed")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 solver performance benchmark")
    parser.add_argument("--spots", type=int, default=30)
    parser.add_argument("--hands-per-opponent", type=int, default=6)
    parser.add_argument("--profile-warmup", type=int, default=40)
    parser.add_argument("--profile-sample", type=int, default=20)
    parser.add_argument("--fixed-hands", type=int, default=200)
    parser.add_argument("--save", type=Path, default=None, help="write the report as a JSON fixture")
    parser.add_argument("--compare", type=Path, default=None, help="diff the report against a saved fixture")
    parser.add_argument("--quiet", action="store_true", help="only print the summary, not the full report")
    args = parser.parse_args(argv)

    report = run_benchmark(args.spots, args.hands_per_opponent, args.profile_warmup, args.profile_sample, args.fixed_hands)

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(report, indent=2, default=_json_default, sort_keys=True))

    problems: list[str] = []
    if args.compare:
        baseline = json.loads(args.compare.read_text())
        problems = compare(report, baseline)
        if problems:
            print(f"EQUIVALENCE FAILED ({len(problems)} problem(s)):")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"Equivalent to {args.compare} ({len(report['spots'])} spots, {len(report['fixed_hands'])} hands).")

    if not args.quiet:
        print(json.dumps(report["timing"], indent=2, default=_json_default))
        print(f"wall_seconds={report['wall_seconds']}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
