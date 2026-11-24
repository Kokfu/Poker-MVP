"""Frozen Phase 4U ablation with independent terminal river scoring."""
from argparse import ArgumentParser
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np

from coach.service import HERO, _replay
from research.holdem import phase_4o, phase_4p, phase_4q, phase_4r, phase_4s, phase_4t
from research.holdem.decoupled_replay import DecoupledReplay
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, peak_resident_bytes, train
from research.holdem.phase_4l import modeled_continuation, normalize, payoff_values, response_means
from research.holdem.phase_4m import calibration, oracle_response, reply_nodes
from research.holdem.range_support import ResearchReplay
from research.holdem.reply_forecast import (
    REPLY_MODELS, gate, posterior_models, prepare_evaluation, proposed_mix, reply_geometry, scenario_values,
)
from research.holdem.river_ev import ExactRiverEV
from simulation.actions import Action
from solver.bot import _full_equity, replay_hand
from solver.combos import COMBOS, combo_index


PANELS = {"development": (441201, 4, (201,)), "holdout": (441202, 8, (211, 212, 213))}
REPO = phase_4t.REPO
EVIDENCE = REPO / "benchmark-results"
BENCH_DATE = "2026-11-18"


def schedule(panel):
    seed, count, streams = PANELS[panel]
    cases = [list(phase_4q.cases(seed, count, index)) for index in range(len(streams))]
    return [(lines[board], stream, phase_4r.PREFIXES[(board + index) % 4], name)
            for board in range(count) for index, (lines, stream) in enumerate(zip(cases, streams, strict=True))
            for name in STYLES]


def record_policy(bot, ds, keys, exact_values, mix, seconds):
    np.testing.assert_allclose(mix.sum(), 1, atol=1e-12, rtol=0)
    assert np.isfinite(mix).all() and (mix >= 0).all()
    choice = keys[bot._pick(ds, mix)]
    assert choice in keys
    ev = float(mix @ exact_values)
    return dict(mix=dict(zip(keys, mix.tolist(), strict=True)), chosen=choice, ev=ev,
                regret=float(exact_values.max() - ev), seconds=seconds)


def score_replies(baseline, bot, exact, style, evaluation, forecasts, history):
    """Compare response laws with a common reference range, after policies are fixed."""
    node, tree = evaluation.root, evaluation.tree
    nodes = reply_nodes(tree, node)
    if not nodes:
        return [], None, None
    weights = np.array([hand.weight for hand in exact.holdings])
    ids = np.array([combo_index(hand.combo) for hand in exact.holdings])
    order = np.searchsorted(evaluation.ids, ids)
    np.testing.assert_array_equal(evaluation.ids[order], ids)
    _, _, cfr, hero_policy, _ = modeled_continuation(bot, node, exact.holdings)
    incumbent = {}
    if getattr(baseline, "live_node", None) is not None:
        a_node, a_tree = baseline.live_node, baseline.river.tree
        _, _, a_replies, _, _ = modeled_continuation(baseline, a_node, exact.holdings)
        incumbent = {key: (a_tree.nodes[child].actions, a_replies[child])
                     for key, child in zip(a_node.labels, a_node.children, strict=True) if child in a_replies}
    true = {reply.index: oracle_response(reply, exact.holdings, style, False) for reply in nodes}
    out = []
    by_child = dict(zip(node.children, node.labels, strict=True))
    for reply in nodes:
        sigma = forecasts[reply.index][:, order]
        compared = {"CFR": cfr[reply.index], "independent": sigma}
        key = by_child[reply.index]
        if key in incumbent:
            actions, probabilities = incumbent[key]
            assert actions == reply.actions
            compared["incumbent"] = probabilities
        metrics = calibration(reply, compared, true[reply.index], weights)
        row = {"target": by_child[reply.index], "menu": reply.labels,
               "geometry": asdict(reply_geometry(reply.state)), "scores": metrics,
               "true_reference": response_means(reply.actions, true[reply.index] @ weights),
               "independent_own_range": response_means(reply.actions, sigma @ bot.estimate[ids])}
        if history:
            row["holding_probabilities"] = {"cfr": cfr[reply.index].T.tolist(), "independent": sigma.T.tolist(),
                                            "true": true[reply.index].T.tolist()}
        out.append(row)
    full = bot.estimate[ids]
    cfr_full = payoff_values(tree, node, exact.holdings, full, cfr, hero_policy) / BIG_BLIND
    substitutions = None
    if history:
        substitutions = {}
        for name, prior, law in (("full_cfr", full, cfr), ("true_range_cfr", weights, cfr),
                                 ("full_true_replies", full, true), ("true_range_true_replies", weights, true)):
            substitutions[name] = (payoff_values(tree, node, exact.holdings, prior, law, hero_policy)
                                   / BIG_BLIND).tolist()
    return out, substitutions, cfr_full


