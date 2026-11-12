"""Sanity check (NOT a result): what the gate does to locks built from the stored Slumbot reads.

Reads come from the step-8 parse of benchmark-results/phase-5 slumbot learning logs
(facing-a-bet fold/call/raise rates per street, 1,000 hands, step 7 run).  Opponent-bet
("bet") reads and preflop reads were not parsed, so only facing-a-bet nodes appear.
For each representative spot (uniform ranges, one board per street) the same read is
locked with the gate off and on; we count opponent nodes locked and the weights.
"""
import json
import sys
from types import SimpleNamespace

import numpy as np

from simulation.opponent_model import StatEstimate, confidence_for
from solver.bot import AdaptiveSolverBot, GatedAdaptiveSolverBot
from solver.combos import COMBO_COUNT, combo_index
from solver.tree import StreetState

# street: (n, fold, call, raise) from the step-7 Slumbot learning log
READS = {"flop": (550, 0.56, 0.35, 0.08), "turn": (189, 0.48, 0.44, 0.08), "river": (120, 0.50, 0.38, 0.12)}
SPOTS = {"flop": [("Ts", "7h", "3c"), ("Kd", "9s", "4h")], "turn": [("Ts", "7h", "3c", "2d"), ("Kd", "9s", "4h", "Jc")],
         "river": [("Ts", "7h", "3c", "2d", "8s"), ("Kd", "9s", "4h", "Jc", "2h")]}


def est(n, rate):
    k = round(n * rate)
    return StatEstimate(n, k, k / n, (k + 1) / (n + 2), confidence_for(n))


def profile(scale=1.0):
    streets = {s: {"fold_to_bet": est(int(n * scale), f), "call_vs_bet": est(int(n * scale), c), "raise_vs_bet": est(int(n * scale), r), "bet": est(int(n * scale), 0.3)}
               for s, (n, f, c, r) in READS.items()}
    return SimpleNamespace(statistics={}, street_statistics=streets, hands_observed=1000, classification="unknown")


def main(out):
    hero = combo_index(["Ah", "Qc"])
    rows = []
    for scale in (1.0, 0.25):  # full 1,000-hand reads, and the same rates with a quarter of the sample
        prof = profile(scale)
        for street, boards in SPOTS.items():
            for board in boards:
                row = {"street": street, "board": "".join(board), "sample_scale": scale}
                for name, cls in (("base", AdaptiveSolverBot), ("gated", GatedAdaptiveSolverBot)):
                    bot = cls(seed=0, equity_iterations=50)
                    root = StreetState(street, 1, (0, 0), (19000, 19000), (600, 600), 100)
                    solve = bot._solve(root, board, [np.ones(COMBO_COUNT), np.ones(COMBO_COUNT)], hero, 0, prof)
                    row[name] = {"candidate_locks": solve.candidate_locks or solve.locked_nodes, "locked_nodes": solve.locked_nodes, "seconds": round(solve.seconds, 2)}
                rows.append(row)
                print(row, flush=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
