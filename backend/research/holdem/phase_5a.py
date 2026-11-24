"""Offline comparison of river action values with explicit opponent inputs."""
from argparse import ArgumentParser
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations
import json
from math import ceil, fsum
import os
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import NamedTuple

import numpy as np

from coach.service import SpotAction
from research.holdem import action_ev_reference as ledger, phase_4q, phase_4x, phase_4y, phase_4z
from research.holdem.phase_4k import STYLES, label, peak_resident_bytes, to_action, train
from research.holdem.reply_forecast import holding_values
from research.holdem.river_ev import ExactRiverEV, RiverState
from solver.bot import SolverBot, _full_equity
from solver.combos import combo_index
from solver.cfr import RangeSolver
from solver.tree import SizeMenu, StreetState, StreetTree


REPO = phase_4z.REPO
BOARD_SEED, BOARD_COUNT = 550_202, 6
STREAMS, PREFIXES = (541, 542, 543), (0, 3, 30, 100)
EPS, CAP, ITERATIONS = .01, 896, 80
MENU = SizeMenu(((.25, .5, .8, 1., 1.5), (.5, 1.), (1.,)), all_in_merge=1.)


def schedule(seed=BOARD_SEED, count=BOARD_COUNT, streams=STREAMS):
    cases = [list(phase_4q.cases(seed, count, i)) for i in range(4)]
    for board in range(count):
        for i, stream in enumerate(streams):
            mode = ("checked", "live", "closing")[(board + i) % 3]
            case = cases[i][board]
            if mode == "checked" and case.seat != "button":
                case = cases[i + 1][board]
            if mode == "live" and case.behind <= case.pot // 2:
                case = replace(case, depth=30)
            case = replace(case, shove=mode == "closing", pot_wager=False)
            for name in STYLES:
                yield case, mode, stream, PREFIXES[(board + i) % len(PREFIXES)], name


def manifest():
    # Include the source and fixed solver artifacts already tracked by the 4Z audit.
    hashes = phase_4z.manifest()["sources"]
    path = "PHASE_5A_PROTOCOL.md"
    hashes[path] = sha256((REPO / path).read_bytes()).hexdigest()
    return {"sources": hashes, "schedule": [asdict(case) | {
        "mode": mode, "stream": stream, "prefix": prefix, "opponent": name,
    } for case, mode, stream, prefix, name in schedule()]}


class FixedPolicySolver(RangeSolver):
    """Exercise production DCFR and action_values with explicit per-holding locks.

    Every continuation is supplied. Only the actual Hero's root policy learns.
    The equivalent one-row matchup avoids solving irrelevant Hero holdings.
    """

    def __init__(self, tree, root, weights, outcomes, replies, tail):
        hero = root.player
        ranges = (np.ones(1), weights) if hero == 0 else (weights, np.ones(1))
        d = outcomes[None, :] if hero == 0 else -outcomes[:, None]
        super().__init__(tree, ranges, d, np.ones_like(d))
        self.continuations = replies | {idx: probs[:, None] for idx, probs in tail.items()}

    def policy(self, base):
        return {node.index: self.continuations[node.index] if node.index in self.continuations else base(node)
                for node in self.decisions}


def project(weights, cap):
    ordered = np.argsort(-weights, kind="stable")
    return np.sort(ordered[:min(cap, np.count_nonzero(weights))])


def cfr_values(tree, weights, outcomes, replies, tail, ids, iterations):
    root = tree.nodes[tree.root]
    solver = FixedPolicySolver(tree, root, weights[ids] / weights[ids].sum(), outcomes[ids],
                               {idx: probs[:, ids] for idx, probs in replies.items()}, tail)
    result = solver.solve(iterations)
    return solver.action_values(root, 0), result.average[root.index][:, 0]


def exact_subset(tree, root, state, keys, field, weights, replies):
    """Scope B to terminal actions and immediate fold/call-only responses."""
    weights_by_combo = dict(zip((hand.combo for hand in field.holdings), weights, strict=True))
    exact = ExactRiverEV(field.hero, field.board, lambda combo, _: weights_by_combo[combo])
    holding_index = {hand.combo: i for i, hand in enumerate(field.holdings)}
    values = {}
    for key, child in zip(keys, root.children, strict=True):
        node = tree.nodes[child]
        action = to_action(key)
        if node.kind != "decision":
            values[key] = exact.action_ev(state, action)
            continue
        if node.player == root.player or not {"fold", "call"} <= set(node.labels):
            continue
        call = replies[child][node.labels.index("call")]
        other = [i for i, name in enumerate(node.labels) if name not in ("fold", "call")]
        if np.any(replies[child][other][:, weights > 0] > 0):
            continue
        values[key] = exact.action_ev(state, action, lambda combo, *_: call[holding_index[combo]])
    return values


