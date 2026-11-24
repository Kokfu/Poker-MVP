"""Phase 4V offline replay and verification. Run with python -m from backend."""
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import asdict, replace
import json
from math import ceil
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

import numpy as np

from coach import service as coach
from research.holdem import decoupled_replay, phase_4u
from research.holdem.decoupled_replay import CFRWorkingSet, DecoupledReplay, PersistentRange
from research.holdem.live_trace import (
    PublicRangeTrace, SolverTrace, assert_legal, decision_input, mask_stats, partition, public_history, range_stats,
)
from research.holdem.phase_4k import (
    OPPONENTS, STACK, _derived_seed, make_opponent, peak_resident_bytes, train,
)
from research.holdem.phase_4l import normalize
from research.holdem.phase_4r import failed_case
from simulation.bots import BOT_TYPES, AggressiveBot
from simulation.engine import HandEngine
from simulation.history import validate_hand_history
from simulation.history_service import hand_history_from_dict, run_builtin_match_history
from solver import bot as solver
from solver.combos import card_mask, combo_index


MODULE = "research.holdem.phase_4v"
BOARD = ["2c", "7d", "Jh", "9s", "4h"]
COACH_LINES = {
    "tight_passive": (900, 900, "hc vx vx hx vb100 hc vx hx"),
    "loose_passive": (1500, 1500, "hr250 vc vx hb200 vc vx hx va hf"),
    "tight_aggressive": (1500, 3000, "hr300 vc vb300 hr700 vc vx hx va ha"),
    "loose_aggressive": (3000, 3000, "hc vx vb100 hc vx hb300 vc vb200 hc"),
}
MATCHES = {
    "tight-aggressive": ("tight", "aggressive", 42, 5, 3000),
    "range-adaptive": ("range_expert", "adaptive", 71, 4, 1500),
    "range-tracker": ("range_expert", "range_expert", 42, 12, 6000),
    "solver-tight": ("solver", "tight", 42, 2, 1500),
    "solver-equity": ("solver_adaptive", "equity", 71, 2, 1500),
}
SCENARIOS = (*COACH_LINES, "collapse", "collapse-profiled", *MATCHES, "archive")
SOLVERS = ("solver", "solver_adaptive", "solver_adaptive_gated", "solver_adaptive_sized")
ACTION = dict(c="call", x="check", b="bet", r="raise", a="all_in", f="fold")
TIMING = {"decision_seconds", "trace_seconds", "seconds", "solve_seconds", "stage_seconds",
          "elapsed", "peak_mib", "tracker_trace_seconds"}


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in TIMING}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    return value


def coach_spot(name):
    if name in ("collapse", "collapse-profiled"):
        spot = failed_case().spot()
        return replace(spot, actions=[*spot.actions, coach.SpotAction("hero", "fold")])
    hero, villain, line = COACH_LINES[name]
    actions = [coach.SpotAction("hero" if item[0] == "h" else "villain",
                                ACTION[item[1]], int(item[2:]) if item[2:] else None)
               for item in line.split()]
    return coach.Spot(["As", "Kd"], BOARD, hero_stack=hero, villain_stack=villain, actions=actions)


class FixtureStore:
    """Serve synthetic records in the same format as a local Coach store."""

    def __init__(self, name, stream=221, count=None):
        if count is None:
            count = 3 if name in ("tight_passive", "loose_aggressive") else 30
        base = 41_000_000 + 100_000 * OPPONENTS.index(name) + stream * 1000
        self.records = []
        for index in range(count):
            seed = base + index
            engine = HandEngine(AggressiveBot(_derived_seed(seed, "training-hero")),
                                make_opponent(name, _derived_seed(seed, "training-villain")),
                                stack=STACK, seed=seed, hand_id=f"train-{seed}",
                                button=("a", "b")[index % 2])
            result = engine.play()
            history = result["history"]
            revealed = next((event.revealed_hole_cards for event in history.events
                             if event.revealed_hole_cards), {})
            entered = [coach.SpotAction("hero" if event.actor == "a" else "villain", event.applied_action,
                                        event.target_total if event.applied_action in ("bet", "raise") else None)
                       for event in history.events if event.event_type == "action_taken"]
            spot = coach.Spot(
                list(engine.observe("a").hole_cards), history.final_board,
                hero_position="button" if history.button_player == "a" else "big_blind",
                hero_stack=history.starting_stack_a, villain_stack=history.starting_stack_b,
                small_blind=history.small_blind_amount, big_blind=history.big_blind_amount,
                actions=entered, villain_cards=revealed.get("b"))
            self.records.append(coach.spot_to_dict(spot))

    def hands(self, opponent):
        return self.records


