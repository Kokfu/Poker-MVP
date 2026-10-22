"""Vectorized discounted CFR over whole ranges on a one-street tree.

Player ``p`` holds a range over ``combos[p]`` with weights ``ranges[p]``.
``D[i, j]`` (rows = player 0 combos) is P(win) - P(lose) for 0's combo i
against 1's combo j at a leaf; ``compat`` masks impossible pairs.  A leaf with
matched contributions ``c`` pays player 0 ``c * D`` (the pot is split by
equity); a fold pays the folder's contribution to the other player.

Each iteration does, per traverser: a forward pass for reach probabilities,
two matrix products for every terminal at once, and a backward pass for
counterfactual values and regrets.  Discounting follows DCFR
(alpha=1.5, beta=0, gamma=2), which converges much faster than vanilla CFR.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .combos import COMBO_CARDS
from .exploit import group_target
from .tree import Node, StreetTree

ALPHA, BETA, GAMMA = 1.5, 0.0, 2.0


def fit_frequencies(sigma: np.ndarray, reach: np.ndarray, target: np.ndarray, floor: float = 0.02, rounds: int = 12) -> np.ndarray:
    """Rescale ``sigma`` (actions x combos) per action so the reach-weighted
    aggregate frequencies approach ``target`` while every combo keeps its
    relative preferences (iterative proportional fitting).  A small floor
    lets an action the solver never takes still receive observed mass."""
    total = reach.sum()
    if total <= 0:
        return sigma
    target = np.clip(np.asarray(target, dtype=np.float64), 1e-6, None)
    target = target / target.sum()
    base = (sigma + floor) / (1.0 + floor * len(sigma))
    scale = np.ones(len(sigma))
    fitted = base
    for _ in range(rounds):
        fitted = base * scale[:, None]
        fitted = fitted / fitted.sum(axis=0, keepdims=True)
        aggregate = (fitted * reach).sum(axis=1) / total
        scale = scale * target / np.clip(aggregate, 1e-9, None)
    return fitted


@dataclass
class SolveResult:
    tree: StreetTree
    average: dict[int, np.ndarray]  # decision node -> (actions, combos of its player)
    iterations: int
    exploitability: float | None = None  # chips per deal, averaged over players


class RangeSolver:
    def __init__(self, tree: StreetTree, ranges: tuple[np.ndarray, np.ndarray], d: np.ndarray, compat: np.ndarray,
                 combo_ids: tuple[np.ndarray, np.ndarray] | None = None,
                 locks: dict[int, tuple[float, np.ndarray]] | None = None):
        """``combo_ids`` (global combo indices for each range) enables O(n)
        fold values via card blockers; without it folds use ``compat``.

        ``locks`` maps a decision node to ``(weight, groups)`` (see
        ``solver.exploit``), where groups fix the total frequency of sets of actions:
        that node's player then plays ``(1 - w) * sigma + w * fitted``, where
        ``fitted`` rescales sigma per action until the range-weighted action
        frequencies match the targets (hand ordering is preserved).  This is
        node locking: the other player learns a response to the locked play.
        """
        self.tree = tree
        self.locks = dict(locks or {})
        self.ranges = (np.asarray(ranges[0], dtype=np.float64), np.asarray(ranges[1], dtype=np.float64))
        # Contiguous float32 matrices keep every product a single BLAS call
        # (mixing dtypes or strides would copy an n x n matrix per product).
        win = np.asarray(d * compat, dtype=np.float32)
        weight = np.asarray(compat, dtype=np.float32)
        self.win = (np.ascontiguousarray(win), np.ascontiguousarray(-win.T))
        self.compat = (np.ascontiguousarray(weight), np.ascontiguousarray(weight.T))
        self.sizes = (len(self.ranges[0]), len(self.ranges[1]))
        self.decisions = [node for node in tree.nodes if node.kind == "decision"]
        self.terminals = [node for node in tree.nodes if node.kind != "decision"]
        self.leaves = [n for n in self.terminals if n.kind == "leaf"]
        self.folds = [n for n in self.terminals if n.kind == "fold"]
        self.leaf_scale = np.array([min(n.contribution) for n in self.leaves], dtype=np.float64)
        self.fold_scale = tuple(
            np.array([n.contribution[n.player] if n.player != t else -n.contribution[t] for n in self.folds], dtype=np.float64)
            for t in (0, 1)
        )  # the winner collects exactly what the folder put in
        self.blockers = None
        if combo_ids is not None:
            # Reach of opponent combos compatible with combo (a, b) equals
            # total - reach holding a - reach holding b + reach of (a, b) itself.
            ids = [np.asarray(combo_ids[0]), np.asarray(combo_ids[1])]
            incidence = []
            for p in (0, 1):
                matrix = np.zeros((len(ids[p]), 52), dtype=np.float64)
                matrix[np.arange(len(ids[p]))[:, None], COMBO_CARDS[ids[p]]] = 1.0
                incidence.append(matrix)
            self.blockers = []
            for t in (0, 1):
                o = 1 - t
                position = np.searchsorted(ids[o], ids[t]).clip(0, len(ids[o]) - 1)
                same = ids[o][position] == ids[t]
                self.blockers.append((incidence[o].T.copy(), COMBO_CARDS[ids[t]].astype(np.intp), position, same))
        self.regret = {n.index: np.zeros((len(n.actions), self.sizes[n.player])) for n in self.decisions}
        self.strategy_sum = {n.index: np.zeros((len(n.actions), self.sizes[n.player])) for n in self.decisions}
        self.iterations = 0
        # Precomputed once per tree so the hot loop below never rebuilds a
        # Python list or calls np.stack per node per iteration: children are
        # gathered with one fancy-index instead, and the "no regret yet"
        # uniform strategy is a cached array instead of a fresh np.full_like.
        self._num_nodes = len(tree.nodes)
        self._children = {n.index: np.array(n.children, dtype=np.intp) for n in self.decisions}
        self._uniform = {n.index: np.full((len(n.actions), self.sizes[n.player]), 1.0 / len(n.actions)) for n in self.decisions}
        self._leaf_index = np.array([n.index for n in self.leaves], dtype=np.intp)
        self._fold_index = np.array([n.index for n in self.folds], dtype=np.intp)

    # ------------------------------------------------------------------ core
    def current(self, node: Node) -> np.ndarray:
        positive = np.maximum(self.regret[node.index], 0.0)
        total = positive.sum(axis=0)
        has_total = total > 0
        return np.where(has_total, positive / np.where(has_total, total, 1.0), self._uniform[node.index])

    def average(self, node: Node) -> np.ndarray:
        strategy_sum = self.strategy_sum[node.index]
        total = strategy_sum.sum(axis=0)
        has_total = total > 0
        return np.where(has_total, strategy_sum / np.where(has_total, total, 1.0), self._uniform[node.index])

    def _reaches(self, traverser: int, policy) -> tuple[np.ndarray, np.ndarray]:
        """Reach probabilities for every node, as one array per player (row =
        node index) instead of a dict, so terminal reaches can be gathered
        below with a single fancy-index instead of a per-node Python loop."""
        opponent = 1 - traverser
        own = np.zeros((self._num_nodes, self.sizes[traverser]))
        opp = np.zeros((self._num_nodes, self.sizes[opponent]))
        own[self.tree.root] = self.ranges[traverser]
        opp[self.tree.root] = self.ranges[opponent]
        for node in self.tree.nodes:  # parents precede children
            if node.kind != "decision":
                continue
            sigma = policy(node)
            own_row, opp_row = own[node.index], opp[node.index]
            for action, child in enumerate(node.children):
                if node.player == traverser:
                    own[child] = own_row * sigma[action]
                    opp[child] = opp_row
                else:
                    own[child] = own_row
                    opp[child] = opp_row * sigma[action]
        return own, opp

    def _terminal_values(self, traverser: int, opp: np.ndarray) -> np.ndarray:
        values = np.zeros((self._num_nodes, self.sizes[traverser]))
        if len(self._leaf_index):
            reach = opp[self._leaf_index].T.astype(np.float32)
            product = (self.win[traverser] @ reach) * self.leaf_scale
            values[self._leaf_index] = product.T
        if len(self._fold_index) and self.blockers is not None:
            reach = opp[self._fold_index].T
            card_reach, cards, position, same = self.blockers[traverser]
            by_card = card_reach @ reach  # (52, folds)
            compatible_reach = reach.sum(axis=0) - by_card[cards[:, 0]] - by_card[cards[:, 1]] + reach[position] * same[:, None]
            product = compatible_reach * self.fold_scale[traverser]
            values[self._fold_index] = product.T
        elif len(self._fold_index):
            reach = opp[self._fold_index].T.astype(np.float32)
            product = (self.compat[traverser] @ reach) * self.fold_scale[traverser]
            values[self._fold_index] = product.T
        return values

    def _backward(self, traverser: int, values: np.ndarray, policy, best_response: bool = False) -> np.ndarray:
        for node in reversed(self.decisions):
            children = values[self._children[node.index]]
            if node.player == traverser:
                if best_response:
                    values[node.index] = children.max(axis=0)
                else:
                    sigma = policy(node)
                    values[node.index] = (sigma * children).sum(axis=0)
            else:
                values[node.index] = children.sum(axis=0)
        return values

    def iterate(self) -> None:
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

    def policy(self, base) -> dict[int, np.ndarray]:
        """Strategies for every decision node, with locks applied in tree order."""
        strategies = {node.index: base(node) for node in self.decisions}
        if not self.locks:
            return strategies
        reach = {self.tree.root: (self.ranges[0], self.ranges[1])}
        for node in self.decisions:
            own = reach[node.index][node.player]
            if node.index in self.locks:
                lock = self.locks[node.index]
                weight, groups = lock[0], lock[1]
                strength = lock[2] if len(lock) > 2 else 1.0
                sigma = strategies[node.index]
                target = group_target(sigma, own, groups)
                fitted = fit_frequencies(sigma, own, target)
                if strength < 1.0:
                    # Opponents whose actions do not follow hand strength take
                    # the observed mix with every hand (flat), not just the best.
                    fitted = strength * fitted + (1.0 - strength) * target[:, None]
                strategies[node.index] = (1 - weight) * sigma + weight * fitted
            sigma = strategies[node.index]
            for action, child in enumerate(node.children):
                pair = list(reach[node.index])
                pair[node.player] = pair[node.player] * sigma[action]
                reach[child] = tuple(pair)
        return strategies

    def final_policy(self) -> dict[int, np.ndarray]:
        """Average strategies, with locked nodes showing the locked play."""
        return self.policy(self.average)

    def solve(self, iterations: int, measure: bool = False) -> SolveResult:
        for _ in range(iterations):
            self.iterate()
        return SolveResult(self.tree, self.final_policy(), self.iterations,
                           self.exploitability() if measure else None)

    # ------------------------------------------------------------ diagnostics
    def expected_values(self, policy=None) -> tuple[float, float]:
        """Per-deal EV of each player under ``policy`` (default: average)."""
        policy = policy or self.average
        results = []
        for traverser in (0, 1):
            _, opp = self._reaches(traverser, policy)
            values = self._backward(traverser, self._terminal_values(traverser, opp), policy)
            results.append(float(self.ranges[traverser] @ values[self.tree.root]) / self.deal_mass())
        return results[0], results[1]

    def best_response_values(self, policy=None) -> tuple[float, float]:
        policy = policy or self.average
        results = []
        for traverser in (0, 1):
            _, opp = self._reaches(traverser, policy)
            values = self._backward(traverser, self._terminal_values(traverser, opp), policy, best_response=True)
            results.append(float(self.ranges[traverser] @ values[self.tree.root]) / self.deal_mass())
        return results[0], results[1]

    def deal_mass(self) -> float:
        return float(self.ranges[0] @ self.compat[0] @ self.ranges[1])

    def exploitability(self, policy=None) -> float:
        """Mean best-response gain in chips per deal; zero at equilibrium."""
        br0, br1 = self.best_response_values(policy)
        return (br0 + br1) / 2.0
