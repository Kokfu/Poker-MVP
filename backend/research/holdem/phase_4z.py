"""Frozen, offline river action-value audit. No policy is installed or promoted."""
from argparse import ArgumentParser
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations
import json
from math import fsum
import os
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from unittest.mock import patch

import numpy as np

from coach.service import SpotAction
from research.holdem import action_ev_reference as ledger, phase_4p, phase_4q, phase_4t, phase_4x, phase_4y
from research.holdem.decoupled_replay import CFRWorkingSet, hand_tiers
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, to_action, train
from research.holdem.reply_forecast import (REPLY_MODELS, ResponseAssumptions, forecast,
                                          holding_values, reply_geometry, river_counts)
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import Opening, hand_group
from research.holdem.river_wager_reference import law
from solver.bot import SolverBot, _full_equity, replay_hand
from solver.combos import combo_index
from solver.tree import SizeMenu


BOARD_SEED = 450_202
BOARD_COUNT = 6
STREAMS = (341, 342, 343)
PREFIXES = (0, 3, 30, 100)
EPS = .01
EXPANDED = SizeMenu(((.25, .5, .75, 1., 1.5), (1.,)), all_in_merge=1.)
REPO = phase_4y.phase_4w.REPO


def schedule():
    cases = [list(phase_4q.cases(BOARD_SEED, BOARD_COUNT, i)) for i in range(4)]
    for board in range(BOARD_COUNT):
        for i, stream in enumerate(STREAMS):
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
    paths = list((REPO / "backend").glob("*.py"))
    for package in ("coach", "research", "solver", "simulation"):
        paths.extend((REPO / "backend" / package).rglob("*.py"))
    paths.extend((REPO / "backend" / "solver" / "data").glob("*"))
    paths.extend(REPO / file for file in ("PHASE_4Z_PROTOCOL.md", "backend/requirements.txt"))
    schedule_rows = [[asdict(case), mode, stream, prefix, name]
                     for case, mode, stream, prefix, name in schedule()]
    return {
        "sources": {p.relative_to(REPO).as_posix(): sha256(p.read_bytes()).hexdigest()
                    for p in sorted(paths) if p.is_file()},
        "schedule": json.loads(json.dumps(schedule_rows)),
    }


def reference(case, ds, style):
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    steps = [step for step in replay.steps if step.player == villain]
    universe = ExactRiverEV(case.hero, case.board, lambda *_: 1.)
    pairs = [h.combo for h in universe.holdings]
    preflop = tuple(phase_4p.observations(replay, villain, case.seat == "button"))
    weights = phase_4p.reference_weights(pairs, preflop, case.depth, style)
    for step in steps:
        if step.street in ("flop", "turn"):
            board = list(case.board[:3 if step.street == "flop" else 4])
            weights *= [phase_4p.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                        for pair in pairs]
        elif step.street == "river":
            s = step.before
            opening = Opening(s.pot, s.stack[villain], s.stack[1 - villain],
                              s.last_full_raise, case.line[1] != "check")
            observed = 0 if step.kind == "check" else opening.action(step.target)[0]
            weights *= [law(opening, hand_group(h.combo, case.board, h.rank), style)[observed]
                        for h in universe.holdings]
    mass = dict(zip(pairs, weights, strict=True))
    return ExactRiverEV(case.hero, case.board, lambda pair, _: mass[pair])


def continuation_nodes(tree, root):
    pending = list(root.children)
    while pending:
        node = tree.nodes[pending.pop()]
        pending.extend(node.children)
        if node.kind == "decision":
            yield node


def values_dict(keys, vector):
    return dict(zip(keys, np.asarray(vector).tolist(), strict=True))


def sign(value):
    return int(value > EPS) - int(value < -EPS)


def rankings(values, truth):
    return [sign(values[a] - values[b]) == sign(truth[a] - truth[b])
            for a, b in combinations(truth, 2) if sign(truth[a] - truth[b])]


def category(action, child):
    if child.kind == "decision":
        g = reply_geometry(child.state)
        ratio = g.cost / g.pot_before_wager
        if g.cost == g.effective_stack:
            return "closing_shove"
        return "small" if ratio <= .33 else "medium" if ratio < .75 else "large" if ratio < 1 else "pot" if ratio == 1 else "overbet"
    return "cover" if action == "all_in" else action