def verify_history(history):
    validation = validate_hand_history(history)
    assert validation.valid, validation.errors
    total = history.starting_stack_a + history.starting_stack_b
    assert history.settlement_complete and not history.illegal_action_count
    assert history.final_stack_a + history.final_stack_b == total
    board = []
    for event in history.events:
        assert event.pot_before + event.stack_a_before + event.stack_b_before == total
        assert event.pot_after + event.stack_a_after + event.stack_b_after == total
        assert event.board[:len(board)] == board
        board = event.board
        if event.event_type == "action_taken":
            assert event.applied_action in event.legal_actions and not event.fallback_used
            if event.applied_action in ("bet", "raise"):
                assert event.minimum_legal_target <= event.target_total <= event.maximum_legal_target
    return public_history(history)


def coach_prefixes(spot):
    slots = []
    for index in range(len(spot.actions) + 1):
        prefix = replace(spot, actions=spot.actions[:index])
        status, payload, _ = coach._replay(prefix)
        if status == "hero_to_act":
            prefix = replace(prefix, board=payload["state"]["board"])
            slots.append(prefix)
        elif status == "hand_complete":
            slots.append(prefix)
    assert slots[-1].actions == spot.actions
    return slots


def traced_factory(factory, detailed, decisions, contexts):
    def construct(*args, **kwargs):
        bot = factory(*args, **kwargs)
        SolverTrace(bot, detailed, decisions, contexts)
        return bot

    return construct


def run_coach(prefixes, name, store, detailed):
    decisions, contexts = [], []
    factories = {key: traced_factory(getattr(solver, key), detailed, decisions, contexts)
                 for key in ("SolverBot", "AdaptiveSolverBot")}
    started = perf_counter()
    with patch.multiple(solver, **factories):
        responses = [coach.advise(spot, name, store=store, seed=917) for spot in prefixes]
    elapsed = perf_counter() - started
    return {"responses": responses, "decisions": decisions, "elapsed": elapsed}, contexts


def compare_arms(control, traced):
    assert stable(control["responses"]) == stable(traced["responses"])
    comparable = ("source", "action", "mix", "selected", "reason")
    for first, second in zip(control["decisions"], traced["decisions"], strict=True):
        assert {key: first.get(key) for key in comparable} == {key: second.get(key) for key in comparable}


