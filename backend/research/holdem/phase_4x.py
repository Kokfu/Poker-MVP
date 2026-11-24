"""Offline Phase 4X river decision diagnostics."""
from argparse import ArgumentParser
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import product
import json
from math import fsum
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from research.holdem import phase_4p, phase_4q, phase_4s, phase_4w
from research.holdem.decoupled_replay import CFRWorkingSet
from research.holdem.live_persistent import ReplayBeliefs
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, peak_resident_bytes, to_action, train
from research.holdem.phase_4l import exact_values, legal_optimum
from research.holdem.reply_forecast import holding_values, river_counts
from research.holdem.river_adjustment import bounded_adjustment
from research.holdem.river_ev import ExactRiverEV, RiverState
from research.holdem.river_wager_calibration import Opening, hand_group
from research.holdem.river_wager_reference import law
from research.holdem.live_trace import assert_legal
from solver.bot import SolverBot, _full_equity, replay_hand
from solver.combos import combo_index


EVIDENCE = phase_4w.REPO / "benchmark-results"
ARCHIVE = EVIDENCE / "phase-4w-2026-11-19" / "holdout-13.json"
PROJECTIONS = [(limit, seed) for limit in (32, 128, 384, 896) for seed in (None, 17, 29)]
FRESH_SEED = 448202
FRESH_STREAMS = (321, 322, 323)
FRESH_BOARDS = 12


def normalize(weights):
    mass = weights.sum()
    assert np.isfinite(weights).all() and (weights >= 0).all() and mass > 0
    return weights / mass


def warm(spot):
    for end in (3, 4, 5):
        _full_equity(tuple(spot.board[:end]), SolverBot.flop_runouts)


def wager_state(ds):
    assert ds.big_blind == BIG_BLIND
    return RiverState(ds.pot, ds.hero_street_commitment, ds.opponent_street_commitment,
                      ds.hero_stack, ds.opponent_stack, ds.last_full_raise_size,
                      raising_reopened=ds.raising_reopened, hero_gets_odd_chip=ds.acting_player == "b")


def witness(spot, arm, profile, selection=None, *, weight_multiplier=None, iterations=None):
    """Capture the solve and pre-wager belief while using the original advice path."""
    solves, observations, overrides = [], [], []
    postflop, observe, solve = SolverBot._postflop_advice, ReplayBeliefs.observe, SolverBot._solve

    def traced_advice(bot, ds, solved, index, hero, hero_combo, board, reach, info, **kwargs):
        solves.append((solved, solved.tree.nodes[index], hero_combo))
        overrides.append(bot.iterations[ds.street])
        return postflop(bot, ds, solved, index, hero, hero_combo, board, reach, info, **kwargs)

    def traced_observe(beliefs, player, likelihood):
        if len(beliefs.board) == 5 and player == beliefs.villain:
            observations.append((beliefs.opponent, likelihood))
        return observe(beliefs, player, likelihood)

    # Phase 4W's witness wraps this method in turn, so each call still records
    # the original global column IDs and validates its replay and projection.
    def stressed_solve(bot, state, board, ranges, hero_combo, hero, profile=None, **kwargs):
        if state.street == "river":
            if iterations is not None:
                bot.iterations = {**bot.iterations, "river": iterations}
            if weight_multiplier is not None:
                reaches = list(ranges)
                reaches[1 - hero] = reaches[1 - hero] * weight_multiplier
                ranges = tuple(reaches)
        return solve(bot, state, board, ranges, hero_combo, hero, profile, **kwargs)

    snapshot, showdown = (profile.snapshot, profile.showdown) if profile else (None, None)
    with patch.object(SolverBot, "_postflop_advice", traced_advice), \
            patch.object(ReplayBeliefs, "observe", traced_observe), \
            patch.object(SolverBot, "_solve", stressed_solve):
        row, ds, posterior, ids = phase_4w.advise(spot, arm, snapshot, showdown, selection, audit=True)
    assert row["source"] == "postflop_solve" and len(solves) == 1
    return row, ds, posterior, ids, solves[0], observations, overrides[0]