def evaluate(case, stream, prefix, name, profile, *, order=0, exact=None, archive=None, history=False):
    status, _, engine = _replay(case.spot())
    assert status == "hero_to_act"
    ds = engine.decision_observation(HERO).decision_state
    style = STYLES[name]
    if exact is None:
        exact = phase_4s.exact_reference(case, ds, style)
    baseline, decoupled = phase_4t.BaselineTrace(False), DecoupledReplay()
    solvers = [("A", baseline), ("B", decoupled)]
    arms = {key: phase_4r.arm(bot, case, profile, exact, style, ds)
            for key, bot in solvers[order:] + solvers[:order]}
    a, b = arms["A"], arms["B"]
    row = {"case": asdict(case), "stream": stream, "prefix": prefix, "opponent": name,
           "closing": ds.opponent_stack == 0 and "fold" in ds.legal_actions, "arms": arms}
    if "failure" in b:
        arms.update({key: b.copy() for key in ("C", "D", "E")})
        row["exact_action_ev"] = a.get("exact_action_ev", {})
        return row

    keys = b["keys"]
    exact_map = row["exact_action_ev"] = b["exact_action_ev"]
    truth = np.array(list(exact_map.values()))
    if "failure" in a:
        fallback = label(Action(*a["fallback_action"]))
        mix = np.array([float(key == fallback) for key in keys])
        arms["A"].update(record_policy(baseline, ds, keys, truth, mix, a["seconds"]))
    else:
        assert a["keys"] == keys and a["exact_action_ev"] == exact_map
        mix = baseline.probabilities
    for bot, record in ((baseline, a), (decoupled, b)):
        if "failure" not in record:
            record["chosen"] = keys[bot._pick(ds, bot.probabilities)]

    arms["D"] = phase_4s.decision_factor(decoupled, ds, b)
    started = perf_counter()
    snapshot = profile.snapshot if profile else None
    evaluation = prepare_evaluation(decoupled, snapshot)
    replies = evaluation.forecasts()
    payoffs = evaluation.values(replies)
    nominal = payoffs @ decoupled.estimate[evaluation.ids]
    # A terminal choice has no reply model. The unchanged B mix is its proposal.
    proposal = proposed_mix(decoupled.probabilities, nominal) if replies else decoupled.probabilities
    forecast_seconds = perf_counter() - started

    started = perf_counter()
    ranges = posterior_models(decoupled, evaluation.ids)
    scenarios = scenario_values(evaluation, ranges, payoffs)
    robust, interval, accepted = gate(mix, proposal, scenarios)
    gate_seconds = perf_counter() - started
    arms["C"] = record_policy(decoupled, ds, keys, truth, proposal, b["seconds"] + forecast_seconds)
    # Charge both replay paths to E, since it requires the true incumbent mix.
    arms["E"] = record_policy(decoupled, ds, keys, truth, robust,
                             a["seconds"] + b["seconds"] + forecast_seconds + gate_seconds)
    if not accepted:
        assert arms["E"]["mix"] == a["mix"] and arms["E"]["chosen"] == a["chosen"]
    np.testing.assert_allclose(nominal, scenarios[0], atol=1e-8, rtol=0)
    delta = proposal - mix
    distinct = bool(np.max(np.abs(delta)) > 1e-12)
    row["adjustment"] = {
        "proposed": distinct, "accepted": accepted, "nominal_action_ev": dict(zip(keys, nominal / BIG_BLIND, strict=True)),
        "predicted_delta": float(nominal @ delta / BIG_BLIND), "true_delta": float(truth @ delta),
        "interval": [value / BIG_BLIND for value in interval], "models": len(scenarios),
        "reply_counts": evaluation.counts, "assumptions": asdict(evaluation.assumptions),
        "decision_seconds": {"forecast": forecast_seconds, "gate": gate_seconds},
    }
    row["replies"], substitutions, cfr_full = score_replies(baseline, decoupled, exact, style, evaluation, replies, history)
    if replies:
        # Diagnostic repricing with the same selection rule, full compatible
        # posterior and Hero continuation to isolate response input from choice.
        cfr = np.array(list(b["modeled_action_ev"].values()))
        matched = proposed_mix(decoupled.probabilities, cfr_full * BIG_BLIND)
        row["reply_only_control"] = {"working_cfr": cfr.tolist(), "full_cfr": cfr_full.tolist(),
                                     "cfr_greedy_ev": float(truth @ matched),
                                     "independent_greedy_ev": arms["C"]["ev"]}
    b["columns"] = [len(ids) for ids in decoupled.river.combos]
    assert max(b["columns"]) <= 896 and decoupled.solve_count == 1
    b["compatible_positive"] = int(np.count_nonzero(decoupled.estimate))
    b["persistent_effective_size"] = float(1 / (decoupled.estimate @ decoupled.estimate))
    assert b["compatible_positive"] > 0
    if history:
        villain = 1 - evaluation.root.player
        last = next(entry for entry in reversed(decoupled.observations) if entry.step.player == villain)
        ids = np.array([combo_index(hand.combo) for hand in exact.holdings])
        order = np.searchsorted(evaluation.ids, ids)
        reference_prior = reference_incoming(case, ds, exact, style)
        row["historical"] = {
            "state": asdict(evaluation.root.state), "villain_observed": [last.step.kind, last.step.target],
            "holdings": [COMBOS[i] for i in ids], "modeled_incoming": normalize(last.prior[ids]).tolist(),
            "modeled_observed_likelihood": last.law.observed(last.step)[ids].tolist(),
            "reference_incoming": reference_prior.tolist(),
            "reference_posterior": [hand.weight for hand in exact.holdings],
            "posterior_models": {model: values[order].tolist() for model, values in ranges.items()},
            "scenario_labels": [[list(model), name] for model in (REPLY_MODELS if replies else REPLY_MODELS[:1])
                                for name in ranges],
            "scenario_action_ev": (scenarios / BIG_BLIND).tolist(),
            "substitutions": substitutions, "archived": archive,
        }
    return row