def run_research(ds, profile, showdown, selection):
    """Observe actual persistent writes and the actual projected solver input."""
    rows, vectors, reaches, solves = [], [], [], []
    hero = 0 if ds.acting_player == ds.button_player else 1
    private = card_mask(ds.hole_cards)
    advisor = DecoupledReplay(selection)
    if showdown is not None:
        advisor.showdown_model = deepcopy(showdown)
    original_solve = solver.SolverBot._solve
    steps = iter(solver.replay_hand(ds).steps)
    hook_seconds = 0.

    class TrackedRange(PersistentRange):
        def __init__(self):
            super().__init__()
            self.seat = len(reaches)
            reaches.append(self)

        def record(self, kind, prior, removed):
            nonlocal hook_seconds
            started = perf_counter()
            blocked = np.array([bool(set(self.board).intersection(pair)) for pair in solver.COMBOS])
            assert not np.any((prior == 0) & (self.weights > 0))
            stats = mask_stats(self.weights, blocked, private if self.seat != hero else np.zeros_like(private))
            assert stats["normalization_sum"] is not None
            assert abs(stats["raw_mass"] - 1.) < 1e-12
            rows.append({"event": kind, "board": self.board, "seat": self.seat,
                         "removed": removed, "posterior": stats})
            vectors.append(self.weights)
            hook_seconds += perf_counter() - started

        def reveal(self, board):
            prior = self.weights
            super().reveal(board)
            self.record("board", prior, float(prior[self.blocked].sum()))

        def observe(self, likelihood):
            step = next(steps)
            assert step.player == self.seat
            prior = self.weights
            evidence = super().observe(likelihood)
            self.record("observation", prior, 1 - evidence)
            rows[-1].update(street=step.street, action=[step.kind, step.target],
                            before=asdict(step.before), evidence=evidence)
            vectors.append(likelihood)
            return evidence

    def solve(bot, state, board, ranges, hero_combo, player, snapshot=None):
        result = original_solve(bot, state, board, ranges, hero_combo, player, snapshot)
        solves.append(result)
        return result

    started = perf_counter()
    with patch.object(decoupled_replay, "PersistentRange", TrackedRange), patch.object(solver.SolverBot, "_solve", solve):
        action, explanation = advisor._decide(ds, profile)
    seconds = perf_counter() - started
    assert_legal(ds, action)
    assert len(solves) == len(advisor.projections) == 1
    assert next(steps, None) is None
    solved = solves[0]
    node = solved.tree.nodes[solved.tree.root]
    holdings = solved.combos[hero]
    column = int(np.searchsorted(holdings, combo_index(ds.hole_cards)))
    mix = solved.average[node.index][:, column]
    assert np.isfinite(mix).all() and (mix >= 0).all() and abs(float(mix.sum()) - 1) < 1e-6
    menu = [advisor._concrete_postflop(ds, item) for item in node.actions]
    for item in menu:
        assert_legal(ds, item)
    seats = []
    for seat, ids in enumerate(solved.combos):
        weights = reaches[seat].weights
        compatible = weights if seat == hero else np.where(private, 0., weights)
        seats.append({"board": partition(weights, ids), "compatible": partition(compatible, ids)})
        assert len(ids) <= selection.limit
        assert len(ids) > 0 and not reaches[seat].blocked[ids].any()
        assert np.isclose(seats[-1]["board"]["omitted"], advisor.projections[0][1][seat].omitted)
    assert not advisor.estimate[private].any() and abs(float(advisor.estimate.sum()) - 1.) < 1e-12
    laws = [entry.law.probabilities for entry in advisor.observations]
    return {"limit": selection.limit, "seed": selection.sample_seed, "action": asdict(action),
            "geometry": asdict(node.state), "mix": mix.tolist(), "menu": [asdict(item) for item in menu],
            "action_ev": explanation["action_ev"], "ranges": rows, "seats": seats,
            "seconds": seconds, "trace_seconds": hook_seconds,
            "stage_seconds": advisor.stage_seconds}, [*vectors, *laws, *advisor.persistent, advisor.estimate]


def research_matrix(ds, profile, showdown, expanded):
    selections = [CFRWorkingSet()]
    if expanded:
        selections += [CFRWorkingSet(limit, seed) for limit in (32, 128, 384, 896)
                       for seed in (None, 17, 29) if (limit, seed) != (896, None)]
    rows = []
    baseline = None
    for selection in selections:
        row, vectors = run_research(ds, profile, showdown, selection)
        if baseline is None:
            baseline = vectors
        else:
            for expected, actual in zip(baseline, vectors, strict=True):
                np.testing.assert_array_equal(expected, actual)
        rows.append(row)
    return rows


def coach_scenario(name, reverse):
    spot = coach_spot(name)
    prefixes = coach_prefixes(spot)
    if name == "collapse-profiled":
        profile_name = "tight_aggressive"
        store = FixtureStore(profile_name, 131, 3)
    else:
        profile_name = None if name == "collapse" else name
        store = FixtureStore(name) if profile_name else None
    # Warm equity and chart caches with the same advice requests. No timing
    # sample from this pass enters the paired measurement.
    untouched = [coach.advise(prefix, profile_name, store=store, seed=917) for prefix in prefixes]
    arms = {}
    for detailed in (True, False) if reverse else (False, True):
        arm, contexts = run_coach(prefixes, profile_name, store, detailed)
        if detailed:
            traced_contexts = contexts
        arms["traced" if detailed else "control"] = arm
    compare_arms(arms["control"], arms["traced"])
    # The warmup may populate the global preflop lock cache.
    for plain, witnessed in zip(untouched, arms["traced"]["responses"], strict=True):
        assert plain.get("advice") == witnessed.get("advice")
        assert (plain.get("explanation") or {}).get("probabilities") == (
            witnessed.get("explanation") or {}).get("probabilities")
    expected_fallbacks = ["empty range"] if name == "collapse-profiled" else []
    actual_fallbacks = [row["reason"] for row in arms["traced"]["decisions"] if row["source"] == "fallback"]
    # Preserve unexpected failures in the evidence alongside the full trace.
    fallback_ok = len(actual_fallbacks) == len(expected_fallbacks) and all(
        expected in actual for actual, expected in zip(actual_fallbacks, expected_fallbacks))
    research = []
    for ds, profile, showdown in traced_contexts:
        if ds.street != "preflop":
            research.append({"input": decision_input(ds),
                             "projections": research_matrix(ds, profile, showdown, name.startswith("collapse"))})
    status, payload, _ = coach._replay(spot)
    assert status == "hand_complete"
    timeline = verify_history(payload["result"]["history"])
    return {"mode": "coach", "arms": arms, "research": research, "timeline": timeline,
            "fallback_ok": fallback_ok}


