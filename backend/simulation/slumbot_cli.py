"""Benchmark a local bot against Slumbot's public API.

    python -m simulation.slumbot_cli --bot expert --hands 200 --output slumbot-expert.jsonl

Hands are played one at a time.  Each finished hand is appended to the JSONL
output immediately, so an interrupted session keeps its evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bots import BOT_TYPES
from .slumbot import SlumbotClient, result_dict, run_slumbot_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a local bot against Slumbot (heads-up, 200bb, 50/100)")
    parser.add_argument("--bot", choices=BOT_TYPES, required=True)
    parser.add_argument("--hands", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--equity-iterations", type=int, default=500)
    parser.add_argument("--pause-seconds", type=float, default=0.2)
    parser.add_argument("--output", help="JSONL file for per-hand results (appended)")
    args = parser.parse_args(argv)
    if args.hands <= 0:
        parser.error("--hands must be positive")
    output = Path(args.output) if args.output else None

    def record(result):
        line = json.dumps(result_dict(result), sort_keys=True)
        if output:
            with output.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        print(f"hand {result.hand_index + 1}: {result.winnings} chips {'DESYNC ' + result.desync if result.desync else ''}", flush=True)

    _, summary = run_slumbot_session(
        lambda index: BOT_TYPES[args.bot](seed=args.seed + index, equity_iterations=args.equity_iterations),
        args.hands, SlumbotClient(), pause_seconds=args.pause_seconds, on_hand=record,
    )
    print(json.dumps({"bot": args.bot, **summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