def validate_reply(node, probabilities, holdings):
    assert probabilities.shape == (len(node.actions), holdings)
    phase_4y.grouped(node, probabilities)


def branch_values(tree, root, state, outcomes, replies, tail, verify=True):
    candidate = holding_values(tree, root, outcomes, replies, tail, state.odd_chip)
    if verify:
        reference = ledger.evaluate_tree(tree, root, state, outcomes, replies, tail)
        np.testing.assert_allclose(candidate, reference, rtol=0, atol=1e-9)
    return candidate


def measure(keys, predictions, truth, baseline, probabilities=None, ds=None):
    pred = {key: float(value) for key, value in predictions.items()}
    actual = dict(zip(keys, map(float, truth), strict=True))
    order = sorted(pred, key=lambda key: (-pred[key], key))
    if not order:
        return {"actions": {}, "pairs": [], "best": None, "choices": {}}
    best = min(pred, key=lambda key: (-actual[key], key))
    best_full = min(actual, key=lambda key: (-actual[key], key))
    actions = {}
    true_ranks = {key: rank for rank, key in enumerate(sorted(pred, key=lambda a: (-actual[a], a)), 1)}
    for rank, key in enumerate(order, 1):
        actions[key] = {"predicted": pred[key], "actual": actual[key], "error": pred[key] - actual[key],
                        "rank": rank, "true_rank": true_ranks[key],
                        "pred_advantage": pred[key] - pred[baseline] if baseline in pred else None,
                        "true_advantage": actual[key] - actual[baseline],
                        "regret": actual[best] - actual[key], "full_menu_regret": actual[best_full] - actual[key]}
    choices = {"greedy": order[0]}
    if probabilities is not None:
        assert np.all(np.asarray(probabilities) >= 0) and abs(fsum(probabilities) - 1) < 1e-12
        choices["mode"] = min(zip(keys, probabilities, strict=True), key=lambda row: (-row[1], row[0]))[0]
        choices["seeded"] = keys[SolverBot(seed=917)._pick(ds, probabilities)]
        mix = fsum(p * actual[k] for k, p in zip(keys, probabilities, strict=True))
    else:
        # The exact evaluators recommend a pure EV maximizer.
        choices.update(mode=order[0], seeded=order[0])
        mix = actual[order[0]]
    return {"actions": actions, "pairs": phase_4z.rankings(pred, {k: actual[k] for k in pred}),
            "best": best, "full_best": best_full, "choices": choices, "mix_ev": mix,
            "mix_regret": actual[best_full] - mix,
            "probabilities": dict(zip(keys, map(float, probabilities), strict=True)) if probabilities is not None else None}


