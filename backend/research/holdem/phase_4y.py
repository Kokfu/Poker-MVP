"""Offline river reply calibration and recommendation risk audit."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import fsum, log
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter
import traceback

import numpy as np

from research.holdem import phase_4q, phase_4s, phase_4t, phase_4u, phase_4w, phase_4x
from research.holdem.decoupled_replay import hand_tiers
from research.holdem.live_trace import assert_legal
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, strength, to_action, train
from research.holdem.phase_4l import exact_values
from research.holdem.phase_4m import group_indices, oracle_response
from research.holdem.reply_forecast import ResponseAssumptions, forecast, holding_values, reply_geometry, river_counts
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import hand_group
from solver.bot import SolverBot
from solver.combos import combo_index
from solver.tree import SizeMenu, StreetState, StreetTree


BOARD_SEED = 449202
BOARD_COUNT = 8
STREAMS = (331, 332)
PREFIXES = (0, 3, 30, 100)
CHOOSER = 917
EVIDENCE = phase_4x.EVIDENCE
GRID = (0.25, 0.5, 1., 1.5)
ARMS = ("A", "B", "C")


def schedule():
    boards = [list(phase_4q.cases(BOARD_SEED, BOARD_COUNT, i)) for i in range(len(STREAMS))]
    return [(cases[board], stream, PREFIXES[(board + i) % len(PREFIXES)], name)
            for board in range(BOARD_COUNT) for i, (stream, cases) in enumerate(zip(STREAMS, boards, strict=True))
            for name in STYLES]


def manifest():
    files = phase_4x.manifest()["sources"]
    protocol = "PHASE_4Y_PROTOCOL.md"
    files[protocol] = sha256((phase_4w.REPO / protocol).read_bytes()).hexdigest()
    return {"sources": files, "schedule": [[asdict(case), stream, prefix, name]
                                           for case, stream, prefix, name in schedule()]}


@dataclass
class Field:
    reference: ExactRiverEV

    def __post_init__(self):
        self.ids = np.array([combo_index(h.combo) for h in self.reference.holdings])
        self.ranks = np.array([h.rank for h in self.reference.holdings])
        self.outcomes = np.array([h.result for h in self.reference.holdings])
        self.weights = np.array([h.weight for h in self.reference.holdings])


def action_risk(policy, values, incumbent):
    """Measure a realized choice in action space using conditional reference EV."""
    mix, selected = policy["mix"], policy["action"]
    modal = min(mix, key=lambda key: (-mix[key], key))
    best = max(values.values())
    baseline = values[incumbent["action"]]
    exact_ev = phase_4x.score(mix, values)
    return {
        "ev": exact_ev, "regret": best - exact_ev, "modal": modal,
        "selected_ev": values[selected], "modal_ev": values[modal],
        "selected_delta": values[selected] - baseline, "modal_delta": values[modal] - baseline,
        "selected_regret": best - values[selected], "modal_regret": best - values[modal],
        "max_supported_regret": max(best - values[key] for key, mass in mix.items() if mass > 0),
        "harmful_mass": fsum(mass for key, mass in mix.items() if values[key] - baseline < -.50),
    }


def wager_category(node):
    g = reply_geometry(node.state)
    if node.state.stack[1 - node.player] == 0 or g.cost == g.effective_stack:
        return "closing_shove"
    ratio = g.cost / g.pot_before_wager
    return "small" if ratio <= .33 else "medium" if ratio < 1 else "pot" if ratio == 1 else "overbet"


def grouped(node, matrix):
    if (matrix.shape[0] != len(node.actions) or not np.isfinite(matrix).all() or
            (matrix < 0).any() or not np.allclose(matrix.sum(axis=0), 1, atol=1e-12, rtol=0)):
        raise AssertionError("invalid concrete reply law")
    return np.array([matrix[list(indices)].sum(axis=0) for indices in group_indices(node)])


def probability_scores(node, predicted, truth, weights, groups):
    predicted, truth = grouped(node, predicted), grouped(node, truth)
    error = predicted - truth
    return {
        "predicted": (predicted @ weights).tolist(), "truth": (truth @ weights).tolist(),
        "marginal_excess_brier": float(np.sum((error @ weights) ** 2)),
        "holding_excess_brier": float(np.sum(error ** 2, axis=0) @ weights),
        "log_loss": float((-np.log(predicted.clip(1e-12)) * truth).sum(axis=0) @ weights),
        "reference_log_loss": float((-np.log(truth.clip(1e-12)) * truth).sum(axis=0) @ weights),
        "by_tier_and_blocker": {
            str(group): {"mass": float(weights[groups == group].sum()),
                         "fold_bias_mass": float(error[0, groups == group] @ weights[groups == group])}
            for group in range(6)
        },
    }


def calibrate_native(ds, field, style, posterior, context, policy):
    """Price every offered branch, using one fixed Hero continuation for reply swaps."""
    solve, root, hero_id = context
    hero = root.player
    hero_col = np.searchsorted(solve.combos[hero], hero_id)
    hero_policy = {n.index: solve.average[n.index][:, hero_col] for n in solve.tree.nodes
                   if n.kind == "decision" and n.player == hero}
    keys, modeled, present, replies = phase_4x.modeled_payoffs(context, field.ids, field.ranks, field.outcomes, ds)
    model_weights = phase_4x.normalize(posterior[field.ids] * present)
    projected = modeled @ model_weights
    pending = root.children.copy()
    plain = {}
    while pending:
        node = solve.tree.nodes[pending.pop()]
        pending.extend(node.children)
        if node.index in replies:
            plain[node.index] = oracle_response(node, field.reference.holdings, style, raising=False)
    substituted = holding_values(solve.tree, root, field.outcomes, plain, hero_policy,
                                 ds.acting_player == "b") / BIG_BLIND
    grades = np.array([hand_group(h.combo, tuple(ds.board_cards), h.rank) for h in field.reference.holdings])
    branches = []
    for i, (action, child_index) in enumerate(zip(keys, root.children, strict=True)):
        if child_index not in replies:
            continue
        node = solve.tree.nodes[child_index]
        stats = probability_scores(node, replies[child_index], plain[child_index], field.weights, grades)
        model_stats = probability_scores(node, replies[child_index], plain[child_index], model_weights, grades)
        branches.append({
            **stats, "on_model": model_stats, "category": wager_category(node), "action": action,
            "tree_target": root.actions[i][1], "reply_menu": node.labels,
            "geometry": asdict(reply_geometry(node.state)), "usage": policy["mix"][action],
            "predicted_ev": float(projected[i]), "truth_ev": float(substituted[i] @ field.weights),
            "reply_swap_ev": float(substituted[i] @ model_weights),
            "common_range_predicted_ev": float(modeled[i] @ field.weights),
            "reference_mass_outside_columns": float(field.weights[~present].sum()),
        })
    return branches, dict(zip(keys, projected.tolist(), strict=True))


def grid_scores(case, ds, field, style, counts):
    """Probe additional exact targets on a checked-to counterfactual price grid."""
    pot = case.pot
    assumptions = ResponseAssumptions.from_counts(*counts)
    legal_ids, legal_tiers = hand_tiers(tuple(ds.board_cards))
    tiers = legal_tiers[np.searchsorted(legal_ids, field.ids)]
    grades = np.array([hand_group(h.combo, tuple(ds.board_cards), h.rank) for h in field.reference.holdings])
    covers = strength(RANKER.score(list(case.hero), list(case.board))) == 2
    results = []
    for stack in (3 * pot // 4, 3 * pot):
        state = StreetState("river", 0, (0, 0), (stack, stack), (pot // 2, pot - pot // 2), BIG_BLIND,
                            acted=(False, True))
        tree = StreetTree(state, SizeMenu((GRID, ()), all_in_merge=1.))
        root = tree.nodes[tree.root]
        hero_tail = {n.index: np.array([float(kind == ("call" if covers else "fold")) for kind, _ in n.actions])
                     for n in tree.nodes if n.player == 0 and n.kind == "decision" and n.index != root.index}
        for index, child in enumerate(root.children):
            node = tree.nodes[child]
            if node.kind != "decision":
                continue
            predicted = forecast(node, tiers, assumptions)
            truth = oracle_response(node, field.reference.holdings, style, raising=True)
            stats = probability_scores(node, predicted, truth, field.weights, grades)
            cost = reply_geometry(node.state).cost
            call_payoff = showdown_payoff(field.outcomes, pot, cost, ds.acting_player == "b")
            shove_payoff = (showdown_payoff(field.outcomes, pot, stack, ds.acting_player == "b")
                            if covers else np.full(len(field.ids), -cost))
            transfers = np.array([np.full(len(field.ids), pot), call_payoff, shove_payoff]) / BIG_BLIND
            reference_payoff = (grouped(node, truth) * transfers).sum(axis=0)
            predicted_payoff = (grouped(node, predicted) * transfers).sum(axis=0)
            for probabilities, payoff in ((predicted, predicted_payoff), (truth, reference_payoff)):
                np.testing.assert_allclose(holding_values(tree, replace(root, children=[child]), field.outcomes,
                                                         {child: probabilities}, hero_tail, ds.acting_player == "b")[0],
                                           payoff * BIG_BLIND, rtol=0, atol=1e-10)
            results.append({**stats, "category": wager_category(node), "action": root.labels[index],
                            "tree_target": root.actions[index][1], "geometry": asdict(reply_geometry(node.state)),
                            "reply_menu": node.labels, "predicted_ev": float(predicted_payoff @ field.weights),
                            "truth_ev": float(reference_payoff @ field.weights), "usage": None})
    return results


def showdown_payoff(outcomes, pot, paid, odd):
    contest = pot + 2 * paid
    return np.where(outcomes > 0, contest, np.where(outcomes == 0, (contest + odd) // 2, 0)) - paid


def fold_stress(node, field, style, state, action, alternate_weights):
    """Shift odds on all holdings while preserving their ordering."""
    price = reply_geometry(node.state)
    grouped_truth = grouped(node, oracle_response(node, field.reference.holdings, style, raising=False))
    folds = grouped_truth[0]
    call_value = showdown_payoff(field.outcomes, price.pot_before_wager, price.cost, state.hero_gets_odd_chip)
    # A river raise also pays Hero's amount to call, outside the incremental wager.
    call_value -= state.villain_commit - state.hero_commit
    model = []
    for name, weights in (("reference", field.weights), ("alternate", alternate_weights)):
        for tilt in (-log(1.25), 0., log(1.25)):
            odds = np.exp(tilt)
            shifted = folds * odds / (1 - folds + folds * odds)
            value = float((shifted * state.pot + (1 - shifted) * call_value) @ weights / BIG_BLIND)
            if not tilt and name == "reference":
                expected = field.reference.action_ev(state, to_action(action), style.call_probability) / BIG_BLIND
                assert abs(value - expected) < 1e-10
            model.append({"range": name, "log_odds_shift": tilt, "fold": float(shifted @ weights), "ev": value})
    return model


def replay_row(case, stream, prefix, name, profile, reverse=False, detailed=False):
    spot, style = case.spot(), STYLES[name]
    phase_4x.warm(spot)
    snapshot = profile.snapshot if profile else None
    replays = {tag: phase_4x.witness(spot, tag, profile) for tag in ("BA" if reverse else "AB")}
    a, ds, a_range, _, _, _, _ = replays["A"]
    b, ds_b, b_range, _, b_context, observations, _ = replays["B"]
    assert ds == ds_b and (ds.opponent_stack == 0) == case.shove and len(observations) == 1
    assert len(b["columns"]) == 1 and max(b["columns"][0]) <= 896
    state = phase_4x.wager_state(ds)
    c = phase_4x.candidate(ds, state, a, b)
    arms = dict(zip(ARMS, (a, b, c), strict=True))
    keys = sorted(a["mix"].keys() | b["mix"].keys())
    for arm in arms.values():
        assert abs(fsum(arm["mix"].values()) - 1) <= 1e-12 and arm["mix"][arm["action"]] > 0
        assert all(np.isfinite(p) and p >= 0 for p in arm["mix"].values())
    for key in keys:
        assert_legal(ds, to_action(key))

    # The exact references enter after all advice and policies have been fixed.
    reference = phase_4s.exact_reference(case, ds, style)
    field = Field(reference)
    values = exact_values(reference, state, keys, style.call_probability)
    phase_4w.verify_exact_payoffs(reference, state, values, style.call_probability)
    for arm in arms.values():
        arm.update(action_risk(arm, values, a))
    modeled, modeled_action_ev = {}, {}
    counts = river_counts(snapshot)
    for tag, (_, _, posterior, _, context, _, _) in replays.items():
        modeled[tag], modeled_action_ev[tag] = calibrate_native(ds, field, style, posterior, context, arms[tag])
        for branch in modeled[tag]:
            assert abs(branch["truth_ev"] - values[branch["action"]]) < 1e-10
    delta = c["ev"] - a["ev"]
    if c["fraction"]:
        assert delta >= c["fraction"] * c["unclipped_lower_bb"] - 1e-12
    else:
        assert c["mix"] == a["mix"] and c["action"] == a["action"]
    rows = {"board_index": case.index, "stream": stream, "prefix": prefix, "opponent": name,
            "case": asdict(case), "state": asdict(state), "closing": case.shove,
            "legal_actions": list(ds.legal_actions),
            "legal_targets": [ds.minimum_legal_target, ds.maximum_legal_target],
            "observed_reply_counts": counts, "values": values, "arms": arms,
            "native": modeled, "modeled_action_ev": modeled_action_ev,
            "grid": [] if detailed else grid_scores(case, ds, field, style, counts),
            "range_tv": {k: float(abs(p[field.ids] - field.weights).sum() / 2)
                         for k, p in (("A", a_range), ("B", b_range))},
            "range_effective": {k: float(1 / (p @ p)) for k, p in
                                (("A", a_range[field.ids]), ("B", b_range[field.ids]), ("reference", field.weights))}}
    solve, root, _ = b_context
    rows["stress"] = {label(SolverBot._legalize(ds, *action)):
                      fold_stress(solve.tree.nodes[child], field, style, state,
                                  label(SolverBot._legalize(ds, *action)), b_range[field.ids])
                      for action, child in zip(root.actions, root.children, strict=True)
                      if solve.tree.nodes[child].kind == "decision"}
    if detailed:
        prior, likelihood = observations[0]
        ref_prior, ref_likelihood = phase_4x.reference_factors(case, ds, style, reference.holdings)
        rows["weights"] = {"holdings": [h.combo for h in reference.holdings],
                           "reference": field.weights.tolist(), "A": a_range[field.ids].tolist(),
                           "B": b_range[field.ids].tolist(), "prior_B": phase_4x.normalize(prior[field.ids]).tolist(),
                           "observed_wager_B": likelihood[field.ids].tolist(),
                           "prior_reference": ref_prior.tolist(), "observed_wager_reference": ref_likelihood.tolist()}
        rows["actions"] = [asdict(action) for action in spot.actions]
        if 0 < c["fraction"] < 1:
            token = f"solver|{CHOOSER}|{ds.match_id}|{ds.hand_id}|{ds.hand_number}|{ds.street}|{len(ds.hand_actions)}"
            draw = Random(int.from_bytes(sha256(token.encode()).digest()[:8], "big")).random() * (1 - 1e-12)
            c["sampling_draw"] = draw
            c["sampling_order"] = list(c["mix"])
            incumbent_order = list(a["mix"]) + sorted(c["mix"].keys() - a["mix"].keys())
            c["sample_with_incumbent_order"] = incumbent_order[SolverBot(seed=CHOOSER)._pick(
                ds, np.array([c["mix"].get(key, 0.) for key in incumbent_order]))]
    return rows


def read_rows(phase, filename, date="2026-11-19"):
    return json.loads((EVIDENCE / f"phase-{phase}-{date}" / f"{filename}.json")
                      .read_text(encoding="utf-8-sig"))["rows"]


def replay_archive(old, schedule_rows, tags):
    case, stream, prefix, name = next(entry for entry in schedule_rows if
                                     (entry[0].index, entry[1], entry[3]) == phase_4x.key(old))
    profile = train(name, stream, (prefix,))[prefix] if prefix else None
    row = replay_row(case, stream, prefix, name, profile, detailed=True)
    assert old["values"] == row["values"]
    for tag in tags:
        assert all(old["arms"][tag][key] == row["arms"][tag][key] for key in ("mix", "action"))
    return row


def historical():
    old_worst = min(read_rows("4w", "holdout-13"), key=lambda row: row["delta"])
    severe = replay_archive(old_worst, phase_4w.schedule("holdout"), "AB")
    severe["crossed_attribution"] = next(row["cells"] for row in read_rows("4x", "diagnosis-13")
                                         if phase_4x.key(row) == phase_4x.key(old_worst))
    old_seeded = min(read_rows("4x", "holdout-13"), key=lambda row:
                     row["values"][row["arms"]["C"]["action"]] - row["values"][row["arms"]["A"]["action"]])
    seeded = replay_archive(old_seeded, phase_4x.schedule(), "ABC")
    old_u = min(read_rows("4u", "holdout-13", "2026-11-18"),
                key=lambda row: row["arms"]["E"]["ev"] - row["arms"]["A"]["ev"])
    old_call = next(row for row in read_rows("4u", "historical-final", "2026-11-18")
                    if row["case"]["hero"] == ["Jd", "4h"])
    u_cases = []
    for old in (old_u, old_call):
        case = phase_4t.load_case(old, phase_4q.WagerCase)
        name, stream, prefix = (old[k] for k in ("opponent", "stream", "prefix"))
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        row = phase_4u.evaluate(case, stream, prefix, name, profile, history=True)
        assert row["exact_action_ev"] == old["exact_action_ev"]
        baseline = {**row["arms"]["A"], "action": row["arms"]["A"]["chosen"]}
        for tag in ("A", "B", "C", "D", "E"):
            arm = row["arms"][tag]
            assert all(arm[key] == old["arms"][tag][key] for key in ("mix", "chosen"))
            arm.update(action_risk({**arm, "action": arm["chosen"]}, row["exact_action_ev"], baseline))
        row["actions"] = [asdict(action) for action in case.spot().actions]
        u_cases.append(row)
    old_t = next(row for row in read_rows("4t", "holdout-13", "2026-11-18")
                 if row["stream"] == 192 and row["case"]["hero"] == ["Qc", "4s"]
                 and row["opponent"] == "tight_aggressive")
    case = phase_4t.load_case(old_t, phase_4q.WagerCase)
    name, stream, prefix = (old_t[key] for key in ("opponent", "stream", "prefix"))
    profile = train(name, stream, (prefix,))[prefix] if prefix else None
    earlier_call = phase_4t.evaluate(case, stream, prefix, name, profile, vectors=True)
    assert earlier_call["exact_action_ev"] == old_t["exact_action_ev"]
    baseline = earlier_call["arms"]["A"]
    for tag, arm in earlier_call["arms"].items():
        assert all(arm[key] == old_t["arms"][tag][key] for key in ("mix", "chosen"))
        arm.update(action_risk({**arm, "action": arm["chosen"]}, earlier_call["exact_action_ev"],
                               {**baseline, "action": baseline["chosen"]}))
    earlier_call["actions"] = [asdict(action) for action in case.spot().actions]
    return {"rows": [severe, seeded, *u_cases, earlier_call]}


def calibration_table(rows, branches):
    buckets = {}
    for row in rows:
        for branch in branches(row):
            for facet in ("all", row["opponent"], f"prior_hands={row['prefix']}",
                          f"raise_legal={len(branch['reply_menu']) > 2}"):
                buckets.setdefault((facet, branch["category"]), []).append(branch)
    result = {}
    for (facet, category), subset in buckets.items():
        losses = [item["predicted_ev"] - item["truth_ev"] for item in subset]
        usage = [item["usage"] for item in subset] if subset[0]["usage"] is not None else None
        result.setdefault(facet, {})[category] = {
            "n": len(subset),
            "predicted": np.mean([item["predicted"] for item in subset], axis=0).tolist(),
            "truth": np.mean([item["truth"] for item in subset], axis=0).tolist(),
            **{key: mean(item[key] for item in subset) for key in
               ("marginal_excess_brier", "holding_excess_brier", "log_loss", "reference_log_loss")},
            "ev_bias": mean(losses), "ev_mae": mean(map(abs, losses)),
            "max_ev_error": max(map(abs, losses)),
            "mix_weighted_ev_mae": (fsum(weight * abs(error) for weight, error in zip(usage, losses, strict=True))
                                    / fsum(usage) if usage and fsum(usage) else None),
        }
    return result


def comparison(rows, tag, mode):
    pairs = []
    for row in rows:
        arms = {key: {**row["arms"][source]} for key, source in (("A", "A"), ("B", tag))}
        if mode != "mixed":
            for arm in arms.values():
                arm.update(action=arm["modal"] if mode == "modal" else arm["action"],
                           ev=arm[f"{mode}_ev"], regret=arm[f"{mode}_regret"])
                arm["mix"] = {arm["action"]: 1.}
        pairs.append({"board_index": row["board_index"], "stream": row["stream"], "opponent": row["opponent"],
                      "closing": row["closing"], "values": row["values"], "arms": arms,
                      "delta": arms["B"]["ev"] - arms["A"]["ev"]})
    result = phase_4w.summarize(pairs)
    result["severe_count"] = sum(pair["delta"] < -.50 for pair in pairs)
    return result


def risk_summary(rows, tag):
    risks = [row["arms"][tag] for row in rows]
    return {
        "mean_harmful_mass": mean(arm["harmful_mass"] for arm in risks),
        "maximum_harmful_mass": max(arm["harmful_mass"] for arm in risks),
        "supported_regret_max": max(arm["max_supported_regret"] for arm in risks),
        "mixed_regret_max": max(arm["regret"] for arm in risks),
        "safe_mean_but_unsafe_draw": sum(
            arm["selected_delta"] < -.50 and arm["ev"] - row["arms"]["A"]["ev"] >= -.50
            for row, arm in zip(rows, risks, strict=True)),
        "draw_differs_from_mode": sum(arm["action"] != arm["modal"] for arm in risks),
    }


def holdout(reverse, out):
    started = perf_counter()
    profiles = {(stream, name): train(name, stream, PREFIXES[1:]) for stream in STREAMS for name in STYLES}
    rows, failures = [], []
    # Flush each outcome so that an external timeout leaves an auditable prefix.
    with out.with_suffix(".jsonl").open("x", encoding="utf-8") as ledger:
        for index, (case, stream, prefix, name) in enumerate(schedule()):
            try:
                row = replay_row(case, stream, prefix, name, profiles[stream, name].get(prefix),
                                 (index % 2 == 0) == reverse)
                rows.append(row)
                ledger.write(json.dumps(row, allow_nan=False) + "\n")
            except Exception:
                failure = {"index": index, "case": asdict(case), "stream": stream, "prefix": prefix,
                           "opponent": name, "error": traceback.format_exc()}
                failures.append(failure)
                ledger.write(json.dumps(failure) + "\n")
            ledger.flush()
            if (index + 1) % 8 == 0:
                print(f"{index + 1} attempted, {len(failures)} failed", flush=True)
    summary = None
    if not failures:
        summary = {"paired": {tag: {mode: comparison(rows, tag, mode)
                                   for mode in ("mixed", "selected", "modal")} for tag in ("B", "C")},
                   "risk": {tag: risk_summary(rows, tag) for tag in ARMS},
                   "native_calibration": {tag: calibration_table(rows, lambda row: row["native"][tag])
                                          for tag in ("A", "B")},
                   "price_grid_calibration": calibration_table(rows, lambda row: row["grid"])}
    return {"rows": rows, "failures": failures, "summary": summary, "seconds": perf_counter() - started}


def compare(first, second):
    assert not first["failures"] and not second["failures"]
    result = phase_4x.compare({"rows": first["rows"]}, {"rows": second["rows"]})
    phase_4x.compare({"rows": [first["summary"]]}, {"rows": [second["summary"]]})
    assert result["identical_rows"] == len(schedule())
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "historical", "holdout", "compare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--runs", nargs=2, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result = manifest()
    elif args.command == "historical":
        result = historical()
    elif args.command == "holdout":
        saved = json.loads(args.manifest.read_text(encoding="utf-8"))
        assert saved == json.loads(json.dumps(manifest())), "frozen inputs changed"
        result = holdout(args.reverse, args.output)
    else:
        result = compare(*(json.loads(path.read_text(encoding="utf-8")) for path in args.runs))
    phase_4s.write_json(args.output, result)
    if result.get("failures"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