def reference_incoming(case, ds, exact, style):
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    pairs = [hand.combo for hand in exact.holdings]
    pre = phase_4p.reference_weights(pairs, phase_4p.observations(replay, villain, case.seat == "button"),
                                     case.depth, style)
    for step in [step for step in replay.steps if step.player == villain][:-1]:
        if step.street != "preflop":
            board = list(case.board[:3 if step.street == "flop" else 4])
            pre *= [phase_4p.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                    for pair in pairs]
    return normalize(pre)


def historical():
    def rows(phase, filename):
        path = EVIDENCE / f"phase-{phase}-{BENCH_DATE}" / f"{filename}.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))["rows"]

    def report(case, name, stream, prefix, exact=None, archive=None):
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        return evaluate(case, stream, prefix, name, profile, exact=exact, archive=archive, history=True)

    output = [report(phase_4r.failed_case(), "tight_aggressive", 131, 3)]
    for filename, hero, name, stream, kind in (
        ("historical", ["Js", "3c"], "loose_aggressive", 91, phase_4o.Case),
        ("diagnostic-13", ["Kc", "As"], "tight_passive", 132, phase_4q.WagerCase),
    ):
        old = next(r for r in rows("4q", filename) if r["case"]["hero"] == hero
                   and r["opponent"] == name and r["stream"] == stream)
        case = phase_4t.load_case(old, kind)
        evidence = old["evidence"]
        truth = dict(zip(map(tuple, evidence["combos"]), evidence["true_posterior"], strict=True))
        exact = ExactRiverEV(case.hero, case.board, lambda pair, _: truth[pair])
        archive = {key: old.get(key) for key in ("decision", "exact_ev_bb", "live_mix", "opening")}
        if old.get("phase_4p_replay"):
            archive["phase_4p_replay"] = old["phase_4p_replay"]["decision"]
        output.append(report(case, name, stream, old["hands"], exact, archive))
    for phase, hero, stream in (("4s", ["Jd", "4h"], 172), ("4t", ["Js", "Kh"], 191)):
        old = next(r for r in rows(phase, "holdout-13") if r["case"]["hero"] == hero
                   and r["opponent"] == "loose_aggressive" and r["stream"] == stream)
        output.append(report(phase_4t.load_case(old, phase_4q.WagerCase), old["opponent"], stream, old["prefix"],
                             archive={"arms": old["arms"], "exact_action_ev": old["exact_action_ev"]}))
    return {"rows": output}