def known_model(ds, state, field, style, baseline, reverse=False):
    tree = StreetTree(state, MENU)
    root = tree.nodes[tree.root]
    keys = concrete_keys(ds, root)
    g = ledger.root_ledger(ds, root.player)
    nodes = list(phase_4z.continuation_nodes(tree, root))
    weights = np.asarray([hand.weight for hand in field.holdings])
    outcomes = np.asarray([hand.result for hand in field.holdings])
    replies = {n.index: ledger.reference_reply(n, field.holdings, style) for n in nodes if n.player != root.player}
    # Fix Hero tails in both comparator and reference. Calling also exercises
    # the settlement of every positive-probability raised branch.
    tail = {n.index: np.asarray([float(k == "call") for k in n.labels]) for n in nodes if n.player == root.player}
    for node in nodes:
        if node.player != root.player:
            validate_reply(node, replies[node.index], len(weights))
        else:
            assert tail[node.index].sum() == 1
    bb = ds.big_blind
    truth = ledger.evaluate_tree(tree, root, g, outcomes, replies, tail) @ weights / bb
    rstate = replace(phase_4x.wager_state(ds), checked_to=ds.amount_to_call == 0)
    ids = project(weights, CAP)
    operations = {
        "A": lambda: cfr_values(tree, weights, outcomes, replies, tail, ids, ITERATIONS),
        "B": lambda: exact_subset(tree, root, rstate, keys, field, weights, replies),
        "C": lambda: branch_values(tree, root, g, outcomes, replies, tail, verify=False) @ weights,
    }
    evaluated, timings = timed(operations, reverse)
    raw, probabilities = evaluated["A"]
    full, _ = cfr_values(tree, weights, outcomes, replies, tail, project(weights, len(weights)), 0)
    projected = ledger.evaluate_tree(tree, root, g, outcomes, replies, tail)[:, ids] @ (weights[ids] / weights[ids].sum())
    numerical = float(max(abs(raw - projected)) / bb)
    assert numerical < 1e-4 and max(abs(full / bb - truth)) < 1e-4
    arms = {
        "A": measure(keys, phase_4z.values_dict(keys, raw / bb), truth, baseline, probabilities, ds),
        "B": measure(keys, {k: v / bb for k, v in evaluated["B"].items()}, truth, baseline),
        "C": measure(keys, phase_4z.values_dict(keys, evaluated["C"] / bb), truth, baseline),
    }
    for arm in ("B", "C"):
        assert all(abs(rec["error"]) < 1e-10 for rec in arms[arm]["actions"].values())
    return {"arms": arms, "categories": categories(tree, root, keys), "times": timings,
            "numerical_max": numerical, "full_numerical_max": float(max(abs(full / bb - truth))),
            "max_projection_shift": float(max(abs(projected / bb - truth))),
            "omitted_mass": float(1 - weights[ids].sum()), "columns": [1, len(ids)], "nodes": len(tree.nodes),
            "baseline": baseline, "oracle_weights": weights.tolist(),
            "wager_targets": dict(zip(keys, (target for _, target in root.actions), strict=True))}


def concrete_keys(ds, root):
    actions = [SolverBot._legalize(ds, *action) for action in root.actions]
    for action in actions:
        phase_4y.phase_4w.assert_legal(ds, action)
    keys = [label(action) for action in actions]
    assert len(keys) == len(set(keys))
    return keys


def categories(tree, root, keys):
    return {key: phase_4z.category(key, tree.nodes[child])
            for key, child in zip(keys, root.children, strict=True)}


def timed(operations, reverse):
    values, seconds = {}, {}
    for key in reversed(operations) if reverse else operations:
        start = perf_counter()
        values[key] = operations[key]()
        seconds[key] = perf_counter() - start
    return values, seconds


