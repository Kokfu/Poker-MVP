"""Command line entry point for duplicate-deal evaluation (Phase 5A).

Examples::

    python -m simulation.duplicate_cli pair --strategy expert --opponent random --pairs 500
    python -m simulation.duplicate_cli tournament --pairs 2000 --workers 8 --output baseline.json
    python -m simulation.duplicate_cli gate --report baseline.json --candidate range_expert
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .bots import BOT_TYPES
from .duplicate_evaluation import SEED_SETS, DuplicateConfig, duplicate_report, run_tournament, win_rate_gate
from .evaluation import json_report_text, write_json_report


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pairs", type=int, default=500)
    parser.add_argument("--seed-set", choices=tuple(SEED_SETS), default="development")
    parser.add_argument("--seed-offset", type=int, default=0)
    parser.add_argument("--session-hands", type=int, default=1, help="hands per learning session (1 = independent hands)")
    parser.add_argument("--starting-stack", type=int, default=10_000)
    parser.add_argument("--small-blind", type=int, default=50)
    parser.add_argument("--big-blind", type=int, default=100)
    parser.add_argument("--equity-iterations", type=int, default=100)
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    parser.add_argument("--statistics-seed", type=int, default=91_002)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--output")
    parser.add_argument("--overwrite", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Duplicate-deal heads-up evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("pair", help="one strategy against one opponent")
    pair.add_argument("--strategy", choices=BOT_TYPES, required=True)
    pair.add_argument("--opponent", choices=BOT_TYPES, required=True)
    _add_common(pair)
    tournament = commands.add_parser("tournament", help="round robin with pool standings")
    tournament.add_argument("--bots", nargs="+", choices=BOT_TYPES, default=list(BOT_TYPES))
    _add_common(tournament)
    gate = commands.add_parser("gate", help="apply the Phase 5 win-rate gate to a saved tournament")
    gate.add_argument("--report", required=True)
    gate.add_argument("--candidate", required=True)
    return parser


def _config(args: argparse.Namespace) -> DuplicateConfig:
    return DuplicateConfig(
        starting_stack=args.starting_stack, small_blind=args.small_blind, big_blind=args.big_blind,
        pairs=args.pairs, seed_set=args.seed_set, seed_offset=args.seed_offset,
        equity_iterations=args.equity_iterations, bootstrap_resamples=args.bootstrap_resamples,
        statistics_seed=args.statistics_seed, workers=args.workers, session_hands=args.session_hands,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "gate":
            report = win_rate_gate(json.loads(Path(args.report).read_text(encoding="utf-8")), args.candidate)
        else:
            config = _config(args)
            if args.command == "pair":
                report = duplicate_report(config, args.strategy, args.opponent)
            else:
                report = run_tournament(config, args.bots)
            if args.output:
                write_json_report(report, args.output, overwrite=args.overwrite)
            report = {key: value for key, value in report.items() if key not in {"raw_pairs", "bootstrap_pool_samples"}}
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json_report_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
