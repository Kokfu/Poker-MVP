"""Frozen, offline evaluation of the observable river risk diagnostic."""

from argparse import ArgumentParser
from collections import Counter
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import product
import json
from math import sqrt
import os
from pathlib import Path
from random import Random
from statistics import mean

import numpy as np

from coach.service import SpotAction
from research.holdem import action_ev_reference as ledger, phase_4q, phase_4t, phase_4z, phase_5b
from research.holdem import river_shadow as shadow
from research.holdem.phase_4k import BIG_BLIND, MISMATCH, STYLES, peak_resident_bytes, train
from research.holdem.phase_5a import distribution
from solver.bot import _EQUITY_CACHE


BOARD_SEED = 653_202
DESIGN_SEED = 653_203
STREAM_START = 8200
HIGH = 2.
SEVERE = 8.
WAGERS = {"checked": None, "quarter": .25, "half": .5, "three_quarter": .75, "overbet": 1.25, "closing": None}
PREFIXES = (0, 3, 30, 100)
HISTORY = phase_5b.REPO / "benchmark-results/phase-4z-2026-11-19"


def schedule():
    factors = list(product(STYLES, WAGERS, PREFIXES))
    Random(DESIGN_SEED).shuffle(factors)
    cases = phase_4q.cases(BOARD_SEED, len(factors), 3)
    for i, (case, (style, wager, prefix)) in enumerate(zip(cases, factors, strict=True)):
        fraction = WAGERS[wager]
        if fraction and case.behind <= int(case.pot * fraction):
            case = replace(case, depth=30)
        case = replace(case, shove=wager == "closing", pot_wager=False)
        spot = case.spot()
        if wager == "checked":
            if case.seat == "button":
                spot.actions[-1] = SpotAction("villain", "check")
            else:
                spot.actions[-2:] = []
        elif fraction:
            spot.actions[-1] = SpotAction("villain", "bet", int(case.pot * fraction))
        match = (tuple(STYLES).index(style) + tuple(WAGERS).index(wager) + PREFIXES.index(prefix)) % 2 == 0
        profile_style = (style if match else MISMATCH[style]) if prefix else None
        yield case, spot, style, wager, prefix, profile_style, STREAM_START + i


def manifest():
    base = phase_4z.manifest()["sources"]
    protocol = "PHASE_5C_PROTOCOL.md"
    base[protocol] = sha256((phase_5b.REPO / protocol).read_bytes()).hexdigest()
    return {"sources": base, "schedule": [
        [asdict(case), asdict(spot), style, wager, prefix, profile_style, stream]
        for case, spot, style, wager, prefix, profile_style, stream in schedule()
    ], "design_seed": DESIGN_SEED, "board_seed": BOARD_SEED, "coach_seed": phase_5b.SEED,
        "reference_styles": {name: asdict(style) for name, style in STYLES.items()}}


def flags(trace):
    selected, preferred = trace["seeded"], trace["bounded_preferred"]
    estimate, scenarios = trace["bounded_ev_bb"], trace["sensitivity_ev_bb"]
    lead = estimate[preferred] - estimate[selected]
    swing = max(abs(values[preferred] - values[selected] - lead) for values in scenarios.values())
    alternate = max(max(values.values()) - values[preferred] for values in scenarios.values())
    return {
        "disagreement": (trace["cfr_preferred"] != preferred) if trace["cfr_preferred"] is not None else None,
        "phase_5b": max(swing, alternate) >= phase_5b.RISK or trace["range"]["effective"] < 50,
        "phase_5c": trace["decision_risk"]["flagged"],
        "nominal_gap": lead >= HIGH,
        "low_support": trace["range"]["effective"] < 50,
    }