def estimated_model(ds, policy, posterior, context, field, style, mismatch, reverse=False):
    solved, root, hero_id = context
    tree, hero = solved.tree, root.player
    column = int(np.searchsorted(solved.combos[hero], hero_id))
    keys, _, present, replies = phase_4x.modeled_payoffs(context, field.ids, field.ranks, field.outcomes, ds)
    assert keys == concrete_keys(ds, root)
    g = ledger.root_ledger(ds, hero)
    assert g.totals == root.state.commit and g.cash == root.state.stack
    nodes = list(phase_4z.continuation_nodes(tree, root))
    villain_nodes = [n for n in nodes if n.player != hero]
    inferred = {n.index: replies[n.index] for n in villain_nodes}
    specified = {n.index: ledger.reference_reply(n, field.reference.holdings, style) for n in villain_nodes}
    for n in villain_nodes:
        validate_reply(n, inferred[n.index], len(field.ids))
        validate_reply(n, specified[n.index], len(field.ids))
    tail = {n.index: solved.average[n.index][:, column] for n in nodes if n.player == hero}
    for probs in tail.values():
        assert np.all(probs >= 0) and abs(fsum(probs) - 1) < 1e-12
    weights, oracle = posterior[field.ids], field.weights
    assert abs(weights.sum() - 1) < 1e-12
    retained = phase_4x.normalize(weights * present)
    rstate = replace(phase_4x.wager_state(ds), checked_to=ds.amount_to_call == 0)
    bench_field = RiverField(tuple(ds.hole_cards), tuple(ds.board_cards), field.reference.holdings)
    results, times = timed({
        "A": lambda: solved.solver.action_values(root, column),
        "B": lambda: exact_subset(tree, root, rstate, keys, bench_field, weights, inferred),
        "C": lambda: branch_values(tree, root, g, field.outcomes, inferred, tail, verify=False),
    }, reverse)
    bb = ds.big_blind
    raw, partial, predicted = results["A"] / bb, results["B"], results["C"] / bb
    # The independent terminal ledger is authoritative in all four model cells.
    true = ledger.evaluate_tree(tree, root, g, field.outcomes, specified, tail) / bb
    check = ledger.evaluate_tree(tree, root, g, field.outcomes, inferred, tail) / bb
    np.testing.assert_allclose(predicted, check, atol=1e-10, rtol=0)
    cells = {"estimated": predicted @ weights, "oracle_range": predicted @ oracle,
             "oracle_replies": true @ weights, "both": true @ oracle, "projected": predicted @ retained}
    numerical = float(max(abs(cells["projected"] - raw)))
    assert numerical < 1e-4
    base = policy["action"]
    probabilities = solved.average[root.index][:, column]
    truth = cells["both"]
    arms = {
        "A": measure(keys, phase_4z.values_dict(keys, raw), truth, base, probabilities, ds),
        "B": measure(keys, {k: v / bb for k, v in partial.items()}, truth, base),
        "C": measure(keys, phase_4z.values_dict(keys, cells["estimated"]), truth, base),
    }
    alternate_field, alternate_style = mismatch
    assert np.array_equal(alternate_field.ids, field.ids)
    alternate_law = {n.index: ledger.reference_reply(n, alternate_field.reference.holdings, alternate_style)
                     for n in villain_nodes}
    for n in villain_nodes:
        validate_reply(n, alternate_law[n.index], len(field.ids))
    alternate = ledger.evaluate_tree(tree, root, g, field.outcomes, alternate_law, tail) @ alternate_field.weights / bb
    mismatched = {
        "A": measure(keys, phase_4z.values_dict(keys, raw), alternate, base, probabilities, ds),
        "B": measure(keys, {k: v / bb for k, v in partial.items()}, alternate, base),
        "C": measure(keys, phase_4z.values_dict(keys, cells["estimated"]), alternate, base),
    }
    for k, v in partial.items():
        assert abs(v / bb - cells["estimated"][keys.index(k)]) < 1e-10
    assert arms["A"]["choices"]["seeded"] == base
    assert [round(v * bb, 1) for v in raw] == policy["action_ev"]
    return {"arms": arms, "categories": categories(tree, root, keys), "times": times,
            "cells": {name: phase_4z.values_dict(keys, values) for name, values in cells.items()},
            "numerical_max": numerical, "estimated_weights": weights.tolist(), "baseline": base,
            "range_tv": float(abs(weights - oracle).sum() / 2), "nodes": len(tree.nodes),
            "mismatched": mismatched, "advisor": policy}


class RiverField(NamedTuple):
    hero: tuple
    board: tuple
    holdings: tuple


def case_row(case, mode, stream, prefix, name, profile, reverse=False, cold=False):
    spot = case.spot()
    if mode == "checked":
        spot.actions[-1] = SpotAction("villain", "check")
    cold_seconds = phase_4x.witness(spot, "A", profile)[0]["seconds"] if cold else None
    phase_4x.warm(spot)
    policy, ds, posterior, _, context, _, _ = phase_4x.witness(spot, "A", profile)
    assert policy["seconds"] <= 15 and (cold_seconds is None or cold_seconds <= 15)
    style = STYLES[name]
    mismatch_name = dict(zip(STYLES, reversed(STYLES), strict=True))[name]
    mismatch_style = STYLES[mismatch_name]
    exact = phase_4z.reference(case, ds, style)
    field = phase_4y.Field(exact)
    mismatch_field = phase_4y.Field(phase_4z.reference(case, ds, mismatch_style))
    assert len(set(field.ids)) == 990 and abs(field.weights.sum() - 1) < 1e-12
    ids, showdown, _ = _full_equity(case.board, SolverBot.flop_runouts)
    production = showdown[np.searchsorted(ids, combo_index(case.hero)), np.searchsorted(ids, field.ids)]
    np.testing.assert_array_equal(production, field.outcomes)
    known = known_model(ds, context[1].state, RiverField(case.hero, case.board, exact.holdings),
                        style, policy["action"], reverse)
    estimated = estimated_model(ds, policy, posterior, context, field, style,
                                (mismatch_field, mismatch_style), reverse)
    common = set(estimated["arms"]["A"]["actions"])
    expanded = known["arms"]["C"]["actions"]
    assert common <= expanded.keys()
    sizing = max(r["actual"] for r in expanded.values()) - max(expanded[k]["actual"] for k in common)
    # A pure bluff has zero winning or tying mass against the calling range.
    # Report natural opportunity under a fold/call-only reduction separately.
    pure = {}
    tree = StreetTree(context[1].state, MENU)
    root = tree.nodes[tree.root]
    known_field = RiverField(case.hero, case.board, exact.holdings)
    rstate = replace(phase_4x.wager_state(ds), checked_to=ds.amount_to_call == 0)
    default = "check" if ds.amount_to_call == 0 else "fold"
    for key, child in zip(concrete_keys(ds, root), root.children, strict=True):
        node = tree.nodes[child]
        if node.kind != "decision":
            continue
        call = ledger.reference_reply(node, known_field.holdings, style, False)[node.labels.index("call")]
        if float((field.weights * call)[field.outcomes >= 0].sum()) == 0:
            ev = exact.action_ev(rstate, to_action(key), style.call_probability) / ds.big_blind
            pure[key] = ev - expanded[default]["actual"]
    return {"board": case.index, "stream": stream, "prefix": prefix, "mode": mode, "opponent": name,
            "mismatch": mismatch_name, "case": asdict(case), "history": [asdict(a) for a in spot.actions],
            "ledger": asdict(ledger.root_ledger(ds, context[1].player)), "effective_stack": ds.effective_stack,
            "native_legal": list(ds.legal_actions), "native_target_bounds": [ds.minimum_legal_target, ds.maximum_legal_target],
            "known": known, "estimated": estimated, "cold_advisor_seconds": cold_seconds,
            "sizing_gap": sizing, "natural_bluffs": pure, "holding_ids": field.ids.tolist()}


