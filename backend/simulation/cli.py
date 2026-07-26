import argparse
import json

from .bots import BOT_TYPES
from .dataset import validate_dataset
from .engine import SimulationRunner
from .match_service import (
    DEFAULT_BIG_BLIND,
    DEFAULT_EQUITY_ITERATIONS,
    DEFAULT_MATCH_SEED,
    DEFAULT_MAX_HANDS,
    DEFAULT_SMALL_BLIND,
    DEFAULT_STARTING_STACK,
    run_builtin_match,
)


def add_bot_arguments(parser):
    parser.add_argument(
        "--bot-a",
        choices=BOT_TYPES,
        default="random",
        type=str.lower,
    )
    parser.add_argument(
        "--bot-b",
        choices=BOT_TYPES,
        default="random",
        type=str.lower,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Local heads-up poker simulator"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-bots")

    validate = subparsers.add_parser("validate-dataset")
    validate.add_argument("path")

    run = subparsers.add_parser("run")
    add_bot_arguments(run)
    run.add_argument("--hands", type=int, default=100)
    run.add_argument("--seed", type=int)
    run.add_argument("--starting-stack-bb", type=int, default=100)
    run.add_argument("--equity-iterations", type=int, default=1000)
    run.add_argument("--dataset-output")
    run.add_argument("--overwrite", action="store_true")

    match = subparsers.add_parser("match")
    add_bot_arguments(match)
    match.add_argument(
        "--starting-stack",
        type=int,
        default=DEFAULT_STARTING_STACK,
    )
    match.add_argument(
        "--small-blind",
        type=int,
        default=DEFAULT_SMALL_BLIND,
    )
    match.add_argument(
        "--big-blind",
        type=int,
        default=DEFAULT_BIG_BLIND,
    )
    match.add_argument(
        "--max-hands",
        type=int,
        default=DEFAULT_MAX_HANDS,
    )
    match.add_argument("--seed", type=int, default=DEFAULT_MATCH_SEED)
    match.add_argument(
        "--equity-iterations",
        type=int,
        default=DEFAULT_EQUITY_ITERATIONS,
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list-bots":
        print("\n".join(BOT_TYPES))
        return
    if args.command == "validate-dataset":
        result = validate_dataset(args.path)
        print(json.dumps(result, indent=2))
        raise SystemExit(1 if result["invalid_records"] else 0)
    if args.command == "match":
        try:
            result = run_builtin_match(
                bot_a=args.bot_a,
                bot_b=args.bot_b,
                starting_stack=args.starting_stack,
                small_blind=args.small_blind,
                big_blind=args.big_blind,
                max_hands=args.max_hands,
                seed=args.seed,
                equity_iterations=args.equity_iterations,
            )
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2))
        return

    first = BOT_TYPES[args.bot_a](
        seed=args.seed,
        equity_iterations=args.equity_iterations,
    )
    second = BOT_TYPES[args.bot_b](
        seed=None if args.seed is None else args.seed + 1,
        equity_iterations=args.equity_iterations,
    )
    result = SimulationRunner(
        first,
        second,
        args.hands,
        args.starting_stack_bb,
        args.seed,
        args.equity_iterations,
        args.dataset_output,
        args.overwrite,
    ).run()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