def score_reference(model, trace, case, style):
    holdings, weights, outcomes = phase_5b.independent_range(model, case, style, None)
    np.testing.assert_array_equal(outcomes, model.outcomes)
    replies = phase_5b.reference_policy(model, holdings, style, None)
    root, ds = model.root, model.decision
    geometry = ledger.root_ledger(ds, root.player)
    keys = tuple(map(shadow.key, model.menu))

    def values(policy):
        return ledger.evaluate_tree(model, root, geometry, outcomes, policy, model.hero_tail) / ds.big_blind

    nominal, exact = values(model.replies), values(replies)
    estimate = trace["bounded_ev_bb"]
    np.testing.assert_allclose(nominal @ model.posterior, [estimate[key] for key in keys], atol=1e-10, rtol=0.)
    np.testing.assert_allclose(nominal @ model.projected, [trace["projected_ev_bb"][key] for key in keys],
                               atol=1e-10, rtol=0.)
    reference, range_only, replies_only = (
        dict(zip(keys, (array @ range_weights).tolist(), strict=True))
        for array, range_weights in ((exact, weights), (nominal, weights), (exact, model.posterior))
    )
    selected = trace["seeded"]
    best = max(sorted(keys), key=reference.get)
    immediate = shadow.summarize_replies(model, replies, weights)
    passive = [reference[key] for key, (action, _) in zip(keys, root.actions, strict=True)
               if action in ("fold", "call", "check")]
    profitable_bluffs, unprofitable_bluffs = [], []
    profitable_calls, unprofitable_calls = [], []
    for key, (action, target), child in zip(keys, root.actions, root.children, strict=True):
        if action == "call" and set(kind for kind, _ in root.actions) == {"fold", "call"}:
            if reference[key] > .01:
                profitable_calls.append(key)
            elif reference[key] < -.01:
                unprofitable_calls.append(key)
        if action not in ("bet", "raise", "all_in") or not passive or child not in immediate:
            continue
        fold = immediate[child]["actions"].get("fold", 0.)
        fold_ev = (model.nodes[child].state.pot - target + ds.hero_street_commitment) / ds.big_blind
        nonfold = (reference[key] - fold * fold_ev) / (1. - fold) if fold < 1. else None
        if nonfold is not None and nonfold < max(passive) - .01:
            if reference[key] > max(passive) + .01:
                profitable_bluffs.append(key)
            elif reference[key] < max(passive) - .01:
                unprofitable_bluffs.append(key)
    reply_errors = []
    for index, actual in immediate.items():
        predicted = trace["reply_forecasts"]["coach"][str(index)]
        if min(actual["reach"], predicted["reach"]) >= .05 and "fold" in actual["actions"]:
            reply_errors.append({action: predicted["actions"].get(action, 0.) - actual["actions"].get(action, 0.)
                                 for action in ("fold", "call", "all_in")})
    return {
        "ev_bb": reference, "range_only_bb": range_only, "replies_only_bb": replies_only,
        "best": best, "seeded_regret_bb": reference[best] - reference[selected],
        "modal_regret_bb": reference[best] - reference[trace["modal"]],
        "phase_5b_endpoint_regret_bb": reference[best] - reference[trace["bounded_preferred"]],
        "range_tv": float(abs(model.posterior - weights).sum() / 2),
        "reply_errors": reply_errors,
        "same_column_max_error_bb": max(abs(trace["cfr_ev_bb"][key] - trace["projected_ev_bb"][key])
                                        for key in keys),
        "profitable_bluffs": profitable_bluffs, "unprofitable_bluffs": unprofitable_bluffs,
        "profitable_calls": profitable_calls, "unprofitable_calls": unprofitable_calls,
    }


def run(out, reverse, arm):
    rows = list(schedule())
    run_rows = list(enumerate(rows))
    trace_dir = out.parent / f"traces-{out.stem}"
    if arm:
        run_rows = [next((i, r) for i, r in run_rows if r[3] == wager and r[2] == style)
                    for wager, style in zip(WAGERS, (*STYLES, *tuple(STYLES)[:2]), strict=True)]
    elif reverse:
        run_rows.reverse()
    evidence = []
    with out.with_suffix(".jsonl").open("x", encoding="utf-8") as journal:
        for i, (case, spot, style, wager, prefix, profile_style, stream) in run_rows:
            profile = train(profile_style, stream, (prefix,))[prefix] if prefix else None

            def advise(enabled):
                # Use the actual native Coach strategy and menu.
                return phase_5b.run_coach(spot, prefix, profile, None, False, enabled, trace_dir)

            _EQUITY_CACHE.clear()
            row = {"index": i, "style": style, "wager": wager, "prefix": prefix, "profile_style": profile_style,
                   "stream": stream, "depth": case.depth}
            if arm:
                for mode in ("cold", "warm"):
                    advised, trace, _, seconds = advise(arm == "shadow")
                    row[mode] = {"seconds": seconds, "source": advised["response"]["explanation"]["source"],
                                 "trace": trace}
            else:
                paired = i % 8 == 0
                if paired and not reverse:
                    baseline = advise(False)
                    _EQUITY_CACHE.clear()
                enabled, trace, model, seconds = advise(True)
                if paired and reverse:
                    _EQUITY_CACHE.clear()
                    baseline = advise(False)
                row.update(source=enabled["response"]["explanation"]["source"], trace=trace,
                           seconds=seconds, advice=enabled,
                           invariant=baseline[0] == enabled if paired else None,
                           disabled_seconds=baseline[3] if paired else None)
                if trace and trace["status"] == "complete":
                    row["reference"] = score_reference(model, trace, case, STYLES[style])
                    row["flags"] = flags(trace)
            evidence.append(row)
            journal.write(json.dumps(row, allow_nan=False) + "\n")
            journal.flush()
            print(i, wager, row.get("source", arm), ((row.get("trace") or {}).get("status") if not arm else ""),
                  flush=True)
    return {"rows": sorted(evidence, key=lambda row: row["index"]), "peak_mib": peak_resident_bytes() / 2 ** 20}