def aggregate(records):
    actions = [row for data in records for row in data["actions"].values()]
    pairs = [ok for data in records for ok in data["pairs"]]
    positives = [row for row in actions if row["pred_advantage"] is not None and row["pred_advantage"] > EPS]
    outcomes = {}
    for choice in ("greedy", "mode", "seeded"):
        chosen = [record["actions"][record["choices"][choice]] for record in records if record["choices"]]
        if chosen:
            outcomes[choice] = {"ev": mean(a["actual"] for a in chosen),
                                "supported_regret": mean(a["regret"] for a in chosen),
                                "regret": mean(a["full_menu_regret"] for a in chosen),
                                "max_regret": max(a["full_menu_regret"] for a in chosen),
                                "worst_delta": min(a["true_advantage"] for a in chosen),
                                "harmful": sum(a["true_advantage"] < -EPS for a in chosen),
                                "suboptimal": sum(a["full_menu_regret"] > EPS for a in chosen)}
    return {"rows": len(records), "actions": len(actions),
            "mae": mean(abs(row["error"]) for row in actions) if actions else None,
            "pairs": len(pairs), "ranking": mean(pairs) if pairs else None,
            "false_positive": sum(a["true_advantage"] <= EPS for a in positives),
            "positive": len(positives), "choices": outcomes,
            "mixed_ev": mean(r["mix_ev"] for r in records if r["choices"]),
            "mixed_regret": mean(r["mix_regret"] for r in records if r["choices"])}


def distribution(values):
    return [median(values), sorted(values)[ceil(.95 * len(values)) - 1], max(values)]


def crossed_interval(rows, values):
    """Resample boards and streams as crossed clusters, keeping styles paired."""
    lookup = {(r["board"], r["stream"], r["opponent"]): v for r, v in zip(rows, values, strict=True)}
    cell = np.array([[mean(lookup[b, s, style] for style in STYLES) for s in STREAMS] for b in range(BOARD_COUNT)])
    rng = np.random.default_rng(55003)
    boards = rng.integers(BOARD_COUNT, size=(10000, BOARD_COUNT, 1))
    streams = rng.integers(len(STREAMS), size=(10000, 1, len(STREAMS)))
    return np.quantile(cell[boards, streams].mean(axis=(1, 2)), [.025, .975]).tolist()


