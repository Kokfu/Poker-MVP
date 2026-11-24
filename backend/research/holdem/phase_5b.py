"""Frozen offline Coach integration trials. Reference inputs stay in this runner."""
from argparse import ArgumentParser
from collections import Counter
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from unittest.mock import patch

import numpy as np

from coach import service as coach
from research.holdem import action_ev_reference as ledger, phase_4p, phase_4q, phase_4z, river_shadow as shadow
from research.holdem.decoupled_replay import CFRWorkingSet
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, peak_resident_bytes, river_spot, train
from research.holdem.phase_4v import stable
from research.holdem.phase_5a import MENU, distribution
from research.holdem.river_ev import ExactRiverEV
from solver.bot import SolverBot, _EQUITY_CACHE, replay_hand
from solver.combos import combo_index


BOARD_SEED = 650_202
STREAM = 651
SEED = 917
RISK = 2.0
REPO = phase_4z.REPO
KINDS = ("checked", "quarter", "half", "closing", "three_quarter", "overbet", "checked", "closing",
         "half", "closing", "overbet", "quarter", "closing", "checked", "three_quarter", "checked")


def schedule():
    for index, (case, kind) in enumerate(zip(phase_4q.cases(BOARD_SEED, len(KINDS), 2), KINDS, strict=True)):
        # Keep nonclosing wagers and all earlier scripted calls safely below the stack.
        if kind in ("quarter", "half", "three_quarter", "overbet"):
            case = replace(case, depth=30)
        case = replace(case, shove=kind == "closing", pot_wager=False)
        spot = case.spot()
        if kind == "checked":
            if case.seat == "button":
                spot.actions[-1] = coach.SpotAction("villain", "check")
            else:
                spot.actions[-2:] = []
        elif kind != "closing":
            fraction = {"quarter": .25, "half": .5, "three_quarter": .75, "overbet": 1.25}[kind]
            spot.actions[-1] = coach.SpotAction("villain", "bet", int(case.pot * fraction))
        name = tuple(STYLES)[index % 4]
        yield case, spot, name, kind, (0, 3, 30, 100)[(index // 4 + index) % 4], (None, 128, 384, None)[index % 4], None

    # Fresh exact price witnesses. The prescribed opponent cards are used
    # only by the terminal ledger after the enabled and disabled Coach calls.
    controls = (
        ("bluff_profitable", "4c 6d", "2h 8s 9c Js Qd", "Ah Ad", 0, .68),
        ("bluff_unprofitable", "3d 6h", "2s 7c 9h Td Qc", "Ks Kd", 0, .12),
        ("call_profitable", "Ah Kh", "Qh Jh Th 3c 7d", "As Ac", 1250, 0),
        ("call_unprofitable", "2c 3s", "5d 7h 9s Jd Qh", "Qc Qs", 1250, 0),
    )
    for kind, hero, board, villain, bet, folds in controls:
        spot = river_spot(hero, board, bet)
        if bet == 1250:
            spot.actions[-1] = coach.SpotAction("villain", "all_in")
        else:
            spot = replace(spot, hero_stack=2500, villain_stack=2500)
        yield None, spot, "tight_passive", kind, 0, None, (tuple(villain.split()), folds)


def manifest():
    sources = phase_4z.manifest()["sources"]
    path = "PHASE_5B_PROTOCOL.md"
    sources[path] = sha256((REPO / path).read_bytes()).hexdigest()
    return {"sources": sources, "schedule": [{"spot": asdict(spot), "opponent": name, "kind": kind,
                                               "prefix": prefix, "cap": cap, "control": control}
                                              for _, spot, name, kind, prefix, cap, control in schedule()]}


def digest(*parts):
    return sha256(repr(parts).encode()).hexdigest()


def run_coach(spot, prefix, profile, cap, alternate_menu, enabled, trace_dir):
    """Call the actual Coach service, witnessing CFR inputs and unrounded draws."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    model, inputs, draws = [], [], []
    solve, sample, evaluate = SolverBot._solve, SolverBot._sample, shadow.evaluate

    def solve_probe(bot, state, board, ranges, hero_combo, hero, snapshot=None, **kwargs):
        ids = kwargs.get("working_ids")
        inputs.append(digest(state, board, hero_combo, hero, tuple(r.tobytes() for r in ranges),
                             tuple(x.tobytes() for x in ids) if ids is not None else None,
                             snapshot, bot._strength_correlation() if snapshot else None))
        return solve(bot, state, board, ranges, hero_combo, hero, snapshot, **kwargs)

    def sample_probe(bot, ds, probabilities):
        selected = sample(bot, ds, probabilities)
        draws.append((probabilities.tolist(), int(selected)))
        return selected

    def observe(snapshot, deadline):
        model.append(snapshot)
        return evaluate(snapshot, deadline)

    class TrainingHistory:
        hands_observed = prefix

        def snapshot(self):
            return profile.snapshot

    def trained_profile(store, name, observer=None):
        if observer is not None:
            profile.attach(observer)
        return TrainingHistory()

    from os import environ

    with patch.dict(environ, {shadow.FLAG: str(int(enabled)), shadow.TRACE_DIR: str(trace_dir),
                              "POKER_COACH_PERSISTENT_RANGES": str(int(cap is not None))}), \
            patch.object(SolverBot, "range_selection", CFRWorkingSet(cap) if cap else None), \
            patch.object(SolverBot, "postflop_menu", MENU if alternate_menu else SolverBot.postflop_menu), \
            patch.object(SolverBot, "_solve", solve_probe), patch.object(SolverBot, "_sample", sample_probe), \
            patch.object(shadow, "evaluate", observe), patch.object(coach, "profile_for", trained_profile):
        start = perf_counter()
        response = coach.advise(spot, opponent="frozen" if prefix else None, store=object(), seed=SEED)
        seconds = perf_counter() - start
    traces = list(trace_dir.glob("*.json"))
    if traces:
        (path,) = traces
        trace = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
    else:
        trace = None
    return {"response": stable(response), "inputs": inputs, "draws": draws}, trace, next(iter(model), None), seconds


def independent_range(model, case, style, control):
    ds = model.decision
    if control:
        exact = ExactRiverEV(ds.hole_cards, ds.board_cards, lambda pair, _: float(set(pair) == set(control[0])))
    else:
        universe = ExactRiverEV(ds.hole_cards, ds.board_cards, lambda *_: 1.)
        replay = replay_hand(ds)
        villain = 1 - replay.current.to_act
        history = tuple(phase_4p.observations(replay, villain, case.seat == "button"))
        pairs = [h.combo for h in universe.holdings]
        weights = phase_4p.reference_weights(pairs, history, case.depth, style)
        for step in replay.steps:
            if step.player != villain or step.street == "preflop":
                continue
            if step.street == "river":
                weights *= [(1 - style.open_probability(h.rank)) if step.kind == "check"
                            else style.open_probability(h.rank) for h in universe.holdings]
            else:
                board = list(case.board[:3 if step.street == "flop" else 4])
                weights *= [phase_4p.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                            for pair in pairs]
        by_pair = dict(zip(pairs, weights, strict=True))
        exact = ExactRiverEV(ds.hole_cards, ds.board_cards, lambda pair, _: by_pair[pair])
    by_id = {combo_index(h.combo): h for h in exact.holdings}
    holdings = tuple(by_id[i] for i in model.ids)
    return holdings, np.array([hand.weight for hand in holdings]), np.array([hand.result for hand in holdings])


def reference_policy(model, holdings, style, control):
    replies = {}
    for index in model.replies:
        node = model.nodes[index]
        if "check" in node.labels:
            bet = np.array([style.open_probability(h.rank) for h in holdings])
            if control:
                bet.fill(0)
            result = np.stack([1 - bet if key == "check" else bet / (len(node.labels) - 1) for key in node.labels])
        elif control:
            folds = control[1]
            result = np.stack([np.full(len(holdings), folds if key == "fold" else 1 - folds if key == "call" else 0)
                               for key in node.labels])
        else:
            result = ledger.reference_reply(node, holdings, style)
        np.testing.assert_allclose(result.sum(axis=0), 1., atol=1e-12, rtol=0)
        replies[index] = result
    return replies


def reference(model, trace, case, style, control):
    holdings, weights, outcomes = independent_range(model, case, style, control)
    np.testing.assert_array_equal(outcomes, model.outcomes)
    specified = reference_policy(model, holdings, style, control)
    ds, root = model.decision, model.root
    geometry = ledger.root_ledger(ds, root.player)
    keys = tuple(map(shadow.key, model.menu))

    def evaluate(replies):
        return ledger.evaluate_tree(model, root, geometry, outcomes, replies, model.hero_tail) / ds.big_blind

    def keyed(values):
        return dict(zip(keys, values.tolist(), strict=True))

    estimate, exact = evaluate(model.replies), evaluate(specified)
    cells = {"estimated": keyed(estimate @ model.posterior), "range_only": keyed(estimate @ weights),
             "replies_only": keyed(exact @ model.posterior), "reference": keyed(exact @ weights)}
    truth = cells["reference"]
    bounded, cfr = trace["bounded_ev_bb"], trace["cfr_ev_bb"]
    np.testing.assert_allclose(list(cells["estimated"].values()), [bounded[k] for k in keys], rtol=0, atol=1e-10)
    np.testing.assert_allclose(estimate @ model.projected, [trace["projected_ev_bb"][k] for k in keys], rtol=0, atol=1e-10)
    best = max(sorted(truth), key=truth.get)
    chosen = {selector: trace[selector] for selector in ("seeded", "modal", "bounded_preferred", "cfr_preferred")}
    regret = {selector: truth[best] - truth[key] for selector, key in chosen.items()}
    pair_calibration = {arm: phase_4z.rankings(values, truth) for arm, values in
                        (("cfr", cfr), ("shadow", bounded))}
    preferred = chosen["bounded_preferred"]
    cfr_gap = max(abs(trace["projected_ev_bb"][k] - cfr[k]) for k in keys)
    ref_replies = shadow.summarize_replies(model, specified, weights)
    coach_replies = trace["reply_forecasts"]["coach"]
    # Count material directional errors only at reply nodes reached by both models.
    differences = []
    for index, reply in ref_replies.items():
        coach_reply = coach_replies[str(index)]
        if min(reply["reach"], coach_reply["reach"]) < .05 or "fold" not in reply["actions"]:
            continue
        differences.append({key: coach_reply["actions"].get(key, 0.) - reply["actions"].get(key, 0.)
                            for key in ("fold", "call", "all_in")})
    seeded = chosen["seeded"]
    scenario_swing = max(abs((values[preferred] - values[seeded]) - (bounded[preferred] - bounded[seeded]))
                         for values in trace["sensitivity_ev_bb"].values())
    # When greedy agrees with the seed, measure sensitivity of the chosen
    # action against the best alternative in each scenario as well.
    alternate_delta = max(max(values[k] - values[preferred] for k in keys)
                          for values in trace["sensitivity_ev_bb"].values())
    projection_gap = max(abs(trace["projected_ev_bb"][k] - bounded[k]) for k in keys)
    return {"cells": cells, "best": best, "regret": regret, "pairs": pair_calibration,
            "cfr_projected_gap_bb": cfr_gap, "projection_gap_bb": projection_gap,
            "estimated_disagreement": preferred != chosen["cfr_preferred"],
            "false_agreement": preferred == chosen["cfr_preferred"] and regret["bounded_preferred"] > shadow.MATERIAL,
            "risk_flag": max(scenario_swing, alternate_delta) >= RISK or trace["range"]["effective"] < 50,
            "high_risk": regret["bounded_preferred"] >= RISK,
            "scenario_swing_bb": scenario_swing, "scenario_alternate_advantage_bb": alternate_delta,
            "range_total_variation": float(abs(weights - model.posterior).sum() / 2),
            "reply_differences": differences,
            "action_mae_bb": {arm: mean(abs(values[k] - truth[k]) for k in keys)
                              for arm, values in cells.items() if arm != "reference"},
            "paired_reference_switch_bb": truth[preferred] - truth[seeded]}


def execute(out, reverse=False, arm=None):
    profiles = {name: train(name, STREAM, (3, 30, 100)) for name in STYLES}
    schedule_rows = list(enumerate(schedule()))
    if reverse:
        schedule_rows.reverse()
    if arm is not None:
        schedule_rows = [row for row in schedule_rows if row[0] in (0, 5, 10, 15, 16, 18)]
    rows = []
    trace_dir = out.parent / f"traces-{out.stem}"
    for index, (case, spot, name, kind, prefix, cap, control) in schedule_rows:
        profile = profiles[name].get(prefix)

        def run(enabled):
            return run_coach(spot, prefix, profile, cap, kind.startswith("bluff"), enabled, trace_dir)

        if arm is not None:
            _EQUITY_CACHE.clear()
            cold = run(arm == "shadow")
            warm = run(arm == "shadow")
            rows.append({"index": index, "cold_seconds": cold[3], "warm_seconds": warm[3],
                         "sources": [item[0]["response"]["explanation"]["source"] for item in (cold, warm)],
                         "traces": [cold[1], warm[1]] if arm == "shadow" else []})
            continue
        answers = {}
        for enabled in ((True, False) if reverse else (False, True)):
            _EQUITY_CACHE.clear()
            answers[enabled] = run(enabled)
        baseline, _, _, base_seconds = answers[False]
        enabled, trace, model, shadow_seconds = answers[True]
        row = {"index": index, "kind": kind, "style": name, "prefix": prefix, "cap": cap,
               "depth": spot.hero_stack / BIG_BLIND, "invariant": baseline == enabled,
               "input_fingerprints_equal": baseline["inputs"] == enabled["inputs"],
               "source": enabled["response"]["explanation"]["source"], "trace": trace,
               "base_seconds": base_seconds, "shadow_seconds": shadow_seconds}
        if trace and trace["status"] == "complete":
            row["reference"] = reference(model, trace, case, STYLES[name], control)
        rows.append(row)
        print(index, kind, row["source"], trace["status"] if trace else "missing", flush=True)
    rows.sort(key=lambda row: row["index"])
    result = {"rows": rows, "peak_mib": peak_resident_bytes() / 2 ** 20}
    if arm is not None:
        result["arm"] = arm
        result["latency"] = {field: distribution([row[field] for row in rows]) for field in ("cold_seconds", "warm_seconds")}
    else:
        result["status"] = Counter(row["trace"]["status"] if row["trace"] else "missing" for row in rows)
        result["latency"] = {field: distribution([row[field] for row in rows]) for field in ("base_seconds", "shadow_seconds")}
    return result


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()
                if key not in ("peak_mib", "latency", "base_seconds", "shadow_seconds",
                               "advisor_seconds_before_shadow", "risk_seconds")}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def write(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "holdout", "performance", "compare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--arm", choices=("cfr", "shadow"))
    parser.add_argument("--runs", type=Path, nargs=2)
    args = parser.parse_args()
    if args.mode == "freeze":
        write(args.output, manifest())
    elif args.mode == "compare":
        a, b = (json.loads(path.read_text(encoding="utf-8")) for path in args.runs)
        equal = canonical(a) == canonical(b)
        write(args.output, {"canonical_equal": equal})
        if not equal:
            raise SystemExit("canonical holdouts differ")
    else:
        frozen = json.loads(args.manifest.read_text(encoding="utf-8"))
        if frozen != json.loads(json.dumps(manifest())):
            raise SystemExit("frozen sources or schedule differ")
        write(args.output, execute(args.output, args.reverse, args.arm if args.mode == "performance" else None))


if __name__ == "__main__":
    main()