def summarize(rows):
    result = phase_4t.summarize(rows)
    for key in phase_4t.ARMS:
        regrets = [r["arms"][key]["regret"] for r in rows if "regret" in r["arms"][key]]
        if regrets:
            result["arms"][key].update(median_regret=float(np.median(regrets)), max_regret=max(regrets))
    adjustments = [r for r in rows if r.get("adjustment", {}).get("proposed")]
    accepted = [r for r in adjustments if r["adjustment"]["accepted"]]
    rejected = [r for r in adjustments if not r["adjustment"]["accepted"]]
    result["coverage"] = {
        "proposed": len(adjustments), "accepted": len(accepted), "rejected": len(rejected),
        "accepted_fraction": len(accepted) / len(adjustments) if adjustments else 0.,
        "accepted_true_mean": mean(r["adjustment"]["true_delta"] for r in accepted) if accepted else None,
        "rejected_true_mean": mean(r["adjustment"]["true_delta"] for r in rejected) if rejected else None,
        "rejected_true_positive": sum(r["adjustment"]["true_delta"] > .01 for r in rejected),
        "rejected_true_negative": sum(r["adjustment"]["true_delta"] < -.01 for r in rejected),
        "accepted_by_style": {name: sum(r["opponent"] == name for r in accepted) for name in STYLES},
        "accepted_closing": sum(r["closing"] for r in accepted),
        "accepted_nonclosing": sum(not r["closing"] for r in accepted),
    }
    replies = [reply for row in rows for reply in row.get("replies", ())]
    fields = ("excess_brier", "holding_brier")
    def reply_scores(group):
        by_method = {method: [r["scores"][method] for r in group if method in r["scores"]]
                     for method in ("incumbent", "CFR", "independent")}
        return {method: {field: mean(r[field] for r in samples) if samples else None for field in fields}
                for method, samples in by_method.items()}
    result["calibration"] = {"rows": len(replies), "overall": reply_scores(replies),
                             "by_style": {style: reply_scores([reply for row in rows if row["opponent"] == style
                                                              for reply in row.get("replies", ())]) for style in STYLES},
                             "by_prefix": {str(p): reply_scores([reply for row in rows if row["prefix"] == p
                                                                 for reply in row.get("replies", ())])
                                           for p in phase_4r.PREFIXES}}
    result["profitable_cover_regressions"] = [
        [r["case"]["index"], r["stream"], r["opponent"]]
        for r in rows if r["closing"] and max(r["exact_action_ev"].values(), default=0.) > 0
        and "mix" in r["arms"]["E"] and "mix" in r["arms"]["A"]
        and (r["arms"]["E"]["mix"].get("fold", 0.) - r["arms"]["A"]["mix"].get("fold", 0.) > 1e-12
             or (r["arms"]["E"]["chosen"] == "fold" and r["arms"]["A"]["chosen"] != "fold"))]
    matched = [r["reply_only_control"] for r in rows if "reply_only_control" in r]
    result["reply_only_delta"] = mean(r["independent_greedy_ev"] - r["cfr_greedy_ev"] for r in matched) if matched else None
    return result