def run_match(options, detailed):
    decisions, contexts = [], []
    factories = {key: traced_factory(BOT_TYPES[key], detailed, decisions, contexts)
                 for key in SOLVERS}
    tracker = PublicRangeTrace()
    original_update = HandEngine._update_public_ranges
    original_observe = HandEngine.decision_observation

    def update(engine, actor, action, target, pot, commitment):
        viewer = engine.other(actor)
        if viewer not in engine.range_trackers:
            return original_update(engine, actor, action, target, pot, commitment)
        return tracker.capture(engine, viewer, action, original_update, actor, action, target, pot, commitment)

    def observe(engine, seat):
        if not getattr(engine.bots[seat], "uses_range_equity", False):
            return original_observe(engine, seat)
        return tracker.capture(engine, seat, "decision", original_observe, seat)

    started = perf_counter()
    with patch.dict(BOT_TYPES, factories):
        if detailed and "range_expert" in (options["bot_a"], options["bot_b"]):
            with patch.object(HandEngine, "_update_public_ranges", update), patch.object(
                    HandEngine, "decision_observation", observe):
                document = run_builtin_match_history(**options)
        else:
            document = run_builtin_match_history(**options)
    elapsed = perf_counter() - started
    return {"responses": document, "decisions": decisions, "elapsed": elapsed,
            "range_tracker": tracker.rows, "tracker_trace_seconds": tracker.seconds}, contexts


def match_scenario(name, reverse):
    bot_a, bot_b, seed, maximum, stack = MATCHES[name]
    options = dict(bot_a=bot_a, bot_b=bot_b, seed=seed, max_hands=maximum,
                   starting_stack=stack, equity_iterations=500)
    untouched = run_builtin_match_history(**options)
    arms = {}
    for detailed in (True, False) if reverse else (False, True):
        arm, contexts = run_match(options, detailed)
        if detailed:
            traced_contexts = contexts
        arms["traced" if detailed else "control"] = arm
    compare_arms(arms["control"], arms["traced"])
    document = arms["traced"]["responses"]
    assert untouched == document
    assert document["aggregate_validation"]["valid"]
    histories = [hand_history_from_dict(item) for item in document["histories"]]
    timelines = [verify_history(history) for history in histories]
    for previous, current in zip(histories, histories[1:]):
        assert (previous.final_stack_a, previous.final_stack_b) == (current.starting_stack_a, current.starting_stack_b)
        assert previous.button_player != current.button_player
    for row in arms["traced"]["decisions"]:
        state = row["input"]
        history = histories[state["hand_number"] - 1]
        actions = [event for event in history.events if event.event_type == "action_taken"]
        prefix = state["hand_actions"]
        assert [(item["player"], item["action"], item["amount"]) for item in prefix] == [
            (event.actor, event.applied_action, event.target_total)
            for event in actions[:len(prefix)]]
        event = actions[len(prefix)]
        hero, villain = state["acting_player"], state["opponent"]
        assert event.actor == hero and event.street == state["street"]
        assert event.pot_before == state["pot"]
        assert getattr(event, f"stack_{hero}_before") == state["hero_stack"]
        assert getattr(event, f"stack_{villain}_before") == state["opponent_stack"]
        assert getattr(event, f"street_commitment_{hero}_before") == state["hero_street_commitment"]
        assert getattr(event, f"street_commitment_{villain}_before") == state["opponent_street_commitment"]
        assert event.legal_actions == state["legal_actions"]
        assert event.applied_action == row["action"]["type"]
        assert event.board == state["board_cards"]
    research = []
    for ds, profile, showdown in traced_contexts:
        if ds.street != "preflop":
            research.append({"input": decision_input(ds),
                             "projections": research_matrix(ds, profile if bot_a == "solver_adaptive" else None,
                                                            showdown, False)})
    # Verify the exported document before dropping showdown card identities.
    for arm in arms.values():
        arm["responses"] = arm["responses"]["match"]
    return {"mode": "match", "arms": arms, "timelines": timelines, "research": research,
            "fallback_ok": not document["aggregate_fallback_count"] and
            all(row["source"] != "fallback" for row in arms["traced"]["decisions"])}


