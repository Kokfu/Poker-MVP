"""Offline Phase 5D evidence aggregation and separate diagnostic controls."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from dataclasses import asdict, replace
import json
from pathlib import Path
from random import Random
from statistics import mean
from unittest.mock import patch

import numpy as np

from coach import service as coach
from poker_analyzer import FULL_DECK
from research.holdem import phase_4q, phase_4t, phase_4z, phase_5b, phase_5c, phase_5d as study
from research.holdem import river_shadow as shadow
from research.holdem.phase_4k import RANKER, STYLES, river_spot, strength, train
from research.holdem.reply_forecast import river_counts
from simulation.opponent_model import OpponentModel
from solver.exploit import beta_interval


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def intervals(rows):
    metrics = np.array([
        [*(r["decision"]["arms"][arm][key] - r["decision"]["arms"]["A"][key]
           for key in ("mae", "regret") for arm in "BC"),
         *(r["ranges"][stage]["tv"] - r["ranges"][stage + "_entry"]["tv"] for stage in study.STREETS)]
        for r in rows
    ])
    strata = defaultdict(list)
    for index, row in enumerate(rows):
        strata[row["style"], row["wager"]].append(index)
    rng = np.random.default_rng(659209)
    indices = np.concatenate([rng.choice(indices, (2000, len(indices)), replace=True)
                              for indices in strata.values()], axis=1)
    low, high = np.quantile(metrics[indices].mean(axis=1), (.025, .975), axis=0)
    names = ["B-A MAE", "C-A MAE", "B-A regret", "C-A regret", *study.STREETS]
    return dict(zip(names, np.stack((metrics.mean(axis=0), low, high), axis=1).tolist(), strict=True))


def reliability(rows):
    totals = defaultdict(lambda: np.zeros(3))
    for row in rows:
        for bucket, *values in row["reliability"]:
            totals[bucket] += values
    return {b: [float(n), float(p / n), float(q / n)] for b, (n, p, q) in sorted(totals.items()) if n > 0}


def summarize_ranges(rows):
    result = {}
    for stage in rows[0]["ranges"]:
        items = [r["ranges"][stage] for r in rows]
        result[stage] = {
            **{key: mean(r[key] for r in items)
               for key in ("tv", "combo_mae", "missing_mass", "brier", "log_loss", "excess_log_loss")},
            "effective": np.mean([r["effective"] for r in items], axis=0).tolist(),
            "tier_mass": np.mean([r["tier_mass"] for r in items], axis=0).tolist(),
            "tier_abs_error": np.mean([abs(np.diff(r["tier_mass"], axis=0))[0] for r in items], axis=0).tolist(),
            "win_abs_error": mean(abs(r["showdown_mass"][0][2] - r["showdown_mass"][1][2])
                                  for r in items) if items[0]["showdown_mass"] else None,
            "reliability": reliability(items),
        }
    return result


def summarize_observed(rows):
    groups = defaultdict(list)
    for row in rows:
        for observed in row["observed"]:
            groups[observed["street"]].append(observed)
    return {street: {"n": len(group), **{key: mean(item[key] for item in group)
             for key in ("estimated", "reference", "mae", "brier", "log_loss",
                         "column_mass_removed", "reference_off_columns")}} for street, group in groups.items()}


def summarize_replies(rows):
    if not rows:
        return None
    by_action = defaultdict(list)
    for row in rows:
        for kind, values in row["actions"].items():
            by_action[kind].append(values)
    return {"n": len(rows), "reach_median": float(np.median([r["reach"] for r in rows])),
            **{key: mean(r[key] for r in rows) for key in ("brier", "excess_brier", "log_loss")},
            "actions": {kind: {"n": len(values), "mean": np.mean(values, axis=0).tolist(),
                               "marginal_mae": mean(abs(p - q) for p, q, _ in values)}
                        for kind, values in by_action.items()}, "reliability": reliability(rows)}


def choices(rows):
    adverse = Counter()
    opportunities = Counter()
    correct = Counter()
    flips = Counter()
    folds = defaultdict(list)
    for record in rows:
        row = record["decision"]
        arms = row["arms"]
        a = arms["A"]
        if a["regret"] > study.MATERIAL:
            b, c = (arms[arm]["regret"] <= study.MATERIAL for arm in "BC")
            adverse["either" if b and c else "range" if b else "reply" if c else "joint"] += 1
        for arm in "BCD":
            if arms[arm]["action"] != a["action"]:
                flips[arm] += 1
                if not {arms[arm]["action"], a["action"]} & {"fold", "check", "call"}:
                    flips[arm + "_size_only"] += 1
        true = arms["D"]["values"]
        if "call" in true and "fold" in true and abs(true["call"] - true["fold"]) > study.MATERIAL:
            kind = "profitable_call" if true["call"] > true["fold"] else "unprofitable_call"
            opportunities[kind] += 1
            if set(true) == {"call", "fold"} or set(true) == {"all_in", "fold"}:
                opportunities[kind + "_closing"] += 1
            if row["seeded"] == "call":
                correct[kind] += 1
        elif set(true) == {"all_in", "fold"} and abs(true["all_in"]) > study.MATERIAL:
            kind = "profitable_call" if true["all_in"] > 0 else "unprofitable_call"
            opportunities[kind] += 1
            opportunities[kind + "_closing"] += 1
            if row["seeded"] == "all_in":
                correct[kind] += 1
        for check in row["fold_checks"]:
            estimated, exact = check["estimated"], check["reference"]
            if exact["nonfold_bb"] is None:
                continue
            passive = max(value for kind, value in true.items() if kind in ("check", "fold", "call"))
            bluff = exact["nonfold_bb"] < passive - study.MATERIAL
            if bluff and abs(exact["margin_bb"]) > study.MATERIAL:
                kind = "profitable_bluff" if exact["margin_bb"] > 0 else "unprofitable_bluff"
                opportunities[kind] += 1
                if row["seeded"] == check["action"]:
                    correct[kind] += 1
            group = "bluff" if bluff else "value_or_neutral"
            folds[group].append((estimated, exact))
    return {"attribution": adverse, "opportunities": opportunities, "selected_opportunities": correct,
            "switches_from_A": flips, "thresholds": {group: threshold_summary(pairs) for group, pairs in folds.items()}}


def threshold_summary(pairs):
    available = [(p, q) for p, q in pairs if p["threshold"] is not None and q["threshold"] is not None]
    return {"n": len(pairs), "fold_bias": mean(p["fold"] - q["fold"] for p, q in pairs),
            "fold_mae": mean(abs(p["fold"] - q["fold"]) for p, q in pairs),
            "available": len(available),
            "crossing_sign_disagreements": sum((p["fold"] >= p["threshold"]) != (q["fold"] >= q["threshold"])
                                               for p, q in available),
            "threshold_margin_mae": mean(abs((p["fold"] - p["threshold"]) - (q["fold"] - q["threshold"]))
                                         for p, q in available) if available else None,
            "near_5pp_n": sum(abs(q["fold"] - q["threshold"]) <= .05 for _, q in available),
            "near_5pp_sign_errors": sum(abs(q["fold"] - q["threshold"]) <= .05 and
                                       (p["fold"] >= p["threshold"]) != (q["fold"] >= q["threshold"])
                                       for p, q in available)}


def decision_summary(rows):
    def regret_stats(regrets):
        harmful = [r for r in regrets if r > study.MATERIAL]
        return {"mean": mean(regrets), "n_harmful": len(harmful),
                "mean_harm": mean(harmful) if harmful else None, "worst": max(regrets),
                "high": sum(r >= 2 for r in regrets), "severe": sum(r >= 8 for r in regrets)}

    records = [r["decision"] for r in rows]
    result = {}
    for arm in "ABCD":
        cells = [r["arms"][arm] for r in records]
        result[arm] = {"decision_mae": mean(c["mae"] for c in cells),
                       "action_mae": sum(c["mae"] * len(c["values"]) for c in cells) / sum(len(c["values"]) for c in cells),
                       "rank_ok": sum(c["rank_ok"] for c in cells), "rank_n": sum(c["rank_n"] for c in cells),
                       "false_advantages": sum(c["false_advantages"] for c in cells),
                       **regret_stats([c["regret"] for c in cells])}
    for label in ("seeded", "modal"):
        result[label] = regret_stats([r[label + "_regret"] for r in records])
    interaction = [abs(v) for r in records for v in r["interaction"]]
    result["interaction_abs_bb"] = [mean(interaction), max(interaction)]
    result["cfr_residual_max_bb"] = max(r["cfr_gap"] for r in records)
    result["projection_gap_max_bb"] = max(r["projection_gap"] for r in records)
    worst = sorted(rows, key=lambda r: r["decision"]["seeded_regret"], reverse=True)[:5]
    result["worst_seeded"] = [{"index": r["index"], "style": r["style"], "wager": r["wager"],
                               "depth": r["depth"], "prefix": r["prefix"], "decision": r["decision"]} for r in worst]
    return result


def summarize(directory):
    files = {seed: [read(directory / f"holdout-{seed}-{shard}.json") for shard in range(4)]
             for seed in (13, 31)}
    runs = {seed: sorted((r for piece in pieces for r in piece["rows"]), key=lambda r: r["index"])
            for seed, pieces in files.items()}
    assert [r["index"] for r in runs[13]] == list(range(96))
    assert [study.canonical(r) for r in runs[13]] == [study.canonical(r) for r in runs[31]]
    rows = runs[13]
    expanded = {model: [item for r in rows for item in r["expanded"].get(model, [])]
                for model in ("fixed_cfr", "pooled_count")}
    profiles = {}
    for n in study.PREFIXES:
        group = [r for r in rows if r["prefix"] == n]
        profiles[n] = {"n": len(group), "range": summarize_ranges(group)["river"],
                       "rivers_with_reply_evidence": sum(sum(r["native_counts"]) > 0 for r in group),
                       "reply_opportunities": mean(sum(r["native_counts"]) for r in group),
                       "reply": summarize_replies([node for r in group for node in r["replies"]]),
                       "decision": decision_summary(group)}
    return {"canonical_equal": True, "n": len(rows), "ranges": summarize_ranges(rows),
            "observed": summarize_observed(rows), "intervals": intervals(rows), "decisions": decision_summary(rows),
            "choices": choices(rows), "profiles": profiles,
            "positions_paths": {field: {value: summarize_ranges([r for r in rows if r[field] == value])["river"]["tv"]
                                        for value in sorted({r[field] for r in rows})} for field in ("seat", "path")},
            "slices": {field: {part: {"n": len(group), "decision": decision_summary(group),
                                     "range_tv": summarize_ranges(group)["river"]["tv"],
                                     "reply": summarize_replies([node for r in group for node in r["replies"]])}
                               for part in sorted({r[field] for r in rows})
                               if (group := [r for r in rows if r[field] == part])}
                       for field in ("style", "wager", "depth")},
            "native_replies": summarize_replies([node for r in rows for node in r["replies"]]),
            "expanded": {model: {size: summarize_replies([r for r in set_rows if r["size"] == size])
                                 for size in sorted({r["size"] for r in set_rows})}
                         for model, set_rows in expanded.items()},
            "runtime": {field: {seed: [float(np.median(samples)), sorted(samples)[int(np.ceil(.95 * len(samples))) - 1],
                                       max(samples)]
                               for seed, section in runs.items() if (samples := [r[field] for r in section])}
                        for field in ("coach_seconds", "shadow_seconds", "offline_seconds")},
            "peaks_mib": {seed: [p["peak_mib"] for p in pieces] for seed, pieces in files.items()},
            "persistent_projection": [r["projection_audit"] for r in rows if r["paired"]]}


def identification():
    rng = Random(659207)
    models = [OpponentModel("b"), OpponentModel("b")]
    raw = [[Counter(), Counter()], [Counter(), Counter()]]
    snapshots = {}
    truth = np.zeros(2)
    for n in range(0, 1001, 2):
        if n in (0, 4, 30, 100, 1000):
            a, b = (model.snapshot() for model in models)
            assert a.as_dict() == b.as_dict()
            snapshots[n] = {"pooled": river_counts(a), "public_profile_equal": True,
                            "sized_buckets": [{k: asdict(s) for k, s in snap.sized_statistics.items()}
                                              for snap in (a, b)],
                            "raw": [[{**dict(c), "posterior_fold": (c["fold"] + 1) / (c["n"] + 2),
                                      "interval": beta_interval(c["fold"], c["n"], level=.95)}
                                     for c in counts] for counts in raw]}
        if n == 1000:
            break
        deal = rng.sample(FULL_DECK, 9)
        hero, villain, board = deal[:2], deal[2:4], deal[4:]
        tier = strength(RANKER.score(villain, board))
        probabilities = np.array((.68, .28)) + (.13, 0., -.22)[tier]
        truth += probabilities / 500
        draw = rng.random()
        for cell, model in enumerate(models):
            for index in range(2):
                fold = draw < probabilities[index ^ cell]
                spot = replace(river_spot(" ".join(hero), " ".join(board), 0),
                               hero_stack=1500, villain_stack=2500, villain_cards=villain)
                spot.actions.extend([coach.SpotAction("hero", "bet", 125) if index == 0
                                     else coach.SpotAction("hero", "all_in"),
                                     coach.SpotAction("villain", "fold" if fold else "call")])
                status, payload, _ = coach._replay(spot)
                assert status == "hand_complete" and not payload["result"]["illegal_actions"]
                history = payload["result"]["history"]
                model.update(history)
                offer, reply = [event for event in history.events if event.event_type == "action_taken"][-2:]
                assert offer.street == reply.street == "river" and offer.actor == "a" and reply.actor == "b"
                assert (offer.applied_action == "all_in") == bool(index)
                raw[cell][index].update(("n", reply.applied_action))
    return {"snapshots": snapshots, "conditional_reference_folds": [truth.tolist(), truth[::-1].tolist()]}


def historical(directory):
    phase_4_output = directory / "historical-phase-4.json"
    if phase_4_output.exists():
        records = read(phase_4_output)["rows"]
    else:
        records = phase_4z.historical()["rows"]
        archive = read(phase_5c.HISTORY / "holdout-13.json")["rows"]
        old = next(r for r in archive if r["case"]["hero"] == ["Qc", "2d"] and
                   r["stream"] == 342 and r["opponent"] == "tight_passive")
        case = phase_4t.load_case(old, phase_4q.WagerCase)
        old_audit = phase_4z.evaluate(case, "live", 342, 0, "tight_passive", None, detailed=True)
        switch_ev = old_audit["arms"]["B"]["reference_plain"]
        assert abs(switch_ev["all_in"] - switch_ev["call"] + 11.551) < .001
        records.append({"case": asdict(case), "audit": old_audit, "archived_switch_regret": 11.551})
        phase_5b.write(directory / "historical-phase-4.json", {"rows": records})
    holdout = read(study.REPO / "benchmark-results/phase-5c-2026-11-19/holdout-13.json")["rows"]
    probes = []
    for index in (21, 24, 46):
        case, spot, style, wager, prefix, profile_style, stream = list(phase_5c.schedule())[index]
        profile = train(profile_style, stream, (prefix,))[prefix] if prefix else None
        with patch.object(shadow, "CEILING", float("inf")), patch.object(shadow, "BUDGET", float("inf")):
            advised, trace, model, _ = phase_5b.run_coach(spot, prefix, profile, None, False, True,
                                                      directory / "diagnostic-traces")
        assert trace and trace["status"] == "complete"
        q_style = STYLES[style]
        reference = phase_5c.score_reference(model, trace, case, q_style)
        original = holdout[index]
        assert json.loads(json.dumps(advised)) == original["advice"]
        assert phase_5c.flags(trace) == original["flags"]
        assert json.loads(json.dumps(reference)) == original["reference"]
        holdings, weights, _ = phase_5b.independent_range(model, case, q_style, None)
        replies = phase_5b.reference_policy(model, holdings, q_style, None)
        probes.append({"index": index, "spot": asdict(spot), "reference": reference, "trace": trace,
                       "flags": phase_5c.flags(trace), "holdings": [h.combo for h in holdings],
                       "weights": {"estimated": model.posterior.tolist(), "reference": weights.tolist()},
                       "replies": {i: {"labels": model.nodes[i].labels,
                                       "estimated": model.replies[i].tolist(), "reference": replies[i].tolist()}
                                   for i in replies},
                       "reference_reply_summary": shadow.summarize_replies(model, replies, weights)})
    return {"phase_4_replay": records, "phase_5c_replay": probes}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("summary", "historical", "identification"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "identification":
        result = identification()
    else:
        operation = summarize if args.mode == "summary" else historical
        result = operation(args.output.parent)
    phase_5b.write(args.output, result)


if __name__ == "__main__":
    main()


