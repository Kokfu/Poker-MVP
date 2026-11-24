"""Local, single-process observation of the existing Coach and Match solvers."""
from copy import deepcopy
from dataclasses import asdict
from functools import wraps
from time import perf_counter

import numpy as np

from solver.bot import ReplayError, map_action, replay_hand
from solver.combos import COMBOS, COMBO_COUNT, card_mask
from solver.preflop import CHART_BB
from simulation.actions import Action


def range_stats(weights):
    total = float(weights.sum())
    stats = {"raw_mass": total, "positive": int(np.count_nonzero(weights)),
             "effective": None, "normalization_sum": None}
    if total > 0:
        normalized = weights / total
        stats.update(effective=float(1 / (normalized @ normalized)),
                     normalization_sum=float(normalized.sum()))
    return stats


def partition(weights, ids):
    selected = np.zeros(COMBO_COUNT, dtype=bool)
    selected[ids] = True
    total = weights.sum()
    return {"columns": len(ids), "positive": int(np.count_nonzero(weights[selected])),
            "omitted": float(weights[~selected].sum() / total) if total else None}


def mask_stats(weights, blocked, private):
    assert np.all(weights[blocked] == 0)
    return {**range_stats(weights), "compatible": range_stats(np.where(private, 0., weights))}


def decision_input(ds, replay=None):
    record = ds.as_dict()
    del record["hole_cards"]
    try:
        replay = replay or replay_hand(ds)
    except ReplayError as error:
        return {**record, "reconstruction_error": str(error)}
    state = replay.current
    actor = state.to_act
    assert state.stack == ((ds.hero_stack, ds.opponent_stack) if actor == 0
                           else (ds.opponent_stack, ds.hero_stack))
    assert state.commit[actor] == ds.hero_street_commitment
    assert state.commit[1 - actor] == ds.opponent_street_commitment
    assert state.pot == ds.pot and replay.street == ds.street
    record["reconstructed"] = asdict(state)
    record["last_raise_matches"] = state.last_full_raise == ds.last_full_raise_size
    # StreetState tracks each player's action since street start. The engine
    # carries authoritative reopening flags separately.
    record["reconstructed_raising_reopened"] = not state.acted[actor] or (
        state.highest - state.commit[actor] >= state.last_full_raise)
    return record


def assert_legal(ds, action):
    assert action.type in ds.legal_actions
    if action.type in ("bet", "raise"):
        assert ds.minimum_legal_target <= action.amount <= ds.maximum_legal_target


