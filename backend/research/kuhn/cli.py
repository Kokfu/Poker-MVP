"""Research-only command line interface: ``python -m research.kuhn.cli train``."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cfr import KuhnCFRTrainer
from .cfr_plus import KuhnCFRPlusTrainer
from .convergence import DEFAULT_CHECKPOINTS, comparison_algorithm_metadata, comparison_report
from .evaluation import metrics

SCHEMA_VERSION = "1.0"
TARGET_VALUE = -1.0 / 18.0

def build_report(iterations: int, checkpoints: tuple[int, ...] = ()) -> dict[str, object]:
    trainer = KuhnCFRTrainer(); reports = []
    previous = 0
    for checkpoint in sorted(set(c for c in checkpoints if c <= iterations)) + ([iterations] if iterations not in checkpoints else []):
        trainer.train(checkpoint - previous); previous = checkpoint
        strategy = trainer.average_strategy(); measure = metrics(strategy, strategy)
        reports.append({"iterations": checkpoint, **measure, "value_error": abs(measure["player0_ev"] - TARGET_VALUE)})
    strategy = trainer.average_strategy(); measure = metrics(strategy, strategy)
    return {"kuhn_cfr_schema_version": SCHEMA_VERSION, "algorithm": "vanilla-cfr", "game": "canonical-three-card-kuhn",
            "game_convention": "two antes of one; u0 check-check +/-1, bet-fold +/-1, bet-call +/-2",
            "iterations": iterations, "information_sets": trainer.strategy_table(), "average_strategy":
            {key: {action.value: probability for action, probability in value.items()} for key, value in strategy.items()},
            "expected_value": measure["player0_ev"], "target_player0_value": TARGET_VALUE,
            "value_error": abs(measure["player0_ev"] - TARGET_VALUE), "best_response_values":
            {"br0": measure["br0"], "br1_as_u0": measure["br1_as_u0"]}, "nashconv": measure["nashconv"],
            "exploitability": measure["exploitability"], "exploitability_convention": "NashConv / 2", "convergence_checkpoints": reports}

def main() -> None:
    parser = argparse.ArgumentParser(description="Exact deterministic Kuhn Poker CFR research")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("train", "evaluate"):
        item = sub.add_parser(command); item.add_argument("--iterations", type=int, required=True)
        item.add_argument("--output", type=Path); item.add_argument("--overwrite", action="store_true")
    compare = sub.add_parser("compare", help="exact matched-checkpoint Vanilla CFR / CFR+ comparison")
    compare.add_argument("--iterations", type=int, default=max(DEFAULT_CHECKPOINTS))
    compare.add_argument("--averaging-delay", type=int, default=0)
    compare.add_argument("--output", type=Path); compare.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "compare":
        checkpoints = tuple(point for point in DEFAULT_CHECKPOINTS if point <= args.iterations)
        if args.iterations not in checkpoints:
            checkpoints += (args.iterations,)
        report = comparison_report({"vanilla-cfr": KuhnCFRTrainer,
                                    "cfr-plus": lambda: KuhnCFRPlusTrainer(args.averaging_delay)}, checkpoints,
                                   comparison_algorithm_metadata(args.averaging_delay))
        output = json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
        if args.output:
            if args.output.exists() and not args.overwrite: parser.error("output exists; pass --overwrite to replace it")
            args.output.write_text(output + "\n", encoding="utf-8")
        for index, checkpoint in enumerate(report["checkpoints"]):
            vanilla = report["algorithms"]["vanilla-cfr"][index]
            plus = report["algorithms"]["cfr-plus"][index]
            print("checkpoint {}: vanilla EV-error={:.10f} NashConv={:.10f} exploitability={:.10f}; "
                  "CFR+ EV-error={:.10f} NashConv={:.10f} exploitability={:.10f}".format(
                      checkpoint, vanilla["value_error"], vanilla["nashconv"], vanilla["exploitability"],
                      plus["value_error"], plus["nashconv"], plus["exploitability"]))
        return
    report = build_report(args.iterations, (1, 10, 100, 1000, 10000, 100000))
    output = json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
    if args.output:
        if args.output.exists() and not args.overwrite: parser.error("output exists; pass --overwrite to replace it")
        args.output.write_text(output + "\n", encoding="utf-8")
    print(f"iterations: {report['iterations']}")
    print(f"Player 0 EV: {report['expected_value']:.10f}; target: {TARGET_VALUE:.10f}; error: {report['value_error']:.10f}")
    print(f"BR0: {report['best_response_values']['br0']:.10f}; BR1-as-u0: {report['best_response_values']['br1_as_u0']:.10f}")
    print(f"NashConv: {report['nashconv']:.10f}; exploitability (NashConv/2): {report['exploitability']:.10f}")
    for checkpoint in report["convergence_checkpoints"]:
        print("checkpoint {iterations}: EV={player0_ev:.10f} error={value_error:.10f} BR0={br0:.10f} "
              "BR1-as-u0={br1_as_u0:.10f} NashConv={nashconv:.10f} exploitability={exploitability:.10f}".format(**checkpoint))

if __name__ == "__main__": main()