def interval(yes, total):
    if not total:
        return None
    rate, z = yes / total, 1.959963984540054
    center = (rate + z*z / (2*total)) / (1 + z*z / total)
    span = z * sqrt(rate * (1 - rate) / total + z*z / (4*total*total)) / (1 + z*z / total)
    return {"count": yes, "total": total, "rate": rate, "wilson95": [max(0., center - span), min(1., center + span)]}


def summarize(rows):
    usable = [row for row in rows if "reference" in row]
    rule_names = ("disagreement", "phase_5b", "phase_5c", "nominal_gap", "low_support")

    def measures(subset, rule):
        eligible = [r for r in subset if r["flags"][rule] is not None]
        pairs = Counter((r["reference"]["seeded_regret_bb"] >= HIGH, r["flags"][rule]) for r in eligible)
        tp, fp, fn, tn = (pairs[key] for key in ((True, True), (False, True), (True, False), (False, False)))
        severe = [r for r in eligible if r["reference"]["seeded_regret_bb"] >= SEVERE]
        opportunities = {}
        for key in ("profitable_bluffs", "unprofitable_bluffs", "profitable_calls", "unprofitable_calls"):
            offered = [r for r in eligible if r["reference"][key]]
            taken = [r for r in offered if r["trace"]["seeded"] in r["reference"][key]]
            opportunities[key] = {"offered": len(offered), "taken": len(taken),
                                  "taken_flagged": interval(sum(r["flags"][rule] for r in taken), len(taken)),
                                  "other_flagged": interval(sum(r["flags"][rule] for r in offered) -
                                                            sum(r["flags"][rule] for r in taken),
                                                            len(offered) - len(taken))}
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "unavailable": len(subset) - len(eligible),
                "recall": interval(tp, tp + fn), "precision": interval(tp, tp + fp), "fpr": interval(fp, fp + tn),
                "fnr": interval(fn, tp + fn), "severe_coverage": interval(sum(r["flags"][rule] for r in severe), len(severe)),
                "action_opportunities": opportunities}

    groups = {
        "overall": usable,
        "geometry=closing": [r for r in usable if r["wager"] == "closing"],
        "geometry=nonclosing": [r for r in usable if r["wager"] != "closing"],
    }
    for column in ("style", "wager", "prefix", "depth"):
        for value in sorted({row[column] for row in usable}):
            groups[f"{column}={value}"] = [row for row in usable if row[column] == value]
    for level in ("matched", "mismatched", "none"):
        groups[f"profile={level}"] = [r for r in usable if (
            "none" if r["profile_style"] is None else "matched" if r["style"] == r["profile_style"] else "mismatched"
        ) == level]
    reply_errors = [error for r in usable for error in r["reference"]["reply_errors"]]
    ev_errors = [r["trace"]["bounded_ev_bb"][key] - truth for r in usable
                 for key, truth in r["reference"]["ev_bb"].items()]
    return {
        "scheduled": len(rows), "scored": len(usable), "statuses": Counter((r["trace"] or {}).get("status", "missing")
                                                                          for r in rows),
        "unexpected_fallbacks": sum(r["source"] != "postflop_solve" for r in rows),
        "invariance": Counter(str(r["invariant"]) for r in rows if r["invariant"] is not None),
        "groups": {name: {rule: measures(subset, rule) for rule in rule_names} for name, subset in groups.items()},
        "reply_error_nodes": len(reply_errors),
        "mean_reply_error": {key: mean(e[key] for e in reply_errors) for key in ("fold", "call", "all_in")} if reply_errors else {},
        "mean_range_tv": mean(r["reference"]["range_tv"] for r in usable) if usable else None,
        "estimated_ev_mae_bb": mean(map(abs, ev_errors)) if ev_errors else None,
        "max_same_column_error_bb": max((r["reference"]["same_column_max_error_bb"] for r in usable), default=None),
        "coach_seconds": distribution([r["seconds"] for r in rows]),
        "paired_disabled_seconds": distribution([r["disabled_seconds"] for r in rows if r["disabled_seconds"] is not None]),
        "shadow_ms": distribution([1000*r["trace"]["shadow_seconds"] for r in usable]) if usable else None,
        "risk_ms": distribution([1000*r["trace"]["risk_seconds"] for r in usable]) if usable else None,
    }


