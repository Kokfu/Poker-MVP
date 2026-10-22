"""``SolverBot``: preflop charts plus real-time postflop range re-solving.

At every decision the bot rebuilds the hand from the public action history in
its ``DecisionState`` (never from engine internals):

* Both players' public ranges start uniform.  Each preflop action multiplies
  the actor's range by the chart probability of that action; each postflop
  action multiplies it by the strategy of a solve of that street from the
  street's start.  Off-tree sizes map to the nearest tree size (log scale).
* For its own decision the bot solves the current street from the *actual*
  current state (exact pot, stacks, and the opponent's real bet size) with
  both public ranges, then samples its combo's mixed strategy with a seeded
  RNG that is independent of the deck and of every other RNG.
* River leaves are exact showdowns; flop/turn leaves are equity over the
  remaining runouts (a documented approximation of later-street play).

Any unexpected state falls back to ``ExpertRuleBot`` and is counted.

``AdaptiveSolverBot`` (registry name ``solver_adaptive``) additionally reads
the public ``OpponentModel`` profile supplied with each observation and node
locks the opponent toward its observed frequencies (``solver.exploit``):
postflop street solves, range updates, and — when preflop reads are
confident — a re-solve of the preflop chart game all respond to that play.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field, replace
from hashlib import sha256
import math
import random
import time
from typing import Any

import eval7
import numpy as np

from simulation.actions import Action
from simulation.bots import PokerBot
from simulation.expert_bot import ExpertRuleBot

from .cfr import RangeSolver
from .combos import CLASS_COMBO_COUNT, COMBO_CLASS, COMBO_COUNT, COMBOS, HAND_CLASSES, card_mask, combo_index
from .equity import equity_matrix, rank_vector
from .exploit import locks_key, tree_locks
from .showdown import ShowdownModel
from .preflop import CHART_BB, PreflopCharts, load_charts, load_class_equity
from .tree import POSTFLOP_MENU, SizeMenu, StreetState, StreetTree

STREETS = ("preflop", "flop", "turn", "river")
_EQUITY_CACHE: OrderedDict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]] = OrderedDict()
# Session play touches many distinct boards; 6 entries thrashed within a few
# hands and forced a full equity_matrix recompute on every new board even
# when the same board recurs later in the same session. Worst case (a
# river/turn board with no combos pruned) is ~6MB/entry (float32 d + bool
# compat at up to ~1,081 live combos), so 12 entries stays well under 75MB.
_EQUITY_CACHE_SIZE = 12
_PREFLOP_CACHE: OrderedDict[tuple, dict[int, np.ndarray]] = OrderedDict()
_PREFLOP_CACHE_SIZE = 128
PREFLOP_LOCKED_ITERATIONS = 250


class ReplayError(ValueError):
    """The public history cannot be reconstructed consistently."""


@dataclass
class Step:
    street: str
    before: StreetState
    player: int  # 0 = button/small blind, 1 = big blind
    kind: str
    target: int | None


@dataclass
class Replay:
    steps: list[Step]
    streets: dict[str, StreetState]  # state at the start of each street reached
    current: StreetState
    street: str
    start_stacks: tuple[int, int]


def _advance(state: StreetState, kind: str, target: int | None) -> tuple[StreetState, bool]:
    """Apply one public action; returns (new state, street closed)."""
    p, o = state.to_act, 1 - state.to_act
    commit, stack, acted = list(state.commit), list(state.stack), list(state.acted)
    acted[p] = True
    if kind == "check":
        return replace(state, acted=tuple(acted), to_act=o), acted[o]
    if kind == "call":
        amount = min(state.highest - commit[p], stack[p])
        commit[p] += amount
        stack[p] -= amount
        closed = acted[o] or stack[p] == 0 or stack[o] == 0
        return replace(state, commit=tuple(commit), stack=tuple(stack), acted=tuple(acted), to_act=o), closed
    if kind in ("bet", "raise", "all_in"):
        if kind == "all_in" or target is None:
            target = commit[p] + stack[p]
        if target <= state.highest and kind == "all_in":
            # An all-in for less than a call behaves as a call.
            stack[p] -= target - commit[p]
            commit[p] = target
            return replace(state, commit=tuple(commit), stack=tuple(stack), acted=tuple(acted), to_act=o), True
        raise_size = target - state.highest
        full = raise_size >= state.last_full_raise
        stack[p] -= target - commit[p]
        commit[p] = target
        if stack[p] < 0:
            raise ReplayError("replayed target exceeds stack")
        return replace(state, commit=tuple(commit), stack=tuple(stack), acted=tuple(acted), to_act=o,
                       last_full_raise=raise_size if full else state.last_full_raise, depth=state.depth + 1), False
    raise ReplayError(f"unexpected action {kind}")


def replay_hand(ds) -> Replay:
    """Reconstruct street structure and stacks from a DecisionState."""
    hero = 0 if ds.acting_player == ds.button_player else 1
    player_index = {ds.button_player: 0, ds.big_blind_player: 1}
    actions = [(player_index[a.player], a.action, a.amount) for a in ds.hand_actions]
    sb, bb = ds.small_blind, ds.big_blind

    def run(start_stacks: tuple[int, int]) -> Replay:
        state = StreetState("preflop", 0, (sb, bb), (start_stacks[0] - sb, start_stacks[1] - bb), (0, 0), bb)
        streets, steps, street_index = {"preflop": state}, [], 0
        for player, kind, amount in actions:
            if player != state.to_act:
                raise ReplayError("actor order does not match betting rules")
            steps.append(Step(STREETS[street_index], state, player, kind, amount))
            if kind == "fold":
                raise ReplayError("hand already folded")
            state, closed = _advance(state, kind, amount)
            if closed:
                if street_index == 3 or 0 in state.stack:
                    raise ReplayError("no decision can follow a closed river or all-in")
                street_index += 1
                base = (state.base[0] + state.commit[0], state.base[1] + state.commit[1])
                state = StreetState(STREETS[street_index], 1, (0, 0), state.stack, base, bb)
                streets[STREETS[street_index]] = state
        return Replay(steps, streets, state, STREETS[street_index], start_stacks)

    # First pass with ample stacks recovers contributions; second pass is exact.
    probe = run((10**12, 10**12))
    spent = [probe.current.base[i] + probe.current.commit[i] for i in (0, 1)]
    stacks_now = {hero: ds.hero_stack, 1 - hero: ds.opponent_stack}
    replay = run((stacks_now[0] + spent[0], stacks_now[1] + spent[1]))
    now = replay.current
    if (replay.street != ds.street or now.to_act != hero or now.commit[hero] != ds.hero_street_commitment
            or now.commit[1 - hero] != ds.opponent_street_commitment or now.pot != ds.pot):
        raise ReplayError("replay does not match the observed state")
    return replay


def _log_distance(a: float, b: float) -> float:
    return abs(math.log(max(a, 1e-9)) - math.log(max(b, 1e-9)))


def map_action(tree: StreetTree, node_index: int, kind: str, target: int | None, scale: float = 1.0) -> int:
    """Index of the tree action closest to an actual (kind, target)."""
    node = tree.nodes[node_index]
    labels = node.labels
    if kind in ("fold", "check", "call"):
        if kind in labels:
            return labels.index(kind)
        if kind == "check" and "call" in labels:
            return labels.index("call")
        if kind == "call" and "check" in labels:
            return labels.index("check")
        raise ReplayError(f"{kind} is not available at node {node_index}")
    aggressive = [i for i, (k, _) in enumerate(node.actions) if k in ("bet", "raise", "all_in")]
    if not aggressive:
        # The tree ends aggression here (e.g. facing all-in); treat as a call.
        return labels.index("call") if "call" in labels else labels.index("check")
    if kind == "all_in" and "all_in" in labels:
        return labels.index("all_in")
    scaled = (target or 0) * scale
    return min(aggressive, key=lambda i: _log_distance(node.actions[i][1], scaled))


def _full_equity(board: tuple[str, ...], flop_runouts: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = (board, flop_runouts)
    if key in _EQUITY_CACHE:
        _EQUITY_CACHE.move_to_end(key)
        return _EQUITY_CACHE[key]
    live = np.where(~card_mask(board))[0]
    d, compat = equity_matrix(list(board), live, live, samples=flop_runouts if len(board) == 3 else None)
    _EQUITY_CACHE[key] = (live, d.astype(np.float32), compat)
    if len(_EQUITY_CACHE) > _EQUITY_CACHE_SIZE:
        _EQUITY_CACHE.popitem(last=False)
    return _EQUITY_CACHE[key]


@dataclass
class StreetSolve:
    tree: StreetTree
    combos: tuple[np.ndarray, np.ndarray]
    average: dict[int, np.ndarray]
    exploitability: float | None
    seconds: float
    locked_nodes: int = 0


@dataclass
class _HandMemory:
    key: tuple
    street_solves: dict[tuple, StreetSolve] = field(default_factory=dict)


class SolverBot(PokerBot):
    uses_range_equity = False
    # Measured on 700-combo turn spots: 60 DCFR iterations leave under 1% of
    # the pot exploitable inside the abstraction, 100 iterations about 0.3%.
    exploit = False
    lock_weighting = "confidence"  # or "evidence" (see solver.exploit._weight)
    pool_streets = False  # partial pooling of postflop reads across streets
    iterations = {"flop": 60, "turn": 70, "river": 80}
    flop_runouts = 30
    prune = 5e-3
    postflop_menu: SizeMenu = POSTFLOP_MENU

    def __init__(self, seed: int | None = None, equity_iterations: int = 1000, charts: PreflopCharts | None = None):
        super().__init__(seed, equity_iterations)
        self.seed_base = 0 if seed is None else seed
        self.charts = charts or load_charts()
        self.fallback = ExpertRuleBot(seed, equity_iterations)
        self.memory: _HandMemory | None = None
        self.decision_count = self.fallback_count = self.solve_count = 0
        self.last_explanation: dict[str, Any] | None = None
        self.decision_trace: list[dict[str, Any]] = []
        self.showdown_model = ShowdownModel()

    def observe_completed_hand(self, history, seat: str) -> None:
        """Post-hand public evidence (showdown reveals) for strength modelling."""
        if self.exploit:
            self.showdown_model.observe(history, "b" if seat == "a" else "a")

    def _strength_correlation(self) -> dict[str, float]:
        return {group: self.showdown_model.correlation(group) for group in ("aggressive", "call")}

    # ------------------------------------------------------------- interface
    def decide(self, observation) -> Action:
        return self.fallback.decide(observation)

    def decide_decision(self, observation) -> Action:
        self.decision_count += 1
        ds = observation.decision_state
        profile = getattr(observation, "opponent_profile", None) if self.exploit else None
        try:
            action, explanation = self._decide(ds, profile)
        except (ReplayError, ValueError, KeyError, IndexError, FloatingPointError) as error:
            self.fallback_count += 1
            action = self.fallback.decide_decision(observation)
            explanation = {"source": "fallback", "reason": f"{type(error).__name__}: {error}"}
        self.last_explanation = explanation
        self.decision_trace.append({"hand_number": ds.hand_number, "street": ds.street, "action": action.type, "target": action.amount, **{k: v for k, v in explanation.items() if k in ("source", "reason", "probabilities", "solve_seconds")}})
        return action


    # ---------------------------------------------------------------- engine
    def _decide(self, ds, profile=None) -> tuple[Action, dict[str, Any]]:
        key = (ds.match_id, ds.hand_id, ds.hand_number)
        if self.memory is None or self.memory.key != key:
            self.memory = _HandMemory(key)
        replay = replay_hand(ds)
        hero = replay.current.to_act
        hero_combo = combo_index(ds.hole_cards)
        ranges = [np.ones(COMBO_COUNT), np.ones(COMBO_COUNT)]
        depth = self.charts.nearest_depth(min(replay.start_stacks) / ds.big_blind)
        scale = CHART_BB / ds.big_blind

        opponent = 1 - hero
        exploit_info = self._profile_summary(profile)

        # Preflop: walk the chart tree, updating ranges with the preflop policy
        # (the stored chart, or a re-solve against confident opponent reads).
        chart_tree = self.charts.trees[depth]
        preflop_locks = tree_locks(chart_tree, opponent, "preflop", profile, self._strength_correlation(), self.lock_weighting, self.pool_streets) if profile is not None else {}
        policy = self._preflop_policy(depth, opponent, preflop_locks)
        node = chart_tree.root
        preflop_steps = [s for s in replay.steps if s.street == "preflop"]
        for step in preflop_steps:
            if chart_tree.nodes[node].kind != "decision":
                raise ReplayError("preflop history left the chart tree")
            choice = map_action(chart_tree, node, step.kind, step.target, scale)
            ranges[step.player] = ranges[step.player] * policy(node)[choice]
            node = chart_tree.nodes[node].children[choice]
        if replay.street == "preflop":
            if chart_tree.nodes[node].kind != "decision":
                raise ReplayError("no chart decision at the current preflop node")
            probabilities = policy(node)[:, hero_combo]
            chart_node = chart_tree.nodes[node]
            choice = self._sample(ds, probabilities)
            action = self._concrete_preflop(ds, chart_node, choice, scale)
            return action, {"source": "preflop_chart" if not preflop_locks else "preflop_exploit", "depth_bb": depth, "labels": chart_node.labels,
                            "probabilities": [round(float(p), 4) for p in probabilities], "chosen": chart_node.labels[choice],
                            "exploit": {**exploit_info, "locked_nodes": len(preflop_locks)},
                            **self._range_report((), hero_combo, ranges[opponent])}

        # Postflop streets already completed, then the current street.
        board: tuple[str, ...] = ()
        for street in STREETS[1:STREETS.index(replay.street) + 1]:
            board = tuple(ds.board_cards[:{"flop": 3, "turn": 4, "river": 5}[street]])
            blocked = card_mask(board)
            for p in (0, 1):
                ranges[p] = np.where(blocked, 0.0, ranges[p])
            steps = [s for s in replay.steps if s.street == street]
            root_state = replay.streets[street]
            solve = self._street_solve((street, board, len(replay.steps) - len(steps)), root_state, board, ranges, hero_combo, hero, profile)
            node = solve.tree.root
            on_tree = True
            for step in steps:
                tree_node = solve.tree.nodes[node]
                if tree_node.kind != "decision":
                    raise ReplayError("postflop history left the street tree")
                choice = map_action(solve.tree, node, step.kind, step.target)
                kind, target = tree_node.actions[choice]
                on_tree &= kind == step.kind or (step.kind in ("check", "call") and kind in ("check", "call"))
                on_tree &= target is None or step.target is None or target == step.target
                ranges[step.player] = self._apply_strategy(ranges[step.player], solve, node, choice)
                node = tree_node.children[choice]
            if street != replay.street:
                continue
            if not on_tree or solve.tree.nodes[node].kind != "decision":
                solve = self._solve(replay.current, board, ranges, hero_combo, hero, profile)
                node = solve.tree.root
            tree_node = solve.tree.nodes[node]
            position = int(np.searchsorted(solve.combos[hero], hero_combo))
            probabilities = solve.average[node][:, position]
            choice = self._sample(ds, probabilities)
            action = self._concrete_postflop(ds, tree_node.actions[choice])
            return action, {"source": "postflop_solve", "street": street, "labels": tree_node.labels,
                            "probabilities": [round(float(p), 4) for p in probabilities], "chosen": tree_node.labels[choice],
                            "range_sizes": [int(len(c)) for c in solve.combos], "solve_seconds": round(solve.seconds, 3),
                            "exploitability": solve.exploitability, "resolved_from_current_state": not on_tree,
                            "exploit": {**exploit_info, "locked_nodes": solve.locked_nodes},
                            **self._range_report(board, hero_combo, ranges[opponent])}
        raise ReplayError("unreachable street")

    def _street_solve(self, key, root_state, board, ranges, hero_combo, hero, profile=None) -> StreetSolve:
        cached = self.memory.street_solves.get(key)
        if cached is None:
            cached = self._solve(root_state, board, ranges, hero_combo, hero, profile)
            self.memory.street_solves[key] = cached
        return cached

    def _solve(self, root_state: StreetState, board, ranges, hero_combo, hero, profile=None) -> StreetSolve:
        started = time.perf_counter()
        self.solve_count += 1
        live, full_d, full_compat = _full_equity(board, self.flop_runouts)
        combos = []
        for p in (0, 1):
            weights = ranges[p][live]
            keep = weights > self.prune * weights.max() if weights.max() > 0 else np.zeros_like(weights, bool)
            if p == hero:
                keep |= live == hero_combo
            combos.append(live[keep])
        if not len(combos[0]) or not len(combos[1]):
            raise ReplayError("empty range")
        rows, cols = np.searchsorted(live, combos[0]), np.searchsorted(live, combos[1])
        d = full_d[np.ix_(rows, cols)]
        compat = full_compat[np.ix_(rows, cols)]
        tree = StreetTree(root_state, self.postflop_menu)
        locks = tree_locks(tree, 1 - hero, root_state.street, profile, self._strength_correlation(), self.lock_weighting, self.pool_streets) if profile is not None else {}
        solver = RangeSolver(tree, (ranges[0][combos[0]], ranges[1][combos[1]]), d, compat, combo_ids=(combos[0], combos[1]), locks=locks)
        result = solver.solve(self.iterations[root_state.street])
        return StreetSolve(tree, (combos[0], combos[1]), result.average, None, time.perf_counter() - started, len(locks))

    def _preflop_policy(self, depth: int, opponent: int, locks: dict):
        """Node -> (actions, 1326) strategy: the chart, or a locked re-solve."""
        if not locks:
            return lambda node: self.charts.strategy(depth, node)
        key = (depth, opponent, locks_key(locks))
        policy = _PREFLOP_CACHE.get(key)
        if policy is None:
            class_d, class_w = load_class_equity()
            counts = CLASS_COMBO_COUNT.astype(float)
            solver = RangeSolver(self.charts.trees[depth], (counts, counts), class_d, class_w, locks=locks)
            policy = solver.solve(PREFLOP_LOCKED_ITERATIONS).average
            _PREFLOP_CACHE[key] = policy
            if len(_PREFLOP_CACHE) > _PREFLOP_CACHE_SIZE:
                _PREFLOP_CACHE.popitem(last=False)
        else:
            _PREFLOP_CACHE.move_to_end(key)
        return lambda node: policy[node][:, COMBO_CLASS]

    def _range_report(self, board, hero_combo: int, villain: np.ndarray) -> dict[str, Any]:
        """Hero equity against the villain's current public range, plus its top classes."""
        hero_cards = COMBOS[hero_combo]
        weights = np.where(card_mask(tuple(hero_cards) + tuple(board)), 0.0, villain)
        total = weights.sum()
        if total <= 0:
            return {}
        if board:
            live, d, compat = _full_equity(tuple(board), self.flop_runouts)
            row = int(np.searchsorted(live, hero_combo))
            w = weights[live] * compat[row]
            equity = float((w * (1 + d[row]) / 2).sum() / w.sum()) if w.sum() > 0 else 0.5
        else:
            class_d, _ = load_class_equity()
            equity = float((weights * (1 + class_d[COMBO_CLASS[hero_combo], COMBO_CLASS]) / 2).sum() / total)
        effective = float(total ** 2 / (weights ** 2).sum())
        report: dict[str, Any] = {"hero_equity_vs_range": round(equity, 4), "villain_effective_combos": round(effective, 1)}
        if effective < 300:  # individual hands are only informative for narrow ranges
            by_class = np.bincount(COMBO_CLASS, weights=weights, minlength=len(HAND_CLASSES)) / total
            top = np.argsort(by_class)[::-1][:12]
            report["villain_top_classes"] = [{"hand": HAND_CLASSES[i], "share": round(float(by_class[i]), 4)} for i in top if by_class[i] > 0]
        if board:
            live = np.where(weights > 0)[0]
            ranks = rank_vector(list(board), live)
            makeup: dict[str, float] = {}
            for rank, weight in zip(ranks, weights[live]):
                label = eval7.handtype(int(rank))
                makeup[label] = makeup.get(label, 0.0) + float(weight) / total
            report["villain_range_makeup"] = [{"type": label, "share": round(share, 4)} for label, share in sorted(makeup.items(), key=lambda item: -item[1])]
        return report

    def _profile_summary(self, profile) -> dict[str, Any]:
        if profile is None:
            return {"active": False}
        return {"active": True, "hands_observed": getattr(profile, "hands_observed", 0), "classification": getattr(profile, "classification", "unknown"),
                **self.showdown_model.summary()}

    @staticmethod
    def _apply_strategy(weights: np.ndarray, solve: StreetSolve, node: int, choice: int) -> np.ndarray:
        player = solve.tree.nodes[node].player
        updated = np.zeros_like(weights)
        combos = solve.combos[player]
        updated[combos] = weights[combos] * solve.average[node][choice]
        return updated

    def _sample(self, ds, probabilities: np.ndarray) -> int:
        text = f"solver|{self.seed_base}|{ds.match_id}|{ds.hand_id}|{ds.hand_number}|{ds.street}|{len(ds.hand_actions)}"
        rng = random.Random(int.from_bytes(sha256(text.encode()).digest()[:8], "big"))
        p = np.clip(np.asarray(probabilities, dtype=float), 0.0, None)
        p = p / p.sum() if p.sum() > 0 else np.full(len(p), 1.0 / len(p))
        return int(np.searchsorted(np.cumsum(p), rng.random() * p.sum() * (1 - 1e-12), side="right"))

    # ----------------------------------------------------------- concretize
    @staticmethod
    def _legalize(ds, kind: str, target: int | None) -> Action:
        legal = ds.legal_actions
        if kind == "fold" and "check" in legal:
            return Action("check")
        if kind in ("fold", "check", "call"):
            if kind in legal:
                return Action(kind)
            return Action("check") if "check" in legal else Action("call") if "call" in legal else Action("fold")
        if kind == "all_in" and "all_in" in legal:
            return Action("all_in")
        aggressive = "bet" if "bet" in legal else "raise" if "raise" in legal else None
        if aggressive is None or ds.minimum_legal_target is None or target is None:
            if "all_in" in legal and kind == "all_in":
                return Action("all_in")
            return Action("call") if "call" in legal else Action("check") if "check" in legal else Action("fold")
        bounded = min(max(int(target), ds.minimum_legal_target), ds.maximum_legal_target)
        if bounded >= ds.maximum_legal_target and "all_in" in legal:
            return Action("all_in")
        return Action(aggressive, bounded)

    def _concrete_preflop(self, ds, node, choice: int, scale: float) -> Action:
        kind, target = node.actions[choice]
        if kind in ("bet", "raise") and target is not None:
            state = node.state
            ratio = target / state.highest
            target = int(round(ratio * ds.current_highest_bet))
        return self._legalize(ds, kind, target)

    def _concrete_postflop(self, ds, action: tuple[str, int | None]) -> Action:
        kind, target = action
        return self._legalize(ds, kind, target)


class AdaptiveSolverBot(SolverBot):
    """SolverBot that exploits confident public reads of its opponent.

    Postflop reads are partially pooled across streets (5I): development A/B
    sessions showed gains against equity and expert with no significant loss
    against any opponent, while sample-size ("evidence") lock weights hurt
    against tight and random and stay off."""
    exploit = True
    pool_streets = True