def reference_factors(case, ds, style, holdings):
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    steps = [step for step in replay.steps if step.player == villain]
    pairs = [hand.combo for hand in holdings]
    history = tuple(phase_4p.observations(replay, villain, case.seat == "button"))
    prior = phase_4p.reference_weights(pairs, history, case.depth, style)
    for step in steps[:-1]:
        if step.street in ("flop", "turn"):
            board = list(case.board[:3 if step.street == "flop" else 4])
            prior *= [phase_4p.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                      for pair in pairs]
    before = steps[-1].before
    opening = Opening(before.pot, before.stack[villain], before.stack[1 - villain],
                      before.last_full_raise, case.line[1] != "check")
    observed, _, _ = opening.action(steps[-1].target)
    likelihood = [law(opening, hand_group(h.combo, case.board, h.rank), style)[observed] for h in holdings]
    return normalize(prior), np.asarray(likelihood)


def modeled_payoffs(context, ids, ranks, outcomes, ds):
    """Traverse CFR's actual final policies with independent terminal transfers.

    Extend replies outside the computed opponent columns by nearest showdown
    rank, averaging equal-rank columns. Both substitutions and this extension
    are diagnostics. On selected columns use each holding's actual strategy.
    """
    solved, root, hero_combo = context
    tree, hero = solved.tree, root.player
    hero_col = int(np.searchsorted(solved.combos[hero], hero_combo))
    cols = solved.combos[1 - hero]
    positions = np.searchsorted(cols, ids).clip(0, len(cols) - 1)
    present = cols[positions] == ids
    levels, groups = np.unique(ranks[present], return_inverse=True)
    assert levels.size
    right = np.searchsorted(levels, ranks).clip(0, len(levels) - 1)
    left = (right - 1).clip(0)
    nearest = np.where(abs(ranks - levels[left]) <= abs(ranks - levels[right]), left, right)
    hero_policy = {node.index: solved.average[node.index][:, hero_col] for node in tree.nodes
                   if node.kind == "decision" and node.player == hero}
    replies = {}
    for node in tree.nodes:
        if node.kind != "decision" or node.player == hero:
            continue
        strategy = solved.average[node.index]
        reply = strategy[:, positions].copy()
        for output in reply:
            sums = np.bincount(groups, weights=output[present], minlength=len(levels))
            output[~present] = (sums / np.bincount(groups))[nearest[~present]]
        replies[node.index] = reply
    keys = [label(SolverBot._legalize(ds, kind, target)) for kind, target in root.actions]
    values = holding_values(tree, root, outcomes, replies, hero_policy, ds.acting_player == "b") / BIG_BLIND
    return keys, values, present, replies


def score(mix, values):
    return fsum(probability * values[key] for key, probability in mix.items())


def greedy(values, truth):
    best = max(values, key=values.get)
    return {"values": values, "mix": {best: 1.}, "regret": max(truth.values()) - truth[best]}