def canonical(data):
    if isinstance(data, dict):
        return {key: canonical(value) for key, value in data.items()
                if key not in ("seconds", "disabled_seconds")}
    if isinstance(data, list):
        return [canonical(value) for value in data]
    return data


def historical(out):
    old_rows = phase_4z.historical()["rows"]
    selections = [
        ("displayed_recommendation", "all_in", None, "C", "selected_delta", -8.204),
        ("harmful_bluff", "all_in", 896, "B", "delta", -17.690),
        ("seeded_shove", "all_in", None, "C", "selected_delta", -9.639),
        ("accepted_adjustment", "all_in", None, "E", "delta", -2.347),
        ("closing_fold_one", "fold", None, None, None, 1.315),
        ("closing_fold_two", "fold", None, None, None, 5.547),
    ]
    holdout = json.loads((HISTORY / "holdout-13.json").read_text(encoding="utf-8"))["rows"]
    archive = next(row for row in holdout if row["case"]["hero"] == ["Qc", "2d"] and row["stream"] == 342
                   and row["opponent"] == "tight_passive")
    case = phase_4t.load_case(archive, phase_4q.WagerCase)
    old_rows.append({"case": archive["case"], "stream": 342, "prefix": 0, "opponent": "tight_passive",
                     "audit": phase_4z.evaluate(case, "live", 342, 0, "tight_passive", None)})
    selections.append(("action_switch", "all_in", 896, None, None, -11.551))
    results = []
    for old, (name, action, cap, arm, field, expected) in zip(old_rows, selections, strict=True):
        case = phase_4t.load_case(old, phase_4q.WagerCase)
        prefix, style = old["prefix"], old["opponent"]
        profile = train(style, old["stream"], (prefix,))[prefix] if prefix else None
        _, trace, model, _ = phase_5b.run_coach(case.spot(), prefix, profile, cap, False, True,
                                                out.parent / "historical-traces")
        audit = old["audit"]["arms"]["B"]["reference_plain"]
        if arm:
            previous = old["arms"][arm]
            # Archived phases used distinct field names for probability-weighted deltas.
            reproduced = previous[field] if field in previous else previous["ev"] - old["arms"]["A"]["ev"]
        elif name == "action_switch":
            reproduced = audit["all_in"] - audit["call"]
        else:
            reproduced = max(audit.values())
        assert abs(reproduced - expected) < .001, (name, reproduced, expected)
        risk = None
        if trace and trace["status"] == "complete":
            labels = tuple(map(shadow.key, model.menu))
            if action in labels:
                risk = shadow.evaluate(replace(model, seeded=labels.index(action)), float("inf"))["decision_risk"]
        results.append({"case": asdict(case), "name": name, "cap": cap, "comparison_bb": reproduced,
                        "candidate": action, "reference_ev_bb": audit, "trace": trace, "candidate_risk": risk})
        print(name, reproduced, None if risk is None else risk["flagged"], flush=True)
    return {"rows": results}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "holdout", "performance", "compare", "historical"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--arm", choices=("cfr", "shadow"))
    parser.add_argument("--runs", type=Path, nargs=2)
    args = parser.parse_args()
    if args.mode == "freeze":
        phase_5b.write(args.output, manifest())
    elif args.mode == "historical":
        phase_5b.write(args.output, historical(args.output))
    elif args.mode == "compare":
        a, b = (json.loads(path.read_text(encoding="utf-8"))["rows"] for path in args.runs)
        equal = canonical(phase_5b.canonical(a)) == canonical(phase_5b.canonical(b))
        phase_5b.write(args.output, {"canonical_equal": equal, "decisions": len(a)})
        if not equal:
            raise SystemExit("canonical holdouts differ")
    else:
        expected = json.loads(args.manifest.read_text(encoding="utf-8"))
        if expected != json.loads(json.dumps(manifest())):
            raise SystemExit("frozen sources or schedule differ")
        seed = os.environ.get("PYTHONHASHSEED")
        if seed not in ("13", "31") or (args.mode == "performance" and args.arm is None):
            raise SystemExit("require hash seed 13 or 31 and an arm for performance")
        result = run(args.output, seed == "31", args.arm)
        if args.mode == "holdout":
            result["summary"] = summarize(result["rows"])
        phase_5b.write(args.output, result)


if __name__ == "__main__":
    main()
