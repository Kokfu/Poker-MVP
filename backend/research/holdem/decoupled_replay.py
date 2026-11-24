"""Full-support public inference and a separate, bounded decision solve."""
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import eval7
import numpy as np

from research.holdem.phase_4r import RangeSupportError, conditional_range
from research.holdem.range_support import MAX_COLUMNS, ResearchReplay, WorkingSet, working_set
from solver.bot import STREETS, ReplayError, SolverBot, Step, _log_distance, map_action, replay_hand
from solver.cfr import fit_frequencies
from solver.combos import COMBOS, COMBO_COUNT, card_mask, combo_index
from solver.equity import rank_vector
from solver.exploit import group_target, tree_locks, node_lock
from solver.preflop import CHART_BB
from solver.tree import Node, POSTFLOP_MENU, legal_abstract_actions


BOARD_LENGTH = {"flop": 3, "turn": 4, "river": 5}
IDS = np.arange(COMBO_COUNT)
OPEN = np.array([.25, .40, .68])
SIZES = np.array([[.52, .67, .38], [.30, .25, .32], [.18, .08, .30]])
CONTINUE = np.array([.35, .72, .95])
RAISE = np.array([.08, .08, .28])


class PersistentRange:
    """Normalized board-legal public reach, in global combo order."""

    def __init__(self):
        self.board = ()
        self.blocked = card_mask(())
        self.weights = np.full(COMBO_COUNT, 1 / COMBO_COUNT)
        self.weights.setflags(write=False)

    def reveal(self, board):
        if board[:len(self.board)] != self.board or len(set(board)) != len(board):
            raise ValueError("board must extend the existing public prefix")
        blocked = card_mask(board)
        updated = conditional_range(self.weights, blocked)
        updated.setflags(write=False)
        self.weights, self.board, self.blocked = updated, board, blocked

    def observe(self, likelihood):
        if (likelihood.shape != (COMBO_COUNT,) or not np.isfinite(likelihood).all()
                or (likelihood < 0).any() or (likelihood > 1 + 1e-12).any()):
            raise ValueError("invalid observed action likelihood")
        joint = self.weights * likelihood
        evidence = float(joint.sum())
        if evidence == 0:
            raise RangeSupportError("observed action has zero model probability")
        self.weights = conditional_range(joint, self.blocked)
        self.weights.setflags(write=False)
        return evidence

    def conditioned(self, known_cards):
        return conditional_range(self.weights, card_mask(known_cards))


@lru_cache(maxsize=24)
def hand_tiers(board):
    ranks = rank_vector(list(board), IDS)
    live = np.flatnonzero(ranks >= 0)
    unique, inverse = np.unique(ranks[live], return_inverse=True)
    types = [eval7.handtype(int(rank)) for rank in unique]
    tier = np.array([0 if name == "High Card" else 1 if name == "Pair" else 2 for name in types])
    live.setflags(write=False)
    tiers = tier[inverse]
    tiers.setflags(write=False)
    return live, tiers


@dataclass(frozen=True)
class ActionLaw:
    actions: tuple
    live: np.ndarray
    probabilities: np.ndarray

    def index(self, step):
        kind, target = step.kind, step.target
        state, player = step.before, step.player
        if kind == "all_in":
            target = state.commit[player] + state.stack[player] if target is None else target
            if target <= state.highest:
                kind = "call"
        if kind in ("check", "call", "fold"):
            if (kind, None) not in self.actions:
                raise ReplayError(f"observed {kind} unavailable")
            return self.actions.index((kind, None))
        if kind not in ("bet", "raise", "all_in") or target is None:
            raise ReplayError("invalid observed wager")
        aggression = [(i, action) for i, action in enumerate(self.actions) if action[1] is not None]
        if not aggression:
            raise ReplayError("observed aggression unavailable")
        for i, (label, size) in aggression:
            if size == target or (label == "all_in" and target >= size):
                return i
        return min(aggression, key=lambda option: _log_distance(target, option[1][1]))[0]

    def observed(self, step):
        row = np.zeros(COMBO_COUNT)
        row[self.live] = self.probabilities[self.index(step)]
        return row