class SolverTrace:
    """Attach to one real solver instance constructed by an offline entry point."""

    def __init__(self, bot, detailed, decisions, contexts=None):
        self.bot, self.detailed = bot, detailed
        self.decisions, self.contexts = decisions, contexts
        self.row = None
        self.seconds = 0.
        self.install("decide_decision", self.decide)
        self.install("_sample", self.sample)
        if detailed:
            self.install("_preflop_policy", self.preflop_policy)
            self.install("_street_solve", self.street_solve)
            self.install("_solve", self.solve)
            self.install("_apply_strategy", self.observe)
            self.install("_range_report", self.report)

    def install(self, name, wrapper):
        original = getattr(self.bot, name)

        @wraps(original)
        def call(*args, **kwargs):
            return wrapper(original, *args, **kwargs)

        setattr(self.bot, name, call)

    def timed(self, function, *args):
        started = perf_counter()
        result = function(*args)
        self.seconds += perf_counter() - started
        return result

    def decide(self, original, observation):
        ds = observation.decision_state
        self.row = {}
        started = perf_counter()
        self.seconds = 0.
        if self.detailed:
            self.ds = ds
            try:
                replay = self.timed(replay_hand, ds)
            except ReplayError:
                replay = None
            record = self.timed(decision_input, ds, replay)
            self.row.update(input=record, solves=[], ranges=[])
            self.last_ranges = [np.ones(COMBO_COUNT), np.ones(COMBO_COUNT)]
            self.board = ()
            self.steps = iter(replay.steps if replay else ())
            self.preflop_steps = [step for step in replay.steps if step.street == "preflop"] if replay else []
            if self.contexts is not None:
                self.contexts.append((ds, observation.opponent_profile, deepcopy(self.bot.showdown_model)))
        action = original(observation)
        assert_legal(ds, action)
        self.row.update(action=asdict(action), source=self.bot.last_explanation["source"])
        if "reason" in self.bot.last_explanation:
            self.row["reason"] = self.bot.last_explanation["reason"]
        if self.detailed:
            explanation = self.bot.last_explanation
            self.row["output"] = {key: explanation[key] for key in (
                "labels", "concrete_labels", "action_ev", "range_sizes",
                "resolved_from_current_state", "instrumentation") if key in explanation}
            if "labels" in explanation:
                if ds.street == "preflop":
                    menu = [parse_label(label) for label in explanation["concrete_labels"]]
                else:
                    raw = [parse_label(label) for label in explanation["labels"]]
                    menu = [self.bot._concrete_postflop(ds, (item.type, item.amount)) for item in raw]
                for item in menu:
                    assert_legal(ds, item)
                assert menu[self.row["selected"]] == action
                self.row["output"]["menu"] = [asdict(item) for item in menu]
            self.row["trace_seconds"] = self.seconds
        self.row["decision_seconds"] = perf_counter() - started
        self.decisions.append(self.row)
        return action

    def sample(self, original, ds, probabilities):
        choice = original(ds, probabilities)
        assert np.isfinite(probabilities).all() and (probabilities >= 0).all()
        assert abs(float(probabilities.sum()) - 1.) <= 1e-6
        self.row.update(mix=probabilities.tolist(), selected=int(choice))
        return choice

    def preflop_policy(self, original, depth, opponent, locks):
        policy = original(depth, opponent, locks)
        tree = self.bot.charts.trees[depth]
        next_step = iter(self.preflop_steps)
        steps_consumed = 0

        def traced_policy(node):
            nonlocal steps_consumed
            matrix = policy(node)
            if steps_consumed < len(self.preflop_steps):
                step = next(next_step)
                choice = map_action(tree, node, step.kind, step.target, CHART_BB / self.ds.big_blind)
                prior = self.last_ranges[step.player]
                updated = prior * matrix[choice]
                self.timed(self.record_action, step.player, prior, updated, None,
                           tree.nodes[node].actions[choice])
                steps_consumed += 1
            return matrix

        return traced_policy

    def record_action(self, seat, prior, updated, ids, mapped):
        step = next(self.steps)
        assert step.player == seat
        selected = prior.sum() if ids is None else prior[ids].sum()
        after = updated.sum()
        self.row["ranges"].append({
            "event": "observation", "street": step.street, "board": self.board, "seat": seat,
            "action": [step.kind, step.target], "mapped_action": mapped, "before": asdict(step.before),
            "projection": partition(prior, ids) if ids is not None else None,
            "prior": range_stats(prior), "posterior": range_stats(updated),
            "observation_mass_removed": float((selected - after) / selected) if selected else None,
            "computational_zeros": int(np.count_nonzero(prior) - np.count_nonzero(prior[ids]))
            if ids is not None else 0,
        })
        assert not np.any((prior == 0) & (updated > 0))
        self.last_ranges[seat] = updated

    def street_solve(self, original, key, state, board, ranges, hero_combo, hero, profile):
        def reveal():
            for seat, weights in enumerate(ranges):
                previous = self.last_ranges[seat]
                assert np.array_equal(weights, np.where(card_mask(board), 0., previous))
                self.row["ranges"].append({
                    "event": "board", "street": state.street, "board": board, "seat": seat,
                    "removed": float(previous[card_mask(board)].sum() / previous.sum()) if previous.sum() else None,
                    "posterior": range_stats(weights),
                })
            self.board, self.last_ranges = board, list(ranges)

        self.timed(reveal)
        cached = key in self.bot.memory.street_solves
        solved = original(key, state, board, ranges, hero_combo, hero, profile)
        if cached:
            self.timed(self.record_solve, solved, state, board, ranges, hero_combo, hero, True)
        return solved

    def solve(self, original, state, board, ranges, hero_combo, hero, profile=None):
        solved = original(state, board, ranges, hero_combo, hero, profile)
        self.timed(self.record_solve, solved, state, board, ranges, hero_combo, hero, False)
        return solved

    def record_solve(self, solved, state, board, ranges, hero_combo, hero, cached):
        blocked, private = card_mask(board), card_mask(COMBOS[hero_combo])
        seats = []
        for player, (weights, ids) in enumerate(zip(ranges, solved.combos, strict=True)):
            assert not blocked[ids].any()
            compatible = weights if player == hero else np.where(private, 0., weights)
            seats.append({"input": range_stats(weights), "board": partition(weights, ids),
                          "compatible": partition(compatible, ids)})
        self.row["solves"].append({"root": asdict(state), "board": board, "cached": cached,
                                   "seconds": solved.seconds, "seats": seats})

    def observe(self, original, weights, solve, node, choice):
        updated = original(weights, solve, node, choice)
        current = solve.tree.nodes[node]
        self.timed(self.record_action, current.player, weights, updated, solve.combos[current.player],
                   current.actions[choice])
        return updated

    def report(self, original, board, hero_combo, villain):
        result = original(board, hero_combo, villain)
        self.row["opponent_range"] = self.timed(
            mask_stats, villain, card_mask(board), card_mask(COMBOS[hero_combo]))
        return result


def public_history(history):
    """Project a real engine timeline onto the offline trace's public fields."""
    fields = ("event_index", "event_type", "street", "actor", "board",
              "pot_before", "pot_after", "stack_a_before", "stack_a_after",
              "stack_b_before", "stack_b_after", "applied_action", "target_total",
              "all_in_classification", "legal_actions", "minimum_legal_target",
              "maximum_legal_target", "amount_paid", "returned_to", "returned_amount",
              "street_commitment_a_before", "street_commitment_b_before",
              "street_commitment_a_after", "street_commitment_b_after",
              "awarded_to_a", "awarded_to_b", "fallback_reason")
    return [{field: getattr(event, field) for field in fields} for event in history.events]


def parse_label(label):
    kind, _, target = label.rpartition("_")
    return Action(kind, int(target)) if target.isdecimal() else Action(label)


class PublicRangeTrace:
    """Record the separate heuristic tracker used by range_expert."""

    def __init__(self):
        self.rows = []
        self.seconds = 0.

    def capture(self, engine, seat, event, original, *args):
        tracker = engine.range_trackers[seat]
        before = dict(tracker.weighted_range.weights)
        result = original(engine, *args)
        started = perf_counter()
        board = engine.state.community_cards
        after = dict(tracker.weighted_range.weights)
        assert all(before.get(combo, 0.) > 0 for combo, weight in after.items() if weight > 0)
        tracker.assert_invariants(board)
        removed = sum(weight for combo, weight in before.items() if set(combo.cards).intersection(board))
        stats = range_stats(np.array(list(after.values())))
        assert abs(stats["raw_mass"] - 1) < 1e-12
        self.rows.append({"hand_number": engine.hand_number, "seat": seat, "event": event,
                          "street": engine.state.street, "board": list(board),
                          "board_mass_removed": removed, "posterior": stats})
        self.seconds += perf_counter() - started
        return result
