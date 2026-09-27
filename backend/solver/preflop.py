"""Offline heads-up preflop charts.

1. ``build_class_equity`` estimates all-in equity for every pair of the 169
   starting-hand classes (seeded Monte Carlo over boards, card removal exact).
2. ``solve_chart`` runs range CFR on the preflop tree (limp, 2.5x open,
   3x 3-bet, 2.3x 4-bet, all-in) for one stack depth.  Seeing a flop is a leaf
   paid by raw equity, a documented simplification (no postflop realization).
3. Charts for several depths are stored in ``solver/data`` and loaded at
   runtime; the bot uses the depth nearest to the effective stack.

Build (from ``backend``)::

    python -m solver.preflop build --boards 10000 --iterations 1500
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path
import time

import numpy as np

from .cfr import RangeSolver
from .combos import CLASS_COMBO_COUNT, COMBO_CLASS, COMBO_COUNT, HAND_CLASSES
from .equity import equity_matrix
from .tree import PREFLOP_MENU, StreetState, StreetTree

DATA_DIR = Path(__file__).resolve().parent / "data"
EQUITY_FILE = DATA_DIR / "preflop_class_equity.npz"
CHART_FILE = DATA_DIR / "preflop_charts.npz"
CHART_BB = 100  # charts are solved in chips with a 100-chip big blind
STACK_DEPTHS_BB = (15, 30, 60, 100, 200)
CHART_VERSION = "1.0"


def build_class_equity(boards: int) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(class_d, class_w)`` for the 169 x 169 class game.

    ``class_w[a, b]`` is the share of combo pairs from classes a and b that
    are card-compatible, and ``class_d`` their average P(win) - P(lose).
    Because preflop strategies are identical across suits, solving the class
    game with combo-count ranges is exactly the combo game.
    """
    everything = np.arange(COMBO_COUNT)
    d, compat = equity_matrix([], everything, everything, samples=boards)
    onehot = np.zeros((COMBO_COUNT, len(HAND_CLASSES)))
    onehot[np.arange(COMBO_COUNT), COMBO_CLASS] = 1.0
    pairs = np.outer(CLASS_COMBO_COUNT, CLASS_COMBO_COUNT).astype(float)
    class_w = (onehot.T @ compat.astype(float) @ onehot) / pairs
    class_d = (onehot.T @ (d * compat) @ onehot) / np.where(class_w > 0, class_w * pairs, 1.0)
    return class_d, class_w


@lru_cache(maxsize=1)
def load_class_equity() -> tuple[np.ndarray, np.ndarray]:
    with np.load(EQUITY_FILE) as data:
        return data["class_d"], data["class_w"]


def chart_root(depth_bb: int) -> StreetState:
    stack = depth_bb * CHART_BB
    small = CHART_BB // 2
    # Player 0 is the button/small blind and acts first preflop.
    return StreetState("preflop", 0, (small, CHART_BB), (stack - small, stack - CHART_BB), (0, 0), CHART_BB)


def chart_tree(depth_bb: int) -> StreetTree:
    return StreetTree(chart_root(depth_bb), PREFLOP_MENU)


def solve_chart(depth_bb: int, iterations: int, class_equity: tuple[np.ndarray, np.ndarray] | None = None):
    class_d, class_w = load_class_equity() if class_equity is None else class_equity
    counts = CLASS_COMBO_COUNT.astype(float)
    solver = RangeSolver(chart_tree(depth_bb), (counts, counts), class_d, class_w)
    return solver, solver.solve(iterations, measure=True)


def build(boards: int, iterations: int, depths=STACK_DEPTHS_BB) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    class_d, class_w = build_class_equity(boards)
    np.savez_compressed(EQUITY_FILE, class_d=class_d, class_w=class_w, boards=boards)
    report = {"chart_version": CHART_VERSION, "equity_boards": boards, "equity_seconds": time.perf_counter() - started, "depths": {}}
    arrays = {}
    for depth in depths:
        started = time.perf_counter()
        solver, result = solve_chart(depth, iterations, (class_d, class_w))
        tree = result.tree
        for index, strategy in result.average.items():
            arrays[f"d{depth}_n{index}"] = strategy.astype(np.float32)
        ev = solver.expected_values()
        report["depths"][str(depth)] = {
            "iterations": iterations,
            "nodes": len(tree.nodes),
            "labels": {str(n.index): n.labels for n in tree.nodes if n.kind == "decision"},
            "exploitability_chips_per_hand": result.exploitability,
            "exploitability_mbb_per_hand": 1000 * result.exploitability / CHART_BB,
            "button_ev_bb": ev[0] / CHART_BB,
            "seconds": time.perf_counter() - started,
        }
    np.savez_compressed(CHART_FILE, metadata=json.dumps(report), **arrays)
    return report


class PreflopCharts:
    """Runtime access to stored charts; trees are rebuilt deterministically."""

    def __init__(self, path: Path = CHART_FILE):
        with np.load(path) as data:
            self.metadata = json.loads(str(data["metadata"]))
            self.arrays = {key: data[key] for key in data.files if key != "metadata"}
        self.depths = tuple(int(depth) for depth in self.metadata["depths"])
        self.trees = {depth: chart_tree(depth) for depth in self.depths}
        for depth, tree in self.trees.items():
            stored = self.metadata["depths"][str(depth)]["labels"]
            built = {str(n.index): n.labels for n in tree.nodes if n.kind == "decision"}
            if stored != built:
                raise ValueError(f"preflop chart for {depth}bb does not match the current tree")

    def nearest_depth(self, effective_bb: float) -> int:
        return min(self.depths, key=lambda depth: abs(np.log(depth) - np.log(max(effective_bb, 1.0))))

    def strategy(self, depth: int, node_index: int) -> np.ndarray:
        """(actions, 1326) combo-level strategy expanded from the class chart."""
        return self.arrays[f"d{depth}_n{node_index}"][:, COMBO_CLASS]


@lru_cache(maxsize=1)
def load_charts() -> PreflopCharts:
    return PreflopCharts()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build heads-up preflop charts")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--boards", type=int, default=10_000)
    build_parser.add_argument("--iterations", type=int, default=1_500)
    build_parser.add_argument("--depths", type=int, nargs="+", default=list(STACK_DEPTHS_BB))
    args = parser.parse_args(argv)
    report = build(args.boards, args.iterations, tuple(args.depths))
    print(json.dumps({k: v for k, v in report.items() if k != "depths"} | {"depths": {d: {k: v for k, v in info.items() if k != "labels"} for d, info in report["depths"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