class OpponentActionLikelihood:
    """Model a past observation from public state, before any decision solve."""

    def distribution(self, state, board, prior, profile=None):
        if len(board) != BOARD_LENGTH.get(state.street):
            raise ValueError("observation requires the street's public board prefix")
        live, tiers = hand_tiers(board)
        actions = tuple((kind, target) for _, kind, target in legal_abstract_actions(state, POSTFLOP_MENU))
        if not actions:
            raise ReplayError("observation has no legal actions")
        base = np.zeros((len(actions), 3))
        facing = actions[0][0] == "fold"
        aggression = len(actions) - (2 if facing else 1)
        if facing:
            outstanding = state.highest - state.commit[state.to_act]
            cost = min(state.stack[state.to_act], outstanding)
            contested_pot = state.pot + cost - (outstanding - cost)
            continuing = np.clip(CONTINUE - .60 * cost / contested_pot, .05, .95)
            raising = continuing * RAISE if aggression else np.zeros(3)
            base[0] = 1 - continuing
            base[1] = continuing - raising
        else:
            base[0] = 1 - OPEN if aggression else 1.
            raising = OPEN
        if aggression:
            base[-aggression:] = np.vstack((SIZES[:aggression - 1], SIZES[aggression - 1:].sum(axis=0))) * raising

        probability = base[:, tiers]
        if profile is not None:
            node = Node(index=0, kind="decision", player=state.to_act, actions=list(actions), state=state)
            read = node_lock(node, state.street, profile)
            if read is not None:
                weight, groups = read
                reach = prior[live]
                target = group_target(probability, reach, groups)
                probability = (1 - weight) * probability + weight * fit_frequencies(probability, reach, target)
        return ActionLaw(actions, live, probability)


@dataclass(frozen=True)
class CFRWorkingSet:
    """One solve's mapping. Alternate limits and sampling are audit controls."""

    limit: int = MAX_COLUMNS
    sample_seed: int | None = None

    def __post_init__(self):
        if not 1 <= self.limit <= MAX_COLUMNS:
            raise ValueError("invalid CFR column limit")

    def select(self, weights, blocked, required, compatible=None):
        if required is not None and blocked[required]:
            raise RangeSupportError("required CFR holding is blocked")
        if self.limit == MAX_COLUMNS and self.sample_seed is None:
            return working_set(weights, blocked, required, compatible)
        legal = np.where(blocked, 0., weights)
        if not legal.any():
            raise RangeSupportError("no board-legal CFR reach")
        if compatible is not None:
            if not legal[compatible].any():
                raise RangeSupportError("no Hero-compatible opponent reach")
            required = int(np.argmax(np.where(compatible, legal, 0.)))
        scaled = legal / legal.max()
        choices = np.flatnonzero(scaled > ResearchReplay.prune)
        choices = choices[choices != required] if required is not None else choices
        slots = self.limit - int(required is not None)
        if len(choices) > slots:
            if self.sample_seed is None:
                choices = choices[np.argsort(-scaled[choices], kind="stable")[:slots]]
            else:
                mass = scaled[choices]
                choices = np.random.default_rng(self.sample_seed).choice(
                    choices, size=slots, replace=False, p=mass / mass.sum())
        ids = np.sort(np.append(choices, required)) if required is not None else np.sort(choices)
        return WorkingSet(ids, int(np.count_nonzero(legal)), min(1., float(scaled[ids].sum() / scaled.sum())))


@dataclass(frozen=True)
class Observation:
    step: Step
    board: tuple
    prior: np.ndarray
    law: ActionLaw
    posterior: np.ndarray
    evidence: float