def archive_scenario():
    case, stream, prefix, name = next(row for row in phase_4u.schedule("holdout")
                                      if (row[0].index, row[1], row[3]) == (3, 213, "loose_passive"))
    profile = train(name, stream, (prefix,))[prefix]
    result = phase_4u.evaluate(case, stream, prefix, name, profile, history=True)
    historical = result["historical"]
    delta = result["adjustment"]["true_delta"]
    assert abs(delta - (-2.3469734621808507)) < 1e-6
    assert result["adjustment"]["accepted"]
    adapter = DecoupledReplay()
    node, ds, _ = adapter.trace(case.spot(), profile)
    ids = np.array([combo_index(pair) for pair in historical["holdings"]])
    modeled = normalize(adapter.estimate[ids])
    reference = np.asarray(historical["reference_posterior"])
    incoming = np.asarray(historical["reference_incoming"])
    evaluation = phase_4u.prepare_evaluation(adapter, profile.snapshot)
    forecast = evaluation.forecasts()
    modeled_reply_values = evaluation.values(forecast)
    order = np.searchsorted(evaluation.ids, ids)
    values = modeled_reply_values[:, order] / ds.big_blind
    policy_delta = np.array(list(result["arms"]["C"]["mix"].values())) - np.array(
        list(result["arms"]["A"]["mix"].values()))
    scenario_vectors = {
        key: float(policy_delta @ (values @ weights)) for key, weights in (
            ("modeled_posterior", modeled), ("reference_posterior", reference),
            ("reference_incoming", incoming))}
    ids_selected = adapter.projections[0][1][1 - node.player].ids
    omitted = ~np.isin(ids, ids_selected)
    # A small omitted probability can still have a material incremental EV
    # contribution. Here both quantities use the same scored payout vector.
    per_hand = policy_delta @ values
    actions = []
    for item in adapter.observations:
        if item.step.player == node.player:
            assert abs(item.posterior.sum() - 1) < 1e-12
            continue
        before, after = normalize(item.prior[ids]), normalize(item.posterior[ids])
        actions.append({"street": item.step.street, "action": item.step.kind,
                        "prior_effective": float(1 / (before @ before)),
                        "posterior_effective": float(1 / (after @ after)),
                        "reply_delta_before": float(per_hand @ before),
                        "reply_delta_after": float(per_hand @ after), "evidence": item.evidence})
    return {"mode": "archive", "key": [case.index, stream, prefix, name], "board": case.board,
            "exact_delta": delta, "interval": result["adjustment"]["interval"],
            "modes": scenario_vectors, "modeled_with_reference_replies": float(
                policy_delta @ historical["substitutions"]["full_true_replies"]),
            "posterior_tv": float(np.abs(modeled - reference).sum() / 2),
            "incoming_tv": float(np.abs(incoming - historical["modeled_incoming"]).sum() / 2),
            "reference_effective": float(1 / (reference @ reference)),
            "modeled_effective": float(1 / (modeled @ modeled)), "actions": actions,
            "omitted_modeled": float(modeled[omitted].sum()),
            "omitted_reference": float(reference[omitted].sum()),
            "omitted_model_reply_delta_modeled": float(per_hand[omitted] @ modeled[omitted]),
            "omitted_model_reply_delta_reference": float(per_hand[omitted] @ reference[omitted])}


def runtime(values):
    values = sorted(values)
    if values:
        return {"n": len(values), "median": median(values), "p95": values[ceil(.95 * len(values)) - 1],
                "max": values[-1]}
    return {"n": 0}