def case_diagnostic(case, stream, prefix, name, profile, archived):
    spot, style = case.spot(), STYLES[name]
    warm(spot)
    a, ds, incumbent, cols_a, context_a, _, _ = witness(spot, "A", profile)
    b, other_ds, repaired, cols_b, context, observations, iterations = witness(spot, "B", profile)
    assert ds == other_ds and len(observations) == 1
    for current, arm in ((a, "A"), (b, "B")):
        original = archived["arms"][arm]
        assert current["action"] == original["action"] and current["mix"] == original["mix"]
        assert current["action_ev"] == original["action_ev"]
    state = wager_state(ds)
    reference = phase_4s.exact_reference(case, ds, style)
    truth = exact_values(reference, state, sorted(a["mix"].keys() | b["mix"].keys()), style.call_probability)
    phase_4w.verify_exact_payoffs(reference, state, truth, style.call_probability)
    assert truth == archived["values"]
    holdings = reference.holdings
    ids = np.array([combo_index(hand.combo) for hand in holdings])
    outcomes, ranks, exact = (np.asarray(items) for items in
                              zip(*[(h.result, h.rank, h.weight) for h in holdings], strict=True))
    prior, observed = (items[ids] for items in observations[0])
    prior = normalize(prior)
    ref_prior, ref_observed = reference_factors(case, ds, style, holdings)
    np.testing.assert_allclose(normalize(prior * observed), repaired[ids], rtol=0, atol=1e-15)
    np.testing.assert_allclose(normalize(ref_prior * ref_observed), exact, rtol=0, atol=1e-15)
    keys, values, present, replies = modeled_payoffs(context, ids, ranks, outcomes, ds)
    assert set(keys) == set(b["mix"])
    solve, root, hero_combo = context
    cfr_ev = solve.solver.action_values(root, np.searchsorted(cols_b[root.player], hero_combo)) / BIG_BLIND
    projected_ev = values @ normalize(repaired[ids] * present)
    np.testing.assert_allclose(projected_ev, cfr_ev, rtol=0, atol=.0051)

    cells = {}
    for swap_prior, swap_observed, swap_replies in product((0, 1), repeat=3):
        weights = normalize((ref_prior if swap_prior else prior) * (ref_observed if swap_observed else observed))
        if swap_replies:
            by_combo = dict(zip((h.combo for h in holdings), weights, strict=True))
            model = ExactRiverEV(case.hero, case.board, lambda pair, _: by_combo[pair])
            model_ev = exact_values(model, state, keys, style.call_probability)
        else:
            model_ev = dict(zip(keys, (values @ weights).tolist(), strict=True))
        cells[f"{swap_prior}{swap_observed}{swap_replies}"] = {
            **greedy(model_ev, truth), "posterior_tv": float(abs(weights - exact).sum() / 2),
            "equity": float(weights @ ((outcomes + 1) / 2)),
        }

    responses = {}
    for key, child_index in zip(keys, root.children, strict=True):
        action = to_action(key)
        hero_target, villain_target, reply = state.branch(action)
        if not reply:
            continue
        child = solve.tree.nodes[child_index]
        modeled_fold = replies[child.index][child.labels.index("fold")]
        cost = villain_target - state.villain_commit
        pot = state.pot - state.hero_commit - state.villain_commit + 2 * min(hero_target, villain_target) - cost
        true_fold = np.asarray([1 - style.call_probability(h.combo, h.rank, cost, pot) for h in holdings])
        projected = normalize(repaired[ids] * present)
        responses[key] = {"cost": cost, "pot_before_call": pot,
                          "model_fold_on_model": float(modeled_fold @ projected),
                          "model_fold_on_truth": float(modeled_fold @ exact),
                          "truth_fold_on_model": float(true_fold @ projected),
                          "truth_fold_on_truth": float(true_fold @ exact),
                          "brier_excess_on_truth": float(((modeled_fold - true_fold) ** 2) @ exact)}
        if archived["delta"] < -17:
            responses[key]["by_holding_fold"] = [modeled_fold.tolist(), true_fold.tolist()]

    optimum, optimal_ev = legal_optimum(reference, state, ds, truth, style.call_probability, truth)
    result = {"board_index": case.index, "stream": stream, "prefix": prefix, "opponent": name,
              "river_response_counts": river_counts(profile.snapshot if profile else None),
              "case": asdict(case), "actions": [asdict(action) for action in spot.actions],
              "state": asdict(state), "legal_actions": list(ds.legal_actions),
              "legal_raise_bounds": [ds.minimum_legal_target, ds.maximum_legal_target],
              "range_tv": {"incumbent": float(abs(incumbent[ids] - exact).sum() / 2),
                           "repaired": float(abs(repaired[ids] - exact).sum() / 2)},
              "exact_effective": float(1 / (exact @ exact)), "omitted_truth": float(exact[~present].sum()),
              "arms": {"A": a, "B": b}, "values": truth, "delta": score(b["mix"], truth) - score(a["mix"], truth),
              "legal_optimum": [optimum, optimal_ev], "cells": cells, "responses": responses,
              "projected_tree_ev": dict(zip(keys, projected_ev.tolist(), strict=True)),
              "cfr_ev": dict(zip(keys, cfr_ev.tolist(), strict=True)), "river_iterations": iterations}
    for arm in (a, b):
        arm["ev"] = score(arm["mix"], truth)
        arm["regret"] = max(truth.values()) - arm["ev"]
    assert abs(result["delta"] - archived["delta"]) < 1e-12
    for arm, ctx in (("A", context_a), ("B", context)):
        solved, node, hero_id = ctx
        col = np.searchsorted(solved.combos[node.player], hero_id)
        result["arms"][arm]["hero_root_weight"] = float(solved.solver.ranges[node.player][col])
        result["arms"][arm]["hero_average_mass"] = float(solved.solver.strategy_sum[node.index][:, col].sum())
    if set(a["mix"]) <= set(keys):
        nominal = cells["000"]["values"]
        result["predicted_delta"] = score(b["mix"], nominal) - score(a["mix"], nominal)
    if archived["delta"] < -17:
        result["holdings"] = [{"cards": h.combo, "result": h.result, "rank": h.rank} for h in holdings]
        result["weights"] = {"incumbent": incumbent[ids].tolist(), "repaired": repaired[ids].tolist(),
                             "reference": exact.tolist(), "model_prior": prior.tolist(),
                             "model_wager": observed.tolist(), "reference_prior": ref_prior.tolist(),
                             "reference_wager": ref_observed.tolist()}
        result["columns"] = {"A": [seat.tolist() for seat in cols_a], "B": [seat.tolist() for seat in cols_b],
                             "A_advice_node": context_a[1].index, "B_advice_node": root.index}
    return result