def summarize(rows):
    views = {"known": [r["known"]["arms"] for r in rows],
             "estimated": [r["estimated"]["arms"] for r in rows],
             "mismatched": [r["estimated"]["mismatched"] for r in rows]}
    summary = {mode: {arm: aggregate([a[arm] for a in view]) for arm in "ABC"} for mode, view in views.items()}
    stratified, common = {}, {}
    for mode, view in views.items():
        category_source = "known" if mode == "known" else "estimated"
        by_size = {}
        for arm in "ABC":
            for row, record in zip(rows, view, strict=True):
                for key, result in record[arm]["actions"].items():
                    bucket = row[category_source]["categories"][key]
                    by_size.setdefault(bucket, {}).setdefault(arm, []).append(abs(result["error"]))
        stratified[mode] = {"size": {k: {a: [len(v), mean(v)] for a, v in arms.items()} for k, arms in by_size.items()},
                            "style": {k: {a: aggregate([v[a] for r, v in zip(rows, view, strict=True)
                                                        if r["opponent"] == k]) for a in "ABC"} for k in STYLES},
                            "prefix": {p: {a: aggregate([v[a] for r, v in zip(rows, view, strict=True)
                                                         if r["prefix"] == p]) for a in "ABC"} for p in PREFIXES}}
        common[mode] = {}
        for a in "ABC":
            same = [[record[a]["actions"][k] for k in record["B"]["actions"]] for record in view]
            correct = [phase_4z.sign(x["predicted"] - y["predicted"]) == phase_4z.sign(x["actual"] - y["actual"])
                       for group in same for x, y in combinations(group, 2) if phase_4z.sign(x["actual"] - y["actual"])]
            common[mode][a] = {"mae": mean(abs(x["error"]) for group in same for x in group),
                               "ranking": mean(correct), "pairs": len(correct)}
    attribution = {name: [] for name in ("estimated", "oracle_range", "oracle_replies", "interaction", "projection")}
    for row in rows:
        cells = row["estimated"]["cells"]
        for key, true in cells["both"].items():
            for cell in ("estimated", "oracle_range", "oracle_replies"):
                attribution[cell].append(abs(cells[cell][key] - true))
            attribution["interaction"].append(abs(true - cells["oracle_range"][key] -
                                                  cells["oracle_replies"][key] + cells["estimated"][key]))
            attribution["projection"].append(abs(cells["projected"][key] - cells["estimated"][key]))
    intervals = {}
    for mode, view in views.items():
        intervals[mode] = {}
        for arm in "ABC":
            regret = [v[arm]["actions"][v[arm]["choices"]["seeded"]]["full_menu_regret"] for v in view]
            mae = [mean(abs(r["error"]) for r in v[arm]["actions"].values()) for v in view]
            vs_a = [v["A"]["actions"][v["A"]["choices"]["seeded"]]["full_menu_regret"] - r
                    for v, r in zip(view, regret, strict=True)]
            intervals[mode][arm] = {"decision_mae": crossed_interval(rows, mae),
                                    "seeded_regret": crossed_interval(rows, regret),
                                    "gain_vs_A_seeded": crossed_interval(rows, vs_a)}
    return {"arms": summary, "strata": stratified, "B_shared_support": common, "intervals_95": intervals,
            "attribution_mae_bb": {k: mean(v) for k, v in attribution.items()},
            "max_numerical_bb": {m: max(r[m]["numerical_max"] for r in rows) for m in ("known", "estimated")},
            "max_full_numerical_bb": max(r["known"]["full_numerical_max"] for r in rows),
            "max_projection_bb": max(r["known"]["max_projection_shift"] for r in rows),
            "max_omitted_mass": max(r["known"]["omitted_mass"] for r in rows),
            "range_tv": mean(r["estimated"]["range_tv"] for r in rows),
            "size_gap_bb": [mean(r["sizing_gap"] for r in rows), max(r["sizing_gap"] for r in rows)],
            "natural_bluffs": {"profitable": sum(v > EPS for r in rows for v in r["natural_bluffs"].values()),
                               "unprofitable": sum(v < -EPS for r in rows for v in r["natural_bluffs"].values())},
            "timings": {mode: {a: distribution([r[mode]["times"][a] for r in rows]) for a in "ABC"}
                        for mode in ("known", "estimated")},
            "advisor_time": distribution([r["estimated"]["advisor"]["seconds"] for r in rows])}


def canonical(value):
    return json.loads(json.dumps(value, allow_nan=False))


def write(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)