def run_panel(output, reverse):
    output.mkdir(parents=True, exist_ok=True)
    rows = {}
    deadline = perf_counter() + 1200
    for name in SCENARIOS:
        filename = output / f"{name}.json"
        command = [sys.executable, "-m", MODULE, "--scenario", name, str(filename)]
        if reverse:
            command.append("--reverse")
        try:
            remaining = deadline - perf_counter()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, 1200)
            result = subprocess.run(command, check=False, timeout=min(90, remaining),
                                    capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            rows[name] = json.loads(filename.read_text(encoding="utf-8"))
        except (subprocess.TimeoutExpired, RuntimeError) as error:
            rows[name] = {"failure": type(error).__name__, "detail": str(error)}
            filename.write_text(json.dumps(rows[name], indent=2), encoding="utf-8")
        print(name, rows[name].get("failure", "finished"), flush=True)
    return rows


def summarize(first_dir, second_dir):
    seeds = [{name: json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
              for name in SCENARIOS} for folder in (first_dir, second_dir)]
    summary = {"hash_match": {}, "seeds": []}
    for name in SCENARIOS:
        summary["hash_match"][name] = (
            all("failure" not in seed[name] for seed in seeds) and
            stable(seeds[0][name]) == stable(seeds[1][name]))
    for seed in seeds:
        groups = {"coach": [], "match": []}
        result = {"failures": {}, "scenarios": {}, "modes": {}}
        for name, row in seed.items():
            if "failure" in row:
                result["failures"][name] = row
                continue
            if row["mode"] == "archive":
                continue
            groups[row["mode"]].append(row)
            decisions = row["arms"]["traced"]["decisions"]
            research = [projection for case in row["research"] for projection in case["projections"]]
            result["scenarios"][name] = {
                "decisions": len(decisions), "research_solves": len(research),
                "fallbacks": [item["reason"] for item in decisions if item["source"] == "fallback"],
                "fallback_ok": row["fallback_ok"],
                "elapsed": {key: arm["elapsed"] for key, arm in row["arms"].items()},
                "peak_mib": row["peak_mib"],
                "source": [item["source"] for item in decisions],
                "geometry": {
                    "reconstruction_errors": sum("reconstruction_error" in item["input"] for item in decisions),
                    "last_raise_mismatches": sum(item["input"].get("last_raise_matches") is False
                                                 for item in decisions),
                    "reopening_mismatches": sum(item["input"].get("reconstructed_raising_reopened") !=
                                                item["input"]["raising_reopened"] for item in decisions
                                                if "reconstructed" in item["input"]),
                },
            }
        for mode, rows in groups.items():
            research = [projection for row in rows for case in row["research"] for projection in case["projections"]]
            stage_totals = [sum(item["stage_seconds"][stage] for stage in ("preflop", "likelihood", "posterior"))
                            for item in research]
            result["modes"][mode] = {
                "workflow": {arm: runtime(row["arms"][arm]["elapsed"] for row in rows)
                             for arm in ("control", "traced")},
                "decision": {arm: runtime(item["decision_seconds"] for row in rows
                                         for item in row["arms"][arm]["decisions"])
                             for arm in ("control", "traced")},
                "trace_hooks": runtime(item["trace_seconds"] for row in rows
                                       for item in row["arms"]["traced"]["decisions"]),
                "research_decision": runtime(item["seconds"] for item in research),
                "research_inference": runtime(stage_totals),
                "research_hooks": runtime(item["trace_seconds"] for item in research),
                "incumbent_columns": runtime(seat["board"]["columns"] for row in rows
                                             for decision in row["arms"]["traced"]["decisions"]
                                             for solve in decision["solves"] for seat in solve["seats"]),
                "research_columns": runtime(seat["board"]["columns"] for item in research for seat in item["seats"]),
            }
        summary["seeds"].append(result)
    return summary


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("FIRST_DIR", "SECOND_DIR"))
    args = parser.parse_args()
    if args.compare:
        result = summarize(*args.compare)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        if not all(result["hash_match"].values()):
            raise SystemExit(1)
        return
    if args.scenario == "archive":
        result = archive_scenario()
    elif args.scenario in MATCHES:
        result = match_scenario(args.scenario, args.reverse)
    elif args.scenario:
        result = coach_scenario(args.scenario, args.reverse)
    else:
        rows = run_panel(args.output.resolve(), args.reverse)
        if any("failure" in row or not row.get("fallback_ok", True) for row in rows.values()):
            raise SystemExit(1)
        return
    result["schema_version"] = 1
    result["peak_mib"] = peak_resident_bytes() / 2**20
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