def key(row):
    return row["board_index"], row["stream"], row["opponent"]


def historical():
    started = perf_counter()
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))["rows"]
    scheduled = {(case.index, stream, name): (case, stream, prefix, name)
                 for case, stream, prefix, name in phase_4w.schedule("holdout")}
    harmed = sorted((row for row in archive if row["delta"] < -.01), key=lambda row: row["delta"])
    assert len(harmed) == 18
    controls = [max((row for row in archive if row["closing"] == closing), key=lambda row: row["delta"])
                for closing in (False, True)]
    rows = []
    for old in harmed + controls:
        case, stream, prefix, name = scheduled[key(old)]
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        rows.append(case_diagnostic(case, stream, prefix, name, profile, old))
        print(key(old), f'{rows[-1]["delta"]:+.6f}', flush=True)
    return {"rows": rows, "peak_mib": peak_resident_bytes() / 1024 ** 2, "seconds": perf_counter() - started}


def sensitivity():
    started = perf_counter()
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))["rows"]
    original = {key(row): row for row in archive}
    # Worst nonclosing, worst closing, best nonclosing, best closing.
    selected = {key(extreme((row for row in archive if row["closing"] == closing),
                            key=lambda row: row["delta"]))
                for closing, extreme in product((False, True), (min, max))}
    rows = []
    for case, stream, prefix, name in phase_4w.schedule("holdout"):
        item_key = (case.index, stream, name)
        if item_key not in selected:
            continue
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        spot, style = case.spot(), STYLES[name]
        warm(spot)
        b, ds, posterior, _, context, _, iterations = witness(spot, "B", profile)
        state = wager_state(ds)
        reference = phase_4s.exact_reference(case, ds, style)
        ids = np.array([combo_index(h.combo) for h in reference.holdings])
        outcomes = np.array([h.result for h in reference.holdings])
        ranks = np.array([h.rank for h in reference.holdings])
        keys, transfer, _, _ = modeled_payoffs(context, ids, ranks, outcomes, ds)
        normalized = posterior[ids]
        by_combo = dict(zip((h.combo for h in reference.holdings), normalized, strict=True))
        modeled = ExactRiverEV(case.hero, case.board, lambda pair, _: by_combo[pair])
        scenario_ev = exact_values(modeled, state, keys, style.call_probability)
        truth = original[item_key]["values"]
        a_mix = original[item_key]["arms"]["A"]["mix"]

        forecasts = []
        # Replace increasing fractions of the modeled continuation EV with the
        # reference continuation EV. This is a convex mixture of reply regimes.
        baseline_ev = dict(zip(keys, (transfer @ normalized).tolist(), strict=True))
        for blend in (0., .025, .05, .10, .25, .50, 1.):
            values = {k: (1 - blend) * baseline_ev[k] + blend * scenario_ev[k] for k in keys}
            choice = greedy(values, truth)
            forecasts.append({"reference_fraction": blend, **choice, "tv": phase_4w.tv(b["mix"], choice["mix"]),
                              "exact_ev": score(choice["mix"], truth)})

        board_weights = np.ones(len(posterior))
        board_weights[ids[outcomes < 0]] = 2
        configurations = [(f"cap-{cap}-seed-{seed}", case, CFRWorkingSet(cap, seed), None, None)
                          for cap, seed in PROJECTIONS]
        configurations.extend((f"iterations-{n}", case, None, None, n)
                              for n in (max(1, iterations // 2), iterations * 4))
        configurations.extend((f"losing-odds-{odds}", case, None, board_weights ** odds, None)
                              for odds in (-1, 1))
        configurations.extend((f"depth-{d:+}", replace(case, depth=case.depth + d), None, None, None)
                              for d in (-3, 3) if case.shove or case.behind - BIG_BLIND * 3 > case.bet or d > 0)
        if case.path in ("bb_open", "limp_call"):
            configurations.append(("earlier-open-plus-50", replace(case, open_to=case.open_to + 50), None, None, None))
        elif case.shove or case.behind - 50 > case.bet + 100:
            configurations.append(("earlier-threebet-plus-50", replace(case, open_to=case.open_to + 50), None, None, None))

        variants = []
        for variant, varied_case, selection, multiplier, count in configurations:
            varied_spot = varied_case.spot()
            warm(varied_spot)
            arm, varied_ds, reach, _, (solved, root, hero), _, _ = witness(
                varied_spot, "B", profile, selection, weight_multiplier=multiplier, iterations=count)
            if varied_case == case:
                assert varied_ds == ds and np.array_equal(reach, posterior)
                varied_ref = reference
            else:
                varied_ref = phase_4s.exact_reference(varied_case, varied_ds, style)
            varied_state = wager_state(varied_ds)
            values = exact_values(varied_ref, varied_state, sorted(arm["mix"]), style.call_probability)
            phase_4w.verify_exact_payoffs(varied_ref, varied_state, values, style.call_probability)
            modeled_ev = solved.solver.action_values(root, np.searchsorted(solved.combos[root.player], hero)) / BIG_BLIND
            menu = [label(SolverBot._legalize(varied_ds, *action)) for action in root.actions]
            modeled_ev = dict(zip(menu, modeled_ev.tolist(), strict=True))
            ev = score(arm["mix"], values)
            variants.append({"variant": variant, "arm": arm, "tv": phase_4w.tv(b["mix"], arm["mix"]),
                             "predicted_ev": score(arm["mix"], modeled_ev), "predicted_values": modeled_ev,
                             "exact_ev": ev, "values": values, "regret": max(values.values()) - ev,
                             "delta_vs_nominal": ev - score(b["mix"], truth) if varied_case == case else None,
                             "delta_vs_incumbent": ev - score(a_mix, truth) if varied_case == case else None})
        action_keys = list(b["mix"])
        probabilities = np.array(list(b["mix"].values()))
        draws = {seed: action_keys[SolverBot(seed=seed)._pick(ds, probabilities)] for seed in (917, 17, 29, 53)}
        rows.append({"key": item_key, "nominal": b, "values": truth, "nominal_modeled_values": baseline_ev,
                     "chooser_seed_actions": draws,
                     "nominal_exact_ev": score(b["mix"], truth), "forecasts": forecasts, "variants": variants})
    return {"rows": rows, "peak_mib": peak_resident_bytes() / 1024 ** 2, "seconds": perf_counter() - started}


def schedule():
    orientations = [list(phase_4q.cases(FRESH_SEED, FRESH_BOARDS, i)) for i in range(len(FRESH_STREAMS))]
    for board in range(FRESH_BOARDS):
        for index, stream in enumerate(FRESH_STREAMS):
            case = orientations[index][board]
            if case.shove:
                prefix = (0, 3, 30, 100)[(board + index + board // 4) % 4]
            else:
                prefix = (3, 3, 0, 30, 3, 100)[(board // 2 + index) % 6]
            for name in STYLES:
                yield case, stream, prefix, name


def manifest():
    files = phase_4w.frozen_manifest()["sources"]
    protocol = "PHASE_4X_PROTOCOL.md"
    files[protocol] = sha256((phase_4w.REPO / protocol).read_bytes()).hexdigest()
    return {"sources": files,
            "schedule": [[asdict(case), stream, prefix, name] for case, stream, prefix, name in schedule()]}


def candidate(ds, state, a, b):
    started = perf_counter()
    mix, fraction, bound = bounded_adjustment(state, a["mix"], b["mix"], ds.big_blind)
    if not fraction:
        action = a["action"]
    elif fraction == 1.:
        action = b["action"]
    else:
        menu = list(mix)  # bounded_adjustment returns stable concrete order
        index = SolverBot(seed=917)._pick(ds, np.array(list(mix.values())))
        action = menu[index]
    assert all(np.isfinite(v) and 0 <= v <= 1 for v in mix.values()) and abs(fsum(mix.values()) - 1) < 1e-12
    for action_key in mix:
        assert_legal(ds, to_action(action_key))
    assert mix[action] > 0
    overhead = perf_counter() - started
    # Standalone replay includes every solve this policy needs.
    seconds = a["seconds"] + (b["seconds"] if fraction else 0.) + overhead
    return {"action": action, "mix": mix, "source": "fallback" if "fallback" in (a["source"], b["source"])
            else "bounded_adjustment", "seconds": seconds, "overhead_seconds": overhead,
            "fraction": fraction, "unclipped_lower_bb": bound}


def fresh_row(case, stream, prefix, name, profile, reverse):
    spot = case.spot()
    warm(spot)
    snapshot, showdown = (profile.snapshot, profile.showdown) if profile else (None, None)
    arms = {tag: phase_4w.advise(spot, tag, snapshot, showdown) for tag in ("BA" if reverse else "AB")}
    a, ds, _, _ = arms["A"]
    b, other_ds, _, _ = arms["B"]
    assert ds == other_ds and (ds.opponent_stack == 0) == case.shove
    assert all(max(columns) <= 896 for columns in b["columns"])
    state = wager_state(ds)
    c = candidate(ds, state, a, b)

    # Reference inputs are constructed only after all three policies are fixed.
    style = STYLES[name]
    reference = phase_4s.exact_reference(case, ds, style)
    values = exact_values(reference, state, sorted(a["mix"].keys() | b["mix"].keys()), style.call_probability)
    phase_4w.verify_exact_payoffs(reference, state, values, style.call_probability)
    policies = {"A": a, "B": b, "C": c}
    for policy in policies.values():
        policy["ev"] = score(policy["mix"], values)
        policy["regret"] = max(values.values()) - policy["ev"]
    adjustment = c["ev"] - a["ev"]
    if c["unclipped_lower_bb"] is not None:
        assert adjustment >= c["fraction"] * c["unclipped_lower_bb"] - 1e-12
    else:
        assert c["mix"] == a["mix"] and c["action"] == a["action"]
    return {"board_index": case.index, "stream": stream, "prefix": prefix, "opponent": name,
            "closing": case.shove, "values": values, "arms": policies,
            "delta": b["ev"] - a["ev"], "candidate_delta": adjustment}


def holdout(reverse):
    started = perf_counter()
    profiles = {(stream, name): train(name, stream, (3, 30, 100))
                for stream in FRESH_STREAMS for name in STYLES}
    rows = []
    for index, (case, stream, prefix, name) in enumerate(schedule()):
        row = fresh_row(case, stream, prefix, name, profiles[stream, name].get(prefix),
                        (index % 2 == 0) == reverse)
        rows.append(row)
        if (index + 1) % 12 == 0:
            print(f"{index + 1} paired decisions completed", flush=True)
    assert len(rows) == FRESH_BOARDS * len(FRESH_STREAMS) * len(STYLES)

    def contrast(first, second):
        # Reuse the original crossed bootstrap and gates for each comparison.
        pairs = [{**r, "arms": {"A": r["arms"][first], "B": r["arms"][second]},
                  "delta": r["arms"][second]["ev"] - r["arms"][first]["ev"]} for r in rows]
        return phase_4w.summarize(pairs)

    summary = {f"{second}-{first}": contrast(first, second) for first, second in ("AB", "AC", "BC")}
    c_gate = summary["C-A"]["gates"]
    c_gate["runtime"] &= all(row["arms"][tag]["seconds"] <= 15 for row in rows for tag in ("A", "B", "C"))
    return {"rows": rows, "summary": summary, "seconds": perf_counter() - started}


def compare(first, second):
    # Ignore measured durations and resident memory. Include every full-precision
    # policy, range, action value, projection and exact payoff.
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items()
                    if k not in {"peak_mib", "stage_seconds", "runtime", "memory"} and not k.endswith("seconds")}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    assert strip(first["rows"]) == strip(second["rows"])
    if "summary" in first:
        assert strip(first["summary"]) == strip(second["summary"])
    return {"identical_rows": len(first["rows"]),
            "runtime_gates_by_seed": [run["summary"]["C-A"]["gates"]["runtime"] for run in (first, second)]
            if "summary" in first else None,
            "memory_gates_by_seed": [run["summary"]["C-A"]["gates"]["memory"] for run in (first, second)]
            if "summary" in first else None}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["historical", "sensitivity", "freeze", "holdout", "compare"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--runs", nargs=2, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result = manifest()
    elif args.command == "holdout":
        assert args.manifest is not None
        current = json.loads(json.dumps(manifest()))
        assert current == json.loads(args.manifest.read_text(encoding="utf-8")), "frozen inputs changed"
        result = holdout(args.reverse)
    elif args.command == "compare":
        assert args.runs
        result = compare(*(json.loads(path.read_text(encoding="utf-8")) for path in args.runs))
    else:
        result = historical() if args.command == "historical" else sensitivity()
    phase_4s.write_json(args.output, result)


if __name__ == "__main__":
    main()
