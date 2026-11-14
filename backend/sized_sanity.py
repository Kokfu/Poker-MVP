"""Sanity check (NOT a result): how many opponent nodes `sized` locks vs base on the stored Slumbot reads.

Per-street facing-a-bet reads are the step 9 gate sanity inputs; the bucket cells are the step 13
feasibility counts (benchmark-results/step-13-feasibility.txt) summed over flop/turn/river.
Spots are representative (uniform ranges, two boards per street), one solve each, so this says
nothing about strength; it only counts locked nodes and timing.
"""
import json
import sys
from types import SimpleNamespace

import numpy as np

from gate_sanity import SPOTS, profile
from simulation.opponent_model import SizedStats
from solver.bot import AdaptiveSolverBot, SizedAdaptiveSolverBot
from solver.combos import COMBO_COUNT, combo_index
from solver.tree import StreetState

# postflop pooled (n, fold, call, raise), Slumbot, six logs, our bets/raises by size bucket
CELLS = {"<=0.5": (2177, 759, 1143, 275), "0.5-1.0": (518, 281, 194, 43), ">1.0": (819, 756, 63, 0)}


def main(out):
    hero = combo_index(["Ah", "Qc"])
    rows = []
    for scale in (1.0, 0.1, 0.005):  # full sample, a tenth (about 100 hands), a two-hundredth (about 5 hands: two buckets thin)
        prof = profile(1.0)  # per-street reads fixed; only the bucket cells shrink
        prof.sized_statistics = {b: SizedStats(*(max(int(v * scale), 0) for v in cell)) for b, cell in CELLS.items()}
        for street, boards in SPOTS.items():
            for board in boards:
                row = {"street": street, "board": "".join(board), "sample_scale": scale, "cells": {b: c.opportunities for b, c in prof.sized_statistics.items()}}
                for name, cls in (("base", AdaptiveSolverBot), ("sized", SizedAdaptiveSolverBot)):
                    bot = cls(seed=0, equity_iterations=50)
                    root = StreetState(street, 1, (0, 0), (19000, 19000), (600, 600), 100)
                    solve = bot._solve(root, board, [np.ones(COMBO_COUNT), np.ones(COMBO_COUNT)], hero, 0, prof)
                    row[name] = {"locked_nodes": solve.locked_nodes, "seconds": round(solve.seconds, 2)}
                    if name == "sized":
                        row[name]["sized_info"] = solve.sized_info
                rows.append(row)
                print(row, flush=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
