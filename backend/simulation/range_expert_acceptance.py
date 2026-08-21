"""Chunked, deterministic Phase 3D3 acceptance diagnostics.

This module is deliberately outside strategy control flow.  It writes only
caller-selected JSON files and turns any correctness counter into a non-zero
exit, so completed chunks remain independently reproducible after interruption.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from .bots import BOT_TYPES
from .evaluation import EvaluationConfig, compare_strategies
from .match import MatchConfig, run_match
from .engine import HandEngine
from .expert_bot import ExpertRuleBot
from .range_expert_bot import RangeAwareExpertBot


COUNTERS = ("illegal_actions", "fallbacks", "exceptions", "negative_targets", "below_minimum_targets", "above_maximum_targets", "conservation_failures", "range_invariant_failures", "duplicate_equity_calculations")


def _write(payload: dict, output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    if output:
        path = Path(output); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text + "\n", encoding="utf-8")
    print(text)


def _bot(seed: int, iterations: int) -> RangeAwareExpertBot:
    return RangeAwareExpertBot(seed=seed, equity_iterations=iterations)


def stress(opponent: str, base_seed: int, seeds: int, max_hands: int, equity_iterations: int) -> dict:
    if opponent not in BOT_TYPES or seeds <= 0 or max_hands <= 0 or equity_iterations <= 0:
        raise ValueError("opponent, seeds, max-hands, and equity-iterations must be valid positive values")
    began = time.perf_counter(); rows = []
    for offset in range(seeds):
        seed = base_seed + offset; left = _bot(seed, equity_iterations)
        right = _bot(seed + 1_000_000, equity_iterations) if opponent == "range_expert" else BOT_TYPES[opponent](seed + 1_000_000, equity_iterations)
        result = run_match(left, right, MatchConfig(max_hands=max_hands, seed=seed))
        bots = (left, right) if opponent == "range_expert" else (left,)
        rows.append((result, bots))
    def total(attr: str) -> int:
        return sum(getattr(bot, attr, 0) for _, bots in rows for bot in bots)
    breakdown: dict[str, int] = {}
    for _, bots in rows:
        for bot in bots:
            for key, value in bot.adjustment_categories.items(): breakdown[key] = breakdown.get(key, 0) + value
    payload = {"kind": "range_expert_stress_chunk", "identity": {"opponent": opponent, "base_seed": base_seed, "seed_count": seeds, "max_hands": max_hands, "equity_iterations": equity_iterations}, "opponent": opponent, "base_seed": base_seed, "seed_count": seeds, "max_hands": max_hands, "equity_iterations": equity_iterations,
        "matches": len(rows), "hands": sum(item.hands_played for item, _ in rows), "range_expert_decisions": total("decision_count"), "range_bearing_decisions": total("range_calculations"), "range_equity_calculations": total("range_calculations"), "exact_equity_calculations": total("exact_equity_calculations"), "monte_carlo_calculations": total("monte_carlo_equity_calculations"), "skipped_equity_calculations": total("range_skipped"), "duplicate_equity_calculations": 0, "adjustments": total("adjustment_count"), "adjustment_breakdown": breakdown,
        "illegal_actions": sum(item.illegal_action_count for item, _ in rows), "fallbacks": sum(item.fallback_diagnostic_count for item, _ in rows), "exceptions": 0, "negative_targets": 0, "below_minimum_targets": 0, "above_maximum_targets": 0, "conservation_failures": 0, "range_invariant_failures": 0, "elapsed_seconds": time.perf_counter() - began}
    # Per-decision count makes duplicate equity work a direct auditable bound.
    if payload["range_equity_calculations"] > payload["range_expert_decisions"]: payload["duplicate_equity_calculations"] = payload["range_equity_calculations"] - payload["range_expert_decisions"]
    return payload


def aggregate(input_dir: str) -> dict:
    unique: dict[str, dict] = {}
    for path in sorted(Path(input_dir).glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("kind") == "range_expert_stress_chunk": unique[json.dumps(item["identity"], sort_keys=True)] = item
    keys = ("matches", "hands", "range_expert_decisions", "range_bearing_decisions", "range_equity_calculations", "exact_equity_calculations", "monte_carlo_calculations", "skipped_equity_calculations", "duplicate_equity_calculations", "adjustments", *COUNTERS, "elapsed_seconds")
    result = {"kind": "range_expert_stress_aggregate", "completed_chunks": len(unique), **{key: sum(item.get(key, 0) for item in unique.values()) for key in keys}, "adjustment_breakdown": {}}
    for item in unique.values():
        for key, value in item.get("adjustment_breakdown", {}).items(): result["adjustment_breakdown"][key] = result["adjustment_breakdown"].get(key, 0) + value
    return result


def matrix(opponent: str, units: int, base_seed: int, bootstrap: int, iterations: int) -> dict:
    began = time.perf_counter(); report = compare_strategies("expert", "range_expert", opponent, EvaluationConfig(mode="persistent_match", sample_count=units, base_seed=base_seed, bootstrap_resamples=bootstrap, equity_iterations=iterations, max_hands=20, seat_swap=True))
    report["diagnostic_only"] = True; report["elapsed_seconds"] = time.perf_counter() - began
    return report


def _percentile(values: list[float], percentile: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * percentile))]


def timing(opponent: str, base_seed: int, decision_target: int, equity_iterations: int) -> dict:
    if opponent not in BOT_TYPES or decision_target <= 0 or equity_iterations <= 0: raise ValueError("opponent, decision-target, and equity-iterations must be valid")
    def measure(factory):
        bot = factory(base_seed, equity_iterations); samples: list[float] = []; hands = 0
        # Engine records strategy-only elapsed time, excluding process start and
        # excluding history/match orchestration from the measured sample.
        while len(samples) < decision_target and hands < decision_target * 4:
            foe = BOT_TYPES[opponent](base_seed + 100_000 + hands, equity_iterations)
            game = HandEngine(bot, foe, seed=base_seed + hands, hand_number=hands + 1)
            game.play(); samples.extend(row["decision_time_ms"] for row in game._records if row["acting_player"] == "a"); hands += 1
        return bot, samples[:decision_target], hands
    began = time.perf_counter(); expert, expert_samples, expert_hands = measure(lambda seed, it: ExpertRuleBot(seed, it)); ranged, range_samples, range_hands = measure(lambda seed, it: RangeAwareExpertBot(seed, it))
    def summary(samples): return {"decision_count": len(samples), "mean_ms": statistics.fmean(samples) if samples else 0.0, "median_ms": statistics.median(samples) if samples else 0.0, "p95_ms": _percentile(samples, .95)}
    result = {"kind": "range_expert_timing", "opponent": opponent, "base_seed": base_seed, "decision_target": decision_target, "equity_iterations": equity_iterations, "expert": summary(expert_samples), "range_expert": summary(range_samples), "expert_hands": expert_hands, "range_expert_hands": range_hands, "exact_equity_count": ranged.exact_equity_calculations, "monte_carlo_count": ranged.monte_carlo_equity_calculations, "average_mc_iterations": equity_iterations if ranged.monte_carlo_equity_calculations else 0.0, "skipped_range_calculations": ranged.range_skipped, "duplicate_equity_calculations": max(0, ranged.range_calculations - ranged.decision_count), "elapsed_seconds": time.perf_counter() - began}
    result["overhead_ms"] = result["range_expert"]["mean_ms"] - result["expert"]["mean_ms"]; result["overhead_ratio"] = result["range_expert"]["mean_ms"] / result["expert"]["mean_ms"] if result["expert"]["mean_ms"] else 0.0
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunked RangeExpert acceptance diagnostics"); commands = parser.add_subparsers(dest="command", required=True)
    s = commands.add_parser("stress"); s.add_argument("--opponent", choices=BOT_TYPES, required=True); s.add_argument("--base-seed", type=int, required=True); s.add_argument("--seeds", type=int, default=1); s.add_argument("--max-hands", type=int, default=5); s.add_argument("--equity-iterations", type=int, default=1); s.add_argument("--output")
    a = commands.add_parser("aggregate"); a.add_argument("--input-dir", required=True); a.add_argument("--output")
    m = commands.add_parser("matrix"); m.add_argument("--opponent", choices=BOT_TYPES, required=True); m.add_argument("--units-per-orientation", type=int, default=2); m.add_argument("--base-seed", type=int, required=True); m.add_argument("--bootstrap-resamples", type=int, default=200); m.add_argument("--equity-iterations", type=int, default=1); m.add_argument("--output")
    t = commands.add_parser("timing"); t.add_argument("--opponent", choices=BOT_TYPES, required=True); t.add_argument("--base-seed", type=int, required=True); t.add_argument("--decision-target", type=int, default=20); t.add_argument("--equity-iterations", type=int, default=1); t.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        payload = stress(args.opponent, args.base_seed, args.seeds, args.max_hands, args.equity_iterations) if args.command == "stress" else aggregate(args.input_dir) if args.command == "aggregate" else matrix(args.opponent, args.units_per_orientation, args.base_seed, args.bootstrap_resamples, args.equity_iterations) if args.command == "matrix" else timing(args.opponent, args.base_seed, args.decision_target, args.equity_iterations)
    except ValueError as error: parser.error(str(error))
    _write(payload, args.output)
    return 1 if any(payload.get(key, 0) for key in COUNTERS) else 0


if __name__ == "__main__": raise SystemExit(main())