class DecoupledReplay(ResearchReplay):
    """Offline Coach adapter with no postflop solve in the inference path."""

    def __init__(self, selection=None):
        super().__init__(separate=True)
        self.selection = selection or CFRWorkingSet()
        self.likelihood = OpponentActionLikelihood()

    def _infer(self, replay, board_cards, big_blind, profile):
        hero = replay.current.to_act
        villain = 1 - hero
        ranges = [PersistentRange(), PersistentRange()]
        started = perf_counter()
        depth = self.charts.nearest_depth(min(replay.start_stacks) / big_blind)
        chart = self.charts.trees[depth]
        locks = tree_locks(chart, villain, "preflop", profile, self._strength_correlation(),
                           self.lock_weighting, self.pool_streets)
        policy = self._preflop_policy(depth, villain, locks)
        node = chart.root
        for step in replay.steps:
            if step.street != "preflop":
                break
            if chart.nodes[node].kind != "decision":
                raise ReplayError("preflop history left the chart tree")
            choice = map_action(chart, node, step.kind, step.target, CHART_BB / big_blind)
            ranges[step.player].observe(policy(node)[choice])
            node = chart.nodes[node].children[choice]
        self.stage_seconds["preflop"] += perf_counter() - started

        for street in STREETS[1:STREETS.index(replay.street) + 1]:
            board = tuple(board_cards[:BOARD_LENGTH[street]])
            started = perf_counter()
            for reach in ranges:
                reach.reveal(board)
            self.stage_seconds["posterior"] += perf_counter() - started
            for step in (step for step in replay.steps if step.street == street):
                reach = ranges[step.player]
                prior = reach.weights
                started = perf_counter()
                law = self.likelihood.distribution(step.before, board, prior, profile if step.player == villain else None)
                observed = law.observed(step)
                self.stage_seconds["likelihood"] += perf_counter() - started
                started = perf_counter()
                evidence = reach.observe(observed)
                self.stage_seconds["posterior"] += perf_counter() - started
                self.observations.append(Observation(step, board, prior, law, reach.weights, evidence))
        return ranges

    def _decide(self, ds, profile=None):
        self.observations = []
        self.live_node = self.persistent = self.river = None
        self.stage_seconds = dict.fromkeys(("reconstruction", "preflop", "likelihood", "posterior",
                                            "selection", "solve", "explanation"), 0.)
        if ds.street == "preflop":
            return super()._decide(ds, profile)

        self.projections.clear()
        self.estimate = self.probabilities = None
        self._info = {"cache_hit": False, "unlocked_action_differs": None}
        self.decision_street = ds.street
        started = perf_counter()
        replay = replay_hand(ds)
        self.stage_seconds["reconstruction"] = perf_counter() - started
        ranges = self._infer(replay, ds.board_cards, ds.big_blind, profile)
        hero = replay.current.to_act
        board = ranges[hero].board
        hero_combo = combo_index(ds.hole_cards)
        started = perf_counter()
        self.estimate = ranges[1 - hero].conditioned(ds.hole_cards)
        self.persistent = tuple(reach.weights for reach in ranges)
        self.stage_seconds["posterior"] += perf_counter() - started

        started = perf_counter()
        compatible = ~card_mask(ds.hole_cards)
        selections = tuple(self.selection.select(
            reach.weights, reach.blocked, hero_combo if player == hero else None,
            compatible if player != hero else None) for player, reach in enumerate(ranges))
        projected = [np.zeros(COMBO_COUNT), np.zeros(COMBO_COUNT)]
        for selection, reach, model in zip(selections, projected, ranges, strict=True):
            reach[selection.ids] = model.weights[selection.ids]
        self.projections.append((ds.street, selections))
        self.stage_seconds["selection"] = perf_counter() - started

        started = perf_counter()
        self.prune = 0
        try:
            solved = SolverBot._solve(self, replay.current, board, projected, hero_combo, hero, profile)
        finally:
            self.prune = ResearchReplay.prune
        self.stage_seconds["solve"] = perf_counter() - started
        for selection, ids in zip(selections, solved.combos, strict=True):
            if not np.array_equal(selection.ids, ids):
                raise AssertionError("solver changed the working-set mapping")
        if ds.street == "river":
            self.river = solved
        node = solved.tree.nodes[solved.tree.root]
        column = int(np.searchsorted(solved.combos[hero], hero_combo))
        started = perf_counter()
        mix = solved.average[node.index][:, column]
        choice = self._sample(ds, mix)
        values = solved.solver.action_values(node, column)
        action = self._concrete_postflop(ds, node.actions[choice])
        info = {
            "source": "postflop_solve", "street": ds.street, "labels": node.labels,
            "probabilities": [round(float(p), 4) for p in mix], "chosen": node.labels[choice],
            "range_sizes": [len(ids) for ids in solved.combos], "solve_seconds": round(solved.seconds, 3),
            "exploitability": solved.exploitability, "resolved_from_current_state": True,
            "action_ev": [round(float(v), 1) for v in values],
            "exploit": {**self._profile_summary(profile), "locked_nodes": solved.locked_nodes},
            "instrumentation": self._instrumentation(ds.street, solved.candidate_locks, solved.locked_nodes),
            **SolverBot._range_report(self, board, hero_combo, self.estimate),
        }
        self.stage_seconds["explanation"] = perf_counter() - started
        return action, info
