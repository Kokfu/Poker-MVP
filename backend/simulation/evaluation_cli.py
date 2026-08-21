"""Command line entry point for deterministic strategy evaluation."""
from __future__ import annotations

import argparse

from .bots import BOT_TYPES
from .evaluation import (
    EvaluationConfig,
    compare_strategies,
    json_report_text,
    strategy_matrix,
    write_json_report,
)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("independent", "persistent_match"), default="persistent_match")
    parser.add_argument("--starting-stack", type=int, default=10_000)
    parser.add_argument("--small-blind", type=int, default=50)
    parser.add_argument("--big-blind", type=int, default=100)
    parser.add_argument("--max-hands", type=int, default=100)
    parser.add_argument("--sample-count", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=10_000)
    parser.add_argument("--equity-iterations", type=int, default=100)
    parser.add_argument("--no-seat-swap", action="store_true")
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    parser.add_argument("--statistics-seed", type=int, default=91_001)
    parser.add_argument("--output")
    parser.add_argument("--overwrite", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Statistical heads-up strategy evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="compare two strategies against one opponent")
    compare.add_argument("--control", choices=BOT_TYPES, default="expert")
    compare.add_argument("--treatment", choices=BOT_TYPES, default="adaptive")
    compare.add_argument("--opponent", choices=BOT_TYPES, required=True)
    _add_common(compare)
    matrix = commands.add_parser("matrix", help="run separate strategy-opponent rows")
    matrix.add_argument("--strategies", nargs="+", choices=BOT_TYPES, default=["expert", "adaptive"])
    matrix.add_argument("--opponents", nargs="+", choices=BOT_TYPES, default=["random", "tight", "aggressive", "equity", "expert"])
    _add_common(matrix)
    return parser


def _config(args: argparse.Namespace) -> EvaluationConfig:
    return EvaluationConfig(
        mode=args.mode,
        starting_stack=args.starting_stack,
        small_blind=args.small_blind,
        big_blind=args.big_blind,
        max_hands=args.max_hands,
        sample_count=args.sample_count,
        base_seed=args.base_seed,
        equity_iterations=args.equity_iterations,
        seat_swap=not args.no_seat_swap,
        bootstrap_resamples=args.bootstrap_resamples,
        statistics_seed=args.statistics_seed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = _config(args)
        if args.command == "compare":
            report = compare_strategies(args.control, args.treatment, args.opponent, config)
        else:
            report = strategy_matrix(args.strategies, args.opponents, config)
        if args.output:
            write_json_report(report, args.output, overwrite=args.overwrite)
    except ValueError as error:
        parser.error(str(error))
    print(json_report_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