def frozen_manifest():
    sources = phase_4t.frozen_manifest()["sources"]
    for path in ("PHASE_4U_PROTOCOL.md", "backend/test_research_holdem_phase_4u.py"):
        sources[path] = sha256((REPO / path).read_bytes()).hexdigest()
    manifest = lambda panel: [dict(case=asdict(case), stream=s, prefix=p, opponent=n)
                              for case, s, p, n in schedule(panel)]
    return {"sources": sources, "development": manifest("development"), "holdout": manifest("holdout")}


def run_panel(panel):
    _, _, streams = PANELS[panel]
    profiles = {(stream, name): train(name, stream, phase_4r.PREFIXES[1:]) for stream in streams for name in STYLES}
    rows = []
    previous = None
    for index, (case, stream, prefix, name) in enumerate(schedule(panel)):
        if case.board != previous:
            for n in (3, 4, 5):
                _full_equity(case.board[:n], ResearchReplay.flop_runouts)
            print(f"Board {case.index + 1} after {index} rows", flush=True)
            previous = case.board
        rows.append(evaluate(case, stream, prefix, name, profiles[stream, name].get(prefix), order=index % 2))
    return {"rows": rows, "summary": summarize(rows)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(*PANELS, "freeze", "historical", "compare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--runs", type=Path, nargs=2)
    args = parser.parse_args()
    started = perf_counter()
    if args.mode == "compare":
        if not args.runs:
            parser.error("compare requires two --runs")
        runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.runs]
        ignored = {"wall_seconds", "seconds", "decision_seconds", "replay_seconds", "over_cap",
                   "process_peak_resident_bytes", "runtime", "memory", "hash_seed"}
        def deterministic(value):
            if isinstance(value, dict):
                return {k: deterministic(v) for k, v in value.items() if k not in ignored}
            if isinstance(value, list):
                return [deterministic(v) for v in value]
            return value
        digests = [sha256(json.dumps(deterministic(run), sort_keys=True).encode()).hexdigest() for run in runs]
        phase_4s.write_json(args.output, {"matched": digests[0] == digests[1], "digests": digests,
                                         "excluded": sorted(ignored)})
        if digests[0] != digests[1]:
            raise SystemExit("hash seed outputs differ")
        return
    if args.mode == "freeze":
        phase_4s.write_json(args.output, frozen_manifest())
        return
    if args.mode == "holdout":
        if args.manifest is None:
            parser.error("holdout requires --manifest")
        if json.loads(args.manifest.read_text(encoding="utf-8")) != json.loads(json.dumps(frozen_manifest())):
            raise ValueError("frozen inputs or schedule changed")
    result = historical() if args.mode == "historical" else run_panel(args.mode)
    result.update(wall_seconds=perf_counter() - started, process_peak_resident_bytes=peak_resident_bytes())
    if args.mode == "holdout":
        result["gates"] = phase_4t.promotion_gates(result)
        coverage = result["summary"]["coverage"]
        result["gates"]["E"].update(profitable_covers_preserved=not result["summary"]["profitable_cover_regressions"],
                                     accepted_adjustments=coverage["accepted"] > 0)
    phase_4s.write_json(args.output, result)


if __name__ == "__main__":
    main()