def run(output, panel, reverse):
    rows, trained = [], {}
    with output.with_suffix(".jsonl").open("x", encoding="utf-8") as log:
        for index, (case, mode, stream, prefix, name) in enumerate(panel):
            log.write(json.dumps({"attempted": index, "board": case.index, "stream": stream, "opponent": name}) + "\n")
            log.flush()
            if prefix and (name, stream) not in trained:
                trained[name, stream] = train(name, stream, PREFIXES[1:])
            profile = trained[name, stream][prefix] if prefix else None
            row = case_row(case, mode, stream, prefix, name, profile, reverse ^ bool(index % 2), cold=index == 0)
            rows.append(row)
            log.write(json.dumps(row, allow_nan=False) + "\n")
            log.flush()
    return rows


def benchmark(arm):
    """Fresh process per evaluator. Precomputed holding order and response law."""
    start = perf_counter()
    hero, board = ("3c", "5c"), ("2c", "4d", "7h", "9s", "Jc")
    exact = ExactRiverEV(hero, board, lambda *_: 1.)
    field = RiverField(hero, board, exact.holdings)
    outcomes = np.array([h.result for h in field.holdings])
    tree = StreetTree(StreetState("river", 0, (0, 0), (2500, 2500), (250, 250), 100, (False, True)), MENU)
    root = tree.nodes[tree.root]
    nodes = list(phase_4z.continuation_nodes(tree, root))
    replies = {n.index: ledger.reference_reply(n, field.holdings, STYLES["loose_passive"])
               for n in nodes if n.player != 0}
    tail = {n.index: np.array([float(k == "call") for k in n.labels]) for n in nodes if n.player == 0}
    g = ledger.Ledger(500, (0, 0), (2500, 2500), 0, True)
    rstate = RiverState(500, 0, 0, 2500, 2500, 100, checked_to=True, hero_gets_odd_chip=True)
    setup = perf_counter() - start
    results = {}
    for size in (990, 1, 32, 128, 384, 896):
        ids = np.arange(size)
        weights = np.full(size, 1 / size)
        scatter = np.pad(weights, (0, len(outcomes) - size))
        laws = {idx: law[:, ids] for idx, law in replies.items()}
        operations = {
            "A": lambda: cfr_values(tree, scatter, outcomes, replies, tail, ids, ITERATIONS),
            "B": lambda: exact_subset(tree, root, rstate, root.labels, field, scatter, replies),
            "C": lambda: branch_values(tree, root, g, outcomes[ids], laws, tail, verify=False) @ weights,
        }
        durations = []
        for _ in range(9):
            start = perf_counter()
            operations[arm]()
            durations.append(perf_counter() - start)
        results[size] = {"first": durations[0], "warmed": distribution(durations[1:])}
    return {"arm": arm, "setup_seconds": setup, "ranges": results, "peak_bytes": peak_resident_bytes(),
            "nodes": len(tree.nodes)}


def stable(report):
    """Exclude measured resource fields from an otherwise exact comparison."""
    report.pop("hash_seed")
    report.pop("peak_bytes")
    summary = report["summary"]
    summary.pop("advisor_time")
    summary.pop("timings")
    for row in report["rows"]:
        row.pop("cold_advisor_seconds")
        for mode in ("known", "estimated"):
            row[mode].pop("times")
        row["estimated"]["advisor"].pop("seconds")
    return report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "development", "holdout", "benchmark", "compare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--arm", choices=tuple("ABC"))
    parser.add_argument("--runs", nargs=2, type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        write(args.output, manifest())
        return
    if args.mode == "benchmark":
        if args.arm is None:
            parser.error("benchmark requires --arm")
        write(args.output, benchmark(args.arm))
        return
    if args.mode == "compare":
        if args.runs is None:
            parser.error("compare requires --runs")
        left, right = (stable(json.loads(path.read_text(encoding="utf-8"))) for path in args.runs)
        assert left == right
        write(args.output, {"stable": True, "rows": len(left["rows"])})
        return
    if args.mode == "holdout":
        if args.manifest is None or json.loads(args.manifest.read_text(encoding="utf-8")) != canonical(manifest()):
            parser.error("holdout requires the unchanged frozen input manifest")
        panel = schedule()
    else:
        panel = schedule(550_201, 2, (531, 532, 533))
    rows = run(args.output, panel, args.reverse)
    peak = peak_resident_bytes()
    write(args.output, {"rows": rows, "summary": summarize(rows) if args.mode == "holdout" else None,
                        "peak_bytes": peak, "hash_seed": os.environ.get("PYTHONHASHSEED")})
    assert peak <= 768 * 1024**2


if __name__ == "__main__":
    main()