def audit(replay, field, ds, style, baseline, snapshot, prior=None, sensitivity=None, detailed=False):
    policy, _, posterior, _, context, _, _ = replay
    solved, root, hero_id = context
    tree, hero = solved.tree, root.player
    col = int(np.searchsorted(solved.combos[hero], hero_id))
    raw = solved.solver.action_values(root, col) / BIG_BLIND
    keys, model, present, replies = phase_4x.modeled_payoffs(context, field.ids, field.ranks, field.outcomes, ds)
    assert len(keys) == len(set(keys)) and baseline in keys and set(keys) == set(policy["mix"])
    probabilities = solved.average[root.index][:, col]
    assert keys[SolverBot(seed=917)._pick(ds, probabilities)] == policy["action"]
    assert [round(float(v * BIG_BLIND), 1) for v in raw] == policy["action_ev"]
    assert abs(fsum(policy["mix"].values()) - 1) <= 1e-12
    weights = posterior[field.ids]
    projected = phase_4x.normalize(weights * present)
    g = ledger.root_ledger(ds, hero)
    assert g.totals == root.state.commit and g.cash == root.state.stack
    nodes = list(continuation_nodes(tree, root))
    villain_nodes = [node for node in nodes if node.player != hero]
    tail = {node.index: solved.average[node.index][:, col] for node in nodes if node.player == hero}
    model_replies = {node.index: replies[node.index] for node in villain_nodes}
    true_replies = {node.index: ledger.reference_reply(node, field.reference.holdings, style)
                    for node in villain_nodes}
    plain = {node.index: ledger.reference_reply(node, field.reference.holdings, style, allow_raise=False)
             for node in villain_nodes}
    for node in villain_nodes:
        for law_ in (model_replies, true_replies, plain):
            phase_4y.grouped(node, law_[node.index])

    def evaluate(law_):
        values = ledger.evaluate_tree(tree, root, g, field.outcomes, law_, tail)
        np.testing.assert_allclose(values, holding_values(tree, root, field.outcomes, law_, tail,
                                                          g.odd_chip), rtol=0, atol=1e-9)
        return values / BIG_BLIND

    np.testing.assert_allclose(evaluate(model_replies), model, rtol=0, atol=1e-10)
    truth = evaluate(true_replies)
    full_plain = evaluate(plain) @ field.weights
    state = replace(phase_4x.wager_state(ds), checked_to=ds.amount_to_call == 0)
    for key, expected in zip(keys, full_plain, strict=True):
        exact = field.reference.action_ev(state, to_action(key), style.call_probability) / BIG_BLIND
        assert abs(exact - expected) < 1e-10, (key, exact, expected)
    cells = dict(zip("ABCD", (model @ weights, model @ field.weights,
                             truth @ weights, truth @ field.weights), strict=True))

    # Exploratory envelope based on public inputs, with no oracle vertices.
    ranges = np.array([weights, projected, np.full(len(weights), 1 / len(weights)),
                       weights if prior is None else phase_4x.normalize(prior[field.ids])])
    legal_ids, tiers = hand_tiers(tuple(ds.board_cards))
    tiers = tiers[np.searchsorted(legal_ids, field.ids)]
    assumptions = ResponseAssumptions.from_counts(*river_counts(snapshot))
    vertices = [raw, *(model @ ranges.T).T]
    if villain_nodes:
        for model_id in REPLY_MODELS:
            alternate = {node.index: forecast(node, tiers, assumptions, model_id) for node in villain_nodes}
            vertices.extend((ledger.evaluate_tree(tree, root, g, field.outcomes, alternate, tail) @
                             ranges.T / BIG_BLIND).T)
    if sensitivity is not None:
        vertices.append([sensitivity[k] for k in keys])
    base = keys.index(baseline)
    delta_vertices = np.asarray(vertices) - np.asarray(vertices)[:, base, None]
    actual = values_dict(keys, cells["D"])
    selected = phase_4y.action_risk(policy, actual, {"action": baseline})
    fold_checks, records = {}, []
    for i, (key, child_index) in enumerate(zip(keys, root.children, strict=True)):
        child = tree.nodes[child_index]
        delta = {tag: float(v[i] - v[base]) for tag, v in {"solver": raw, **cells}.items()}
        bounds = [float(delta_vertices[:, i].min()), float(delta_vertices[:, i].max())]
        records.append({"action": key, "category": category(key, child), "advantage": delta,
                        "bounds": bounds, "covered": bounds[0] - 1e-9 <= delta["D"] <= bounds[1] + 1e-9})
        if child.index not in model_replies:
            continue
        model_reply = phase_4y.grouped(child, model_replies[child.index])
        true_reply = phase_4y.grouped(child, true_replies[child.index])
        fold_checks[key] = {
            "projected_forecast": (model_reply @ projected).tolist(),
            "common_range_forecast": (model_reply @ field.weights).tolist(),
            "reference": (true_reply @ field.weights).tolist(),
            "geometry": asdict(reply_geometry(child.state)),
        }
        if key == "all_in":
            offered = ds.hero_street_commitment + ds.hero_stack
            collectible = ds.opponent_street_commitment + ds.opponent_stack
            fold_checks[key]["physical_target"] = offered
            fold_checks[key]["refundable_overhang"] = max(0, offered - collectible)
        # For fold/call only, condition on the actual calling composition.
        if len(child.actions) == 2:
            paid = min(max(child.state.commit), min(c + s for c, s in
                       zip(child.state.commit, child.state.stack, strict=True))) - g.totals[hero]
            matched = g.totals[hero] + paid
            call_pool = g.past + 2 * matched
            call_payoffs = (np.where(field.outcomes > 0, call_pool, np.where(
                field.outcomes == 0, (call_pool + g.odd_chip) // 2, 0)) - paid) / BIG_BLIND
            for name, r, w, base_value in (("model", model_reply, projected, raw[base]),
                                           ("reference", true_reply, field.weights, cells["D"][base])):
                call_weights = r[1] * w
                call_mass = call_weights.sum()
                conditional = float(call_payoffs @ call_weights / call_mass) if call_mass > 0 else None
                fold_ev = ds.pot / BIG_BLIND
                threshold = ((base_value - conditional) / (fold_ev - conditional)
                             if conditional is not None and abs(fold_ev - conditional) > 1e-12 else None)
                fold_rate = float(r[0] @ w)
                fold_checks[key][f"{name}_threshold"] = {
                    "call_ev": conditional, "break_even_fold": threshold,
                    "fold_minus_threshold": fold_rate - threshold if threshold is not None else None,
                    "fold_improves_ev": conditional < fold_ev if conditional is not None else None,
                }
    grid = ledger.all_wagers(g, field.outcomes, field.weights, field.reference.holdings, style,
                             ds.minimum_legal_target, ds.maximum_legal_target)
    plain_values = values_dict(keys, full_plain)
    best_grid = max(grid.items(), key=lambda item: item[1]) if grid else None
    costs = {"target_count": len(grid), "best_wager": [best_grid[0], best_grid[1] / BIG_BLIND] if grid else None,
             "menu_gap_bb": max(0., (best_grid[1] / BIG_BLIND if grid else -np.inf) - max(plain_values.values())),
             "target_ev_bb": [value / BIG_BLIND for value in grid.values()]}
    output = {"policy": {k: policy[k] for k in ("action", "mix", "action_ev", "columns", "source")},
              "raw_ev": values_dict(keys, raw), "cells": {k: values_dict(keys, v) for k, v in cells.items()},
              "projected_ev": values_dict(keys, model @ projected), "reference_plain": plain_values,
              "max_accounting_delta_bb": float(abs(raw - model @ projected).max()),
              "rank": rankings(values_dict(keys, raw), actual), "recommendation": selected,
              "records": records, "replies": fold_checks, "all_wagers": costs,
              "range_tv": float(abs(weights - field.weights).sum() / 2),
              "reference_mass_omitted": float(field.weights[~present].sum()),
              "seconds": policy["seconds"]}
    if detailed:
        output["weights"] = {"estimated": weights.tolist(), "projected": projected.tolist()}
        output["reply_vectors"] = {str(n.index): {"menu": n.labels, "state": asdict(n.state),
                                                    "estimated": model_replies[n.index].tolist(),
                                                    "reference": true_replies[n.index].tolist()}
                                   for n in villain_nodes}
    return output


def evaluate(case, mode, stream, prefix, name, profile, reverse=False, detailed=False):
    spot = case.spot()
    if mode == "checked":
        spot.actions[-1] = SpotAction("villain", "check")
    phase_4x.warm(spot)
    started = perf_counter()
    replays = {tag: phase_4x.witness(spot, tag, profile) for tag in ("BA" if reverse else "AB")}
    ds = replays["A"][1]
    assert ds == replays["B"][1] and ds.opponent_stack >= 0
    base = replays["A"][0]["action"]
    small = phase_4x.witness(spot, "B", profile, CFRWorkingSet(384))
    if mode == "checked":
        with patch.object(SolverBot, "postflop_menu", EXPANDED):
            replays["expanded"] = phase_4x.witness(spot, "B", profile)
    assert all(r[0]["seconds"] <= 15 for r in (*replays.values(), small))
    for tag, replay in {**replays, "small": small}.items():
        assert replay[1] == ds
        if tag != "A":
            assert len(replay[0]["columns"]) == 1
            assert max(replay[0]["columns"][0]) <= (384 if tag == "small" else 896)

    style = STYLES[name]
    field = phase_4y.Field(reference(case, ds, style))
    assert len(field.ids) == len(set(field.ids)) == 990 and abs(field.weights.sum() - 1) < 1e-12
    live, matrix, _ = _full_equity(case.board, SolverBot.flop_runouts)
    production = matrix[np.searchsorted(live, combo_index(case.hero)), np.searchsorted(live, field.ids)]
    np.testing.assert_array_equal(production, field.outcomes)
    snapshot = profile.snapshot if profile else None
    small_solve, small_root, combo = small[4]
    small_pos = int(np.searchsorted(small_solve.combos[small_root.player], combo))
    small_values = values_dict([label(SolverBot._legalize(ds, *action)) for action in small_root.actions],
                               small_solve.solver.action_values(small_root, small_pos) / BIG_BLIND)
    arms = {}
    for tag, replay in replays.items():
        observations = replay[5]
        arms[tag] = audit(replay, field, ds, style, base, snapshot,
                          prior=observations[-1][0] if observations else None,
                          sensitivity=small_values if tag == "B" else None, detailed=detailed)
    row = {"board_index": case.index, "mode": mode, "stream": stream, "prefix": prefix, "opponent": name,
           "case": asdict(case), "baseline": base, "arms": arms, "alternates": small_values,
           "state": asdict(ledger.root_ledger(ds, 0)), "pot": ds.pot, "to_call": ds.amount_to_call,
           "legal": ds.legal_actions, "targets": [ds.minimum_legal_target, ds.maximum_legal_target],
           "spr": min(ds.hero_stack, ds.opponent_stack + ds.amount_to_call) / (ds.pot - ds.amount_to_call),
           "reply_counts": river_counts(snapshot), "profile_river_observations": sum(river_counts(snapshot)),
           "working_set_seconds": small[0]["seconds"], "diagnostic_elapsed": perf_counter() - started}
    if detailed:
        row.update(history=[asdict(action) for action in spot.actions], reference_weights=field.weights.tolist(),
                   holdings=[h.combo for h in field.reference.holdings])
    return row


def prediction(records):
    pred, true = (np.array([r["advantage"][tag] for r in records]) for tag in ("solver", "D"))
    error = pred - true
    signed = [(sign(p), sign(t)) for p, t in zip(pred, true, strict=True)]
    return {"n": len(records), "predicted_mean": float(pred.mean()), "reference_mean": float(true.mean()),
            "bias": float(error.mean()), "mae": float(abs(error).mean()), "max_abs": float(abs(error).max()),
            "sign_match": mean(p == t for p, t in signed),
            "false_positive": sum(p == 1 and t <= 0 for p, t in signed),
            "false_negative": sum(p == -1 and t >= 0 for p, t in signed),
            "positive": sum(p == 1 for p, _ in signed), "negative": sum(p == -1 for p, _ in signed),
            "missed_profitable": sum(p <= 0 and t == 1 for p, t in signed),
            "covered": mean(r["covered"] for r in records),
            "width": mean(r["bounds"][1] - r["bounds"][0] for r in records),
            "cell_mae": {tag: mean(abs(r["advantage"][tag] - r["advantage"]["D"]) for r in records)
                         for tag in "ABC"},
            "interaction_abs_mean": mean(abs(r["advantage"]["D"] - r["advantage"]["C"] -
                                             r["advantage"]["B"] + r["advantage"]["A"]) for r in records)}


def bootstrap(rows, values):
    index = {(r["board_index"], r["stream"], r["opponent"]): v for r, v in zip(rows, values, strict=True)}
    field = np.array([[mean(index[i, stream, style] for style in STYLES) for stream in STREAMS]
                      for i in range(BOARD_COUNT)])
    rng = np.random.default_rng(45003)
    boards = rng.integers(BOARD_COUNT, size=(10000, BOARD_COUNT, 1))
    streams = rng.integers(len(STREAMS), size=(10000, 1, len(STREAMS)))
    return np.quantile(field[boards, streams].mean(axis=(1, 2)), [.025, .975]).tolist()


def summarize(rows, tag):
    eligible = [r for r in rows if tag in r["arms"]]
    pairs = [(row, row["arms"][tag]) for row in eligible]
    pooled, by = [], {}
    for row, arm in pairs:
        for record in arm["records"]:
            if record["action"] == row["baseline"]:
                continue
            pooled.append(record)
            for axis, key in (("size", record["category"]), ("style", row["opponent"]),
                              ("prefix", row["prefix"]), ("geometry", row["mode"]),
                              ("depth", row["case"]["depth"]), ("line", "/".join(row["case"]["line"])),
                              ("spr", "under_1" if row["spr"] < 1 else "1_to_2" if row["spr"] < 2 else "2_plus")):
                by.setdefault(axis, {}).setdefault(str(key), []).append(record)
    result = {"overall": prediction(pooled),
              "strata": {axis: {key: prediction(v) for key, v in categories.items()}
                         for axis, categories in by.items()}}
    rank = [event for _, arm in pairs for event in arm["rank"]]
    result["rank_correct"] = [sum(rank), len(rank)]
    result["max_repricing_delta_bb"] = max(arm["max_accounting_delta_bb"] for _, arm in pairs)
    result["mean_range_tv"] = mean(arm["range_tv"] for _, arm in pairs)
    result["mean_omitted_reference_mass"] = mean(arm["reference_mass_omitted"] for _, arm in pairs)
    result["menu_gap"] = {k: f([a["all_wagers"]["menu_gap_bb"] for _, a in pairs])
                          for k, f in (("mean", mean), ("max", max))}
    result["fold_bias"] = {}
    for row, arm in pairs:
        categories = {r["action"]: r["category"] for r in arm["records"]}
        for key, replies in arm["replies"].items():
            result["fold_bias"].setdefault(categories[key], []).append(
                replies["common_range_forecast"][0] - replies["reference"][0])
    result["fold_bias"] = {k: {"n": len(v), "mean": mean(v), "mae": mean(map(abs, v))}
                           for k, v in result["fold_bias"].items()}
    result["recommendation"] = {}
    result["closing"] = {"profitable": 0, "losing": 0, "profitable_folds": 0, "losing_covers": 0}
    result["top_wrong"] = {key: 0 for key in ("solver", "A", "B", "C", "D")}
    for row, arm in pairs:
        true = arm["cells"]["D"]
        for key, values in {"solver": arm["raw_ev"], **arm["cells"]}.items():
            best = min(values, key=lambda a: (-values[a], a))
            result["top_wrong"][key] += max(true.values()) - true[best] > EPS
        if row["mode"] == "closing":
            margin = true.get("call", true.get("all_in")) - true["fold"]
            result["closing"]["profitable"] += margin > EPS
            result["closing"]["losing"] += margin < -EPS
            folded = arm["policy"]["action"] == "fold"
            result["closing"]["profitable_folds"] += margin > EPS and folded
            result["closing"]["losing_covers"] += margin < -EPS and not folded
    for choice in ("mixed", "modal", "selected"):
        metric = "regret" if choice == "mixed" else f"{choice}_regret"
        regrets = [arm["recommendation"][metric] for _, arm in pairs]
        i = int(np.argmax(regrets))
        worst_row, worst_arm = pairs[i]
        result["recommendation"][choice] = {"mean_regret": mean(regrets), "wrong": sum(v > EPS for v in regrets),
                                             "worst_regret": regrets[i],
                                             "worst_key": [worst_row[k] for k in ("board_index", "stream", "opponent")],
                                             "worst_action": worst_arm["recommendation"].get(choice),
                                             "severe": sum(v > .5 for v in regrets)}
        if len(eligible) == len(rows):
            result["recommendation"][choice]["regret_ci"] = bootstrap(eligible, regrets)
        if choice != "mixed":
            deltas = [arm["recommendation"][f"{choice}_delta"] for _, arm in pairs]
            result["recommendation"][choice]["mean_delta"] = mean(deltas)
            result["recommendation"][choice]["worst_delta"] = min(deltas)
    if len(eligible) == len(rows):
        result["mae_ci"] = bootstrap(eligible, [
            mean(abs(r["advantage"]["solver"] - r["advantage"]["D"]) for r in arm["records"]
                 if r["action"] != row["baseline"]) for row, arm in pairs])
        result["coverage_ci"] = bootstrap(eligible, [
            mean(r["covered"] for r in arm["records"] if r["action"] != row["baseline"])
            for row, arm in pairs])
    if tag == "B":
        shifts, flips, top_changes = [], [], 0
        for row, arm in pairs:
            low, high, base = row["alternates"], arm["raw_ev"], row["baseline"]
            top_changes += max(low, key=low.get) != max(high, key=high.get)
            for action in high.keys() - {base}:
                a, b = low[action] - low[base], high[action] - high[base]
                shifts.append(abs(a - b))
                flips.append(sign(a) != sign(b))
        result["working_set"] = {"mean_abs_shift": mean(shifts), "max_abs_shift": max(shifts),
                                 "sign_changes": sum(flips), "contrasts": len(flips),
                                 "top_changes": top_changes, "max_seconds": max(r["working_set_seconds"] for r, _ in pairs)}
    times = [a["seconds"] for _, a in pairs]
    return {**result, "seconds": {"median": median(times), "p95": float(np.quantile(times, .95)), "max": max(times)}}


def historical():
    reproduced = phase_4y.historical()
    old = min(phase_4y.read_rows("4y", "holdout-13"), key=lambda r: r["arms"]["C"]["selected_delta"])
    replayed = phase_4y.replay_archive(old, phase_4y.schedule(), "ABC")
    assert abs(replayed["arms"]["C"]["selected_delta"] - old["arms"]["C"]["selected_delta"]) < 1e-10
    records = [replayed, *reproduced["rows"]]
    for old in records:
        case = phase_4t.load_case(old, phase_4q.WagerCase)
        stream, prefix, name = (old[key] for key in ("stream", "prefix", "opponent"))
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        old["audit"] = evaluate(case, "closing" if case.shove else "live", stream, prefix, name, profile, detailed=True)
    return {"rows": records}


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def holdout(output, expected):
    if not expected or manifest() != json.loads(expected.read_text(encoding="utf-8")):
        raise SystemExit("frozen source or schedule mismatch")
    if os.environ.get("PYTHONHASHSEED") not in ("13", "31"):
        raise SystemExit("expected PYTHONHASHSEED 13 or 31")
    profiles = {}
    rows = []
    reverse = os.environ["PYTHONHASHSEED"] == "31"
    with output.with_suffix(".jsonl").open("x", encoding="utf-8") as journal:
        for i, (case, mode, stream, prefix, name) in enumerate(schedule()):
            key = [case.index, stream, name]
            print(key, mode, flush=True)
            try:
                if prefix and (name, stream) not in profiles:
                    profiles[name, stream] = train(name, stream, PREFIXES[1:])
                profile = profiles[name, stream][prefix] if prefix else None
                row = evaluate(case, mode, stream, prefix, name, profile, reverse ^ bool(i % 2))
            except Exception as exc:
                journal.write(json.dumps({"key": key, "error": repr(exc)}) + "\n")
                raise
            journal.write(json.dumps(row, allow_nan=False) + "\n")
            journal.flush()
            rows.append(row)
    return {"rows": rows, "summary": {tag: summarize(rows, tag) for tag in ("A", "B", "expanded")},
            "unexpected_fallbacks": 0}


def stable(data):
    if isinstance(data, dict):
        return {k: stable(v) for k, v in data.items() if k not in
                ("seconds", "working_set_seconds", "max_seconds", "diagnostic_elapsed")}
    if isinstance(data, list):
        return [stable(v) for v in data]
    return data


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "historical", "holdout", "compare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--runs", type=Path, nargs=2)
    args = parser.parse_args()
    if args.mode == "freeze":
        write(args.output, manifest())
    elif args.mode == "historical":
        write(args.output, historical())
    elif args.mode == "holdout":
        write(args.output, holdout(args.output, args.manifest))
    else:
        left, right = [stable(json.loads(path.read_text(encoding="utf-8"))) for path in args.runs]
        assert left == right
        write(args.output, {"equal_excluding_timing": True, "rows": len(left["rows"])})


if __name__ == "__main__":
    main()
