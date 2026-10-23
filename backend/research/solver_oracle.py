"""Stage 0 oracle for the later-street-betting design (research only).

Production solves one street at a time and values every checked-down end of a
flop/turn street by equity.  This module solves the *true* two-street game for
a turn spot: the turn betting tree, every possible river card exactly, and a
river betting tree under each non-all-in turn leaf, all with the production
bet menu so that only the leaf model differs.  It then measures how
exploitable the production one-street strategy is in that two-street game.

Nothing here is imported by production code and nothing in ``solver`` is
modified.  Run ``python -m research.solver_oracle --help``.

Conventions follow ``solver.cfr``: values are net chips for the whole hand,
player 0 is the button, and the big blind (player 1) acts first postflop.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import numpy as np

from solver.bot import SolverBot, _full_equity
from solver.cfr import ALPHA, BETA, GAMMA, RangeSolver
from solver.combos import CARDS, CARD_INDEX, COMBO_CARDS
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree

RIVER_CARDS_PER_PAIR = 44  # 52 - 4 board - 4 hole cards


class RiverSubgame(RangeSolver):
    """River game under one turn leaf and one river card.

    ``iterate`` is the production CFR step; it additionally keeps each
    traverser's counterfactual root values so the turn level can use them.
    """

    def __init__(self, *args, shared: "RiverSubgame | None" = None, **kwargs):
        super().__init__(*args, **kwargs)
        if shared is not None:  # same river card: reuse the big matrices instead of holding copies per leaf
            self.win, self.compat, self.blockers = shared.win, shared.compat, shared.blockers
        self.root_values = [np.zeros(self.sizes[0]), np.zeros(self.sizes[1])]

    def reset(self) -> None:
        """Forget all regrets and averages (ranges are set separately)."""
        self.regret = {n.index: np.zeros((len(n.actions), self.sizes[n.player])) for n in self.decisions}
        self.strategy_sum = {n.index: np.zeros((len(n.actions), self.sizes[n.player])) for n in self.decisions}
        self.iterations = 0

    def iterate(self) -> None:  # same arithmetic as RangeSolver.iterate, plus root values
        self.iterations += 1
        t = self.iterations
        positive_discount = t ** ALPHA / (t ** ALPHA + 1)
        negative_discount = t ** BETA / (t ** BETA + 1)
        average_weight = (t / (t + 1)) ** GAMMA
        for traverser in (0, 1):
            strategies = self.policy(self.current)
            own, opp = self._reaches(traverser, lambda node: strategies[node.index])
            values = self._terminal_values(traverser, opp)
            for node in reversed(self.decisions):
                children = values[self._children[node.index]]
                if node.player != traverser:
                    values[node.index] = children.sum(axis=0)
                    continue
                sigma = strategies[node.index]
                value = (sigma * children).sum(axis=0)
                values[node.index] = value
                regret = self.regret[node.index]
                regret *= np.where(regret > 0, positive_discount, negative_discount)
                regret += children - value
                self.strategy_sum[node.index] *= average_weight
                self.strategy_sum[node.index] += own[node.index] * sigma
            self.root_values[traverser] = values[self.tree.root].copy()


@dataclass
class TurnSpot:
    board: tuple[str, ...]  # four cards
    root: StreetState
    ranges: tuple[np.ndarray, np.ndarray]  # public range weights over all 1,326 combos


class TwoStageSolver(RangeSolver):
    """Joint CFR over the turn tree and, under each non-all-in leaf, every river card."""

    def __init__(self, spot: TurnSpot, prune: float = SolverBot.prune, river_menu=POSTFLOP_MENU, fresh: bool = False):
        """``fresh`` refreshes the river values before each traverser pass (exact CFR order, twice the cost);
        the default refreshes once per iteration, which is what the Stage 0 runs use."""
        self.spot = spot
        self.fresh = fresh
        self._in_iterate = False
        live, full_d, full_compat = _full_equity(spot.board, SolverBot.flop_runouts)
        combos = []
        for player in (0, 1):
            weights = spot.ranges[player][live]
            keep = weights > prune * weights.max() if weights.max() > 0 else np.zeros_like(weights, bool)
            combos.append(live[keep])
        rows, cols = np.searchsorted(live, combos[0]), np.searchsorted(live, combos[1])
        tree = StreetTree(spot.root, SolverBot.postflop_menu)
        super().__init__(tree, (spot.ranges[0][combos[0]], spot.ranges[1][combos[1]]),
                         full_d[np.ix_(rows, cols)], full_compat[np.ix_(rows, cols)], combo_ids=(combos[0], combos[1]))
        self.combos = (combos[0], combos[1])
        self.turn_d, self.turn_compat = full_d[np.ix_(rows, cols)], full_compat[np.ix_(rows, cols)]
        self.pot = float(tree.nodes[tree.root].state.pot)
        self.river_leaves = [n for n in self.leaves if 0 not in n.state.stack]
        self.river_cards = [card for card in CARDS if card not in spot.board]
        self.subs: dict[tuple[int, str], RiverSubgame] = {}
        self.keep: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        templates: dict[str, RiverSubgame] = {}
        arrays: dict[str, tuple] = {}
        for card in self.river_cards:
            index = CARD_INDEX[card]
            self.keep[card] = tuple(~np.isin(COMBO_CARDS[self.combos[p]], [index]).any(axis=1) for p in (0, 1))
        for leaf in self.river_leaves:
            river_state = StreetState("river", 1, (0, 0), leaf.state.stack,
                                      (leaf.state.base[0] + leaf.state.commit[0], leaf.state.base[1] + leaf.state.commit[1]),
                                      spot.root.last_full_raise)
            river_tree = StreetTree(river_state, river_menu)
            for card in self.river_cards:
                keep0, keep1 = self.keep[card]
                if not keep0.any() or not keep1.any():
                    continue
                if card not in arrays:
                    board5 = tuple(spot.board) + (card,)
                    live5, d5, compat5 = _full_equity(board5, 0)
                    ids = (self.combos[0][keep0], self.combos[1][keep1])
                    r5, c5 = np.searchsorted(live5, ids[0]), np.searchsorted(live5, ids[1])
                    arrays[card] = (ids, d5[np.ix_(r5, c5)], compat5[np.ix_(r5, c5)])
                ids, d_sub, compat_sub = arrays[card]
                sub = RiverSubgame(river_tree, (np.ones(len(ids[0])), np.ones(len(ids[1]))), d_sub, compat_sub,
                                   combo_ids=ids, shared=templates.get(card))
                templates.setdefault(card, sub)
                self.subs[(leaf.index, card)] = sub
        self._reach: tuple[np.ndarray, np.ndarray] | None = None

    # ---------------------------------------------------------------- river layer
    def _set_sub_ranges(self, reach0: np.ndarray, reach1: np.ndarray) -> list[tuple[int, str]]:
        """Point every river subgame at the turn reaches; returns the live subgame keys."""
        live = []
        for (leaf_index, card), sub in self.subs.items():
            keep0, keep1 = self.keep[card]
            a, b = reach0[leaf_index][keep0], reach1[leaf_index][keep1]
            if a.sum() <= 1e-12 or b.sum() <= 1e-12:
                continue
            sub.ranges = (a, b)
            live.append((leaf_index, card))
        return live

    def _refresh_rivers(self, reach0: np.ndarray, reach1: np.ndarray) -> None:
        self._live = self._set_sub_ranges(reach0, reach1)
        for key in self._live:
            self.subs[key].iterate()

    def _river_leaf_values(self, traverser: int, values: np.ndarray, root_of) -> None:
        for leaf in self.river_leaves:
            values[leaf.index] = 0.0
        for leaf_index, card in self._live:
            keep = self.keep[card][traverser]
            values[leaf_index][keep] += root_of(self.subs[(leaf_index, card)], traverser) / RIVER_CARDS_PER_PAIR

    # ----------------------------------------------------------------- overrides
    def _terminal_values(self, traverser: int, opp: np.ndarray) -> np.ndarray:
        values = super()._terminal_values(traverser, opp)
        self._river_leaf_values(traverser, values, lambda sub, t: sub.root_values[t])
        return values

    def _reaches(self, traverser: int, policy):
        own, opp = super()._reaches(traverser, policy)
        if self.fresh and self._in_iterate:
            self._refresh_rivers(*((own, opp) if traverser == 0 else (opp, own)))
        return own, opp

    def iterate(self) -> None:
        if self.fresh:
            self._in_iterate = True
            try:
                super().iterate()
            finally:
                self._in_iterate = False
            return
        strategies = self.policy(self.current)
        reach0, reach1 = self._reaches(0, lambda node: strategies[node.index])
        self._refresh_rivers(reach0, reach1)
        super().iterate()

    # ----------------------------------------------------------------- evaluation
    def solve_rivers_for(self, turn_policy: dict[int, np.ndarray], iterations: int) -> None:
        """Fix the turn strategy and solve every river subgame against the resulting ranges."""
        reach0, reach1 = self._reaches(0, lambda node: turn_policy[node.index])
        live = self._set_sub_ranges(reach0, reach1)
        for key in live:
            sub = self.subs[key]
            sub.reset()
            for _ in range(iterations):
                sub.iterate()

    def profile_exploitability(self, turn_policy: dict[int, np.ndarray]) -> float:
        """Mean best-response gain of the fixed profile (turn policy + stored river averages), in chips per deal.

        River strategies are each subgame's current average policy; call
        ``solve_rivers_for`` first for an arbitrary turn policy.
        """
        reach0, reach1 = self._reaches(0, lambda node: turn_policy[node.index])
        self._live = self._set_sub_ranges(reach0, reach1)
        river_policy = {key: self.subs[key].final_policy() for key in self._live}
        gains = []
        for traverser in (0, 1):
            _, opp = self._reaches(traverser, lambda node: turn_policy[node.index])
            values = RangeSolver._terminal_values(self, traverser, opp)
            for leaf in self.river_leaves:
                values[leaf.index] = 0.0
            for key in self._live:
                sub = self.subs[key]
                policy = river_policy[key]
                _, sub_opp = sub._reaches(traverser, lambda node, p=policy: p[node.index])
                sub_values = sub._backward(traverser, sub._terminal_values(traverser, sub_opp), lambda node, p=policy: p[node.index], best_response=True)
                values[key[0]][self.keep[key[1]][traverser]] += sub_values[sub.tree.root] / RIVER_CARDS_PER_PAIR
            self._backward(traverser, values, lambda node: turn_policy[node.index], best_response=True)
            gains.append(float(self.ranges[traverser] @ values[self.tree.root]) / self.deal_mass())
        return (gains[0] + gains[1]) / 2.0


# ------------------------------------------------------------------- one spot
def _root_action_mix(solver: RangeSolver, policy: dict[int, np.ndarray]) -> np.ndarray:
    """Range-weighted turn root action frequencies of the player to act."""
    root = solver.tree.nodes[solver.tree.root]
    weights = solver.ranges[root.player]
    return (policy[root.index] * weights).sum(axis=1) / weights.sum()


def analyse_spot(spot: TurnSpot, oracle_iterations: int = 150, production_iterations: int = 70, river_iterations: int = 80) -> dict[str, Any]:
    """Compare the production one-street turn strategy with the two-street oracle on one spot."""
    started = time.perf_counter()
    solver = TwoStageSolver(spot)
    root = solver.tree.nodes[solver.tree.root]

    # Production: one-street solve (showdown-equity leaves), then rivers solved against its ranges.
    production = RangeSolver(solver.tree, solver.ranges, solver.turn_d, solver.turn_compat, combo_ids=solver.combos)
    production_policy = production.solve(production_iterations).average
    solver.solve_rivers_for(production_policy, river_iterations)
    production_gap = solver.profile_exploitability(production_policy)

    # Oracle: joint solve; evaluate its own average turn strategy with its own river averages.
    for sub in solver.subs.values():
        sub.reset()
    for _ in range(oracle_iterations):
        solver.iterate()
    oracle_policy = solver.final_policy()
    oracle_gap = solver.profile_exploitability(oracle_policy)

    mix_p, mix_o = _root_action_mix(solver, production_policy), _root_action_mix(solver, oracle_policy)
    weights = solver.ranges[root.player]
    per_combo = 0.5 * np.abs(production_policy[root.index] - oracle_policy[root.index]).sum(axis=0)  # total variation
    return {
        "pot": solver.pot, "ranges": [int(len(c)) for c in solver.combos], "turn_nodes": len(solver.tree.nodes),
        "river_leaves": len(solver.river_leaves), "river_subgames": len(solver.subs),
        "production_gap": production_gap, "oracle_gap": oracle_gap,
        "production_gap_pct_pot": 100.0 * production_gap / solver.pot,
        "oracle_gap_pct_pot": 100.0 * oracle_gap / solver.pot,
        "extra_gap_pct_pot": 100.0 * (production_gap - oracle_gap) / solver.pot,
        "root_labels": list(root.labels), "root_mix_production": [round(float(x), 4) for x in mix_p],
        "root_mix_oracle": [round(float(x), 4) for x in mix_o],
        "root_strategy_distance": float((per_combo * weights).sum() / weights.sum()),
        "seconds": time.perf_counter() - started,
    }


# --------------------------------------------------------------- spot capture
class _Captured(BaseException):
    """Raised inside a hand to stop it as soon as the turn spot is recorded."""


class CapturingBot(SolverBot):
    """SolverBot that records the public ranges at the root of the first turn it reaches."""
    spot: TurnSpot | None = None

    def _street_solve(self, key, root_state, board, ranges, hero_combo, hero, profile=None):
        if root_state.street == "turn":
            self.spot = TurnSpot(tuple(board), root_state, (np.array(ranges[0], dtype=float), np.array(ranges[1], dtype=float)))
            raise _Captured
        return super()._street_solve(key, root_state, board, ranges, hero_combo, hero, profile)


CAPTURE_OPPONENTS = ("equity", "expert", "aggressive", "tight", "solver")


def capture_spot(seed: int) -> TurnSpot | None:
    """Play one hand (stacks 100 bb, blinds 50/100) and return the first turn spot the solver reaches, if any."""
    from simulation.bots import BOT_TYPES
    from simulation.engine import HandEngine

    bot = CapturingBot(seed=seed)
    opponent = BOT_TYPES[CAPTURE_OPPONENTS[seed % len(CAPTURE_OPPONENTS)]](seed=seed + 1, equity_iterations=200)
    first, second = (bot, opponent) if seed % 2 == 0 else (opponent, bot)
    engine = HandEngine(first, second, starting_stacks={"a": 10_000, "b": 10_000}, bb=100, small_blind=50,
                        seed=seed, simulation_seed=seed, button="a", hand_id=f"oracle-{seed}")
    try:
        engine.play()
    except _Captured:
        pass
    spot = bot.spot
    if spot is None or 0 in spot.root.stack:
        return None
    return spot


def spot_to_json(seed: int, spot: TurnSpot) -> dict[str, Any]:
    root = spot.root
    return {"seed": seed, "board": list(spot.board),
            "root": {"street": root.street, "to_act": root.to_act, "commit": list(root.commit), "stack": list(root.stack),
                     "base": list(root.base), "last_full_raise": root.last_full_raise, "acted": list(root.acted), "depth": root.depth},
            "ranges": [[round(float(x), 6) for x in r] for r in spot.ranges]}


def spot_from_json(row: dict[str, Any]) -> TurnSpot:
    r = row["root"]
    root = StreetState(r["street"], r["to_act"], tuple(r["commit"]), tuple(r["stack"]), tuple(r["base"]), r["last_full_raise"], tuple(r["acted"]), r["depth"])
    return TurnSpot(tuple(row["board"]), root, (np.array(row["ranges"][0]), np.array(row["ranges"][1])))


def _capture_job(seed: int):
    spot = capture_spot(seed)
    return seed, None if spot is None else spot_to_json(seed, spot)


def _analyse_job(args):
    row, oracle_iterations = args
    result = analyse_spot(spot_from_json(row), oracle_iterations=oracle_iterations)
    return {"seed": row["seed"], "board": row["board"], **result}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from multiprocessing import Pool
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Stage 0 oracle: capture turn spots and measure the one-street model's extended-game gap")
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--spots", type=int, default=200)
    cap.add_argument("--seed-base", type=int, default=20_000)
    cap.add_argument("--workers", type=int, default=6)
    cap.add_argument("--output", required=True)
    run = sub.add_parser("run")
    run.add_argument("--spots-file", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--workers", type=int, default=6)
    run.add_argument("--oracle-iterations", type=int, default=150)
    run.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.command == "capture":
        out = Path(args.output)
        found = tried = 0
        seed = args.seed_base
        with Pool(args.workers) as pool, out.open("a", encoding="utf-8") as handle:
            while found < args.spots:
                batch = list(range(seed, seed + args.workers * 4))
                seed += len(batch)
                for used_seed, row in pool.imap(_capture_job, batch):  # imap keeps seed order, so the first N spots are deterministic
                    tried += 1
                    if row is not None and found < args.spots:
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
                        handle.flush()
                        found += 1
        print(json.dumps({"spots": found, "seeds_tried": tried, "last_seed": seed - 1}))
        return 0

    rows = [json.loads(line) for line in Path(args.spots_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    done = set()
    out = Path(args.output)
    if out.exists():
        done = {json.loads(line)["seed"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    rows = [row for row in rows if row["seed"] not in done][: args.limit]
    with Pool(args.workers, maxtasksperchild=1) as pool, out.open("a", encoding="utf-8") as handle:
        for result in pool.imap_unordered(_analyse_job, [(row, args.oracle_iterations) for row in rows]):
            handle.write(json.dumps(result, sort_keys=True) + "\n")
            handle.flush()
            print(f"seed {result['seed']}: production {result['production_gap_pct_pot']:.2f}% oracle {result['oracle_gap_pct_pot']:.2f}% pot ({result['seconds']:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
