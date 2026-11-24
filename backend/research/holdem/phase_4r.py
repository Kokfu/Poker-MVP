"""Phase 4R offline replay, support audit and paired exact river evaluation."""
from argparse import ArgumentParser
from dataclasses import asdict
import json
from math import fsum
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import numpy as np

from coach.service import HERO, _replay
from research.holdem import phase_4p as prior_reference, phase_4q as wager_reference
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, peak_resident_bytes, train
from research.holdem.phase_4l import exact_values, modeled_continuation, payoff_values, reference
from research.holdem.phase_4m import check_menu, oracle_response, reply_nodes
from research.holdem.phase_4o import PriorTrace
from research.holdem.phase_4o import Case as HistoricalCase
from research.holdem.phase_4q_diagnostics import verify_manifest
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import Opening, hand_group
from research.holdem.river_wager_reference import law
from simulation.actions import Action
from solver.bot import ReplayError, map_action, replay_hand
from solver.combos import COMBOS, COMBO_COUNT, card_mask, combo_index


PANELS = {"development": (438201, 4, (141,)), "holdout": (438202, 8, (151, 152, 153))}
PREFIXES = (0, 3, 30, 100)


class RangeSupportError(ReplayError):
    """Valid public input produced no usable model support."""


def conditional_range(weights, excluded):
    """Normalize positive compatible reach in float64 without adding mass."""
    if weights.shape != (COMBO_COUNT,) or not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("invalid reach weights")
    legal = np.where(excluded, 0.0, weights)
    scale = float(legal.max())
    if scale == 0:
        reason = "all positive holdings blocked" if weights.any() else "zero model reach"
        raise RangeSupportError(reason)
    scaled = legal / scale
    return scaled / scaled.sum()


class SupportReplay(PriorTrace):
    """Research-only. Solve every positive board-legal column, with no likelihood floor."""

    prune = 0.0

    def _solve(self, state, board, ranges, hero_combo, hero, profile=None):
        blocked = card_mask(board)
        for player, weights in enumerate(ranges):
            try:
                conditional_range(weights, blocked)
            except RangeSupportError as error:
                raise RangeSupportError(f"{state.street} start, seat {player}: {error}") from error
        return super()._solve(state, board, ranges, hero_combo, hero, profile)

    def _apply_strategy(self, weights, solve, node, choice):
        updated = super()._apply_strategy(weights, solve, node, choice)
        if not updated.any():
            street = solve.tree.nodes[node].state.street
            raise RangeSupportError(f"{street} observed action: zero model reach")
        return updated

    def _decide(self, ds, profile=None):
        self.actions.clear()
        self.roots.clear()
        action, explanation = super()._decide(ds, profile)
        if ds.street != "preflop":
            board, weights, hero = self.roots[ds.street]
            villain = 1 if ds.acting_player == ds.button_player else 0
            weights = next((
                updated for _, solved, index, _, updated in reversed(self.actions)
                if solved.tree.nodes[index].state.street == ds.street
                and solved.tree.nodes[index].player == villain
            ), weights)
            conditional_range(weights, card_mask((*board, *COMBOS[hero])))
        return action, explanation


def failed_case():
    return tuple(wager_reference.cases(437202, 12, 0))[4]


def replay_trace(bot, case, profile):
    """Audit the same public path the Coach advisor uses, including failures."""
    if profile:
        profile.attach(bot)
    status, payload, engine = _replay(case.spot(), bot, profile.snapshot if profile else None)
    assert status == "hero_to_act"
    ds = engine.decision_observation(HERO).decision_state
    replay = replay_hand(ds)
    hero = replay.current.to_act
    assert engine.state.pot + sum(engine.state.stacks.values()) == 2 * case.depth * BIG_BLIND
    trace = []

    def snapshot(event, player, weights, board, before=None, cutoff=None, selected=None):
        legal = np.array([not set(combo).intersection((*ds.hole_cards, *board))
                          for combo in COMBOS]) if player != hero else ~card_mask(board)
        conditioned = weights * legal
        mass = float(conditioned.sum())
        raw = float(weights.sum())
        normalized = conditioned / mass if mass else None
        entry = {
            "event": event, "seat": player, "board": board, "board_and_hero_cards": (*board, *ds.hole_cards),
            "board_compatible_positive": int(np.count_nonzero(weights)), "raw_mass": raw,
            "legal_positive": int(np.count_nonzero(conditioned)), "legal_raw_mass": mass,
            "normalization_sum": float(normalized.sum()) if mass else None,
            "effective": float(1 / (normalized @ normalized)) if mass else None,
            "remaining_legal_holdings": [combo for combo, w in zip(COMBOS, conditioned, strict=True) if w > 0],
        }
        if before is not None:
            before_mass = float(before.sum())
            entry.update(removed_raw_mass=before_mass - raw,
                         removed_mass_fraction=(before_mass - raw) / before_mass if before_mass else None,
                         removed_legal_mass=float(((before - weights) * legal).sum()))
            if event == "reveal":
                entry["eliminated_holdings"] = [
                    combo for combo, w, new in zip(COMBOS, before, weights, strict=True) if w > 0 and new == 0
                ]
        if cutoff is not None:
            entry["relative_cutoff"] = cutoff
            entry["solve_columns"] = selected.tolist()
        trace.append(entry)

    weights = [np.ones(COMBO_COUNT), np.ones(COMBO_COUNT)]
    chart = bot.charts.trees[bot.chart_depth]
    node = chart.root
    for step in (s for s in replay.steps if s.street == "preflop"):
        choice = map_action(chart, node, step.kind, step.target)
        updated = weights[step.player] * bot.chart_policy(node)[choice]
        snapshot(step.kind, step.player, updated, (), weights[step.player])
        weights[step.player] = updated
        node = chart.nodes[node].children[choice]
    actions = iter(bot.actions)
    for street, (board, _, _) in bot.roots.items():
        for p in (0, 1):
            updated = np.where(card_mask(board), 0.0, weights[p])
            snapshot("reveal", p, updated, board, weights[p])
            weights[p] = updated
        for step in (s for s in replay.steps if s.street == street):
            result = next(actions, None)
            if result is None:
                break
            incoming, solve, index, choice, updated = result
            p = step.player
            assert solve.tree.nodes[index].player == p and np.array_equal(incoming, weights[p])
            retained = np.zeros_like(incoming)
            selected = solve.combos[p]
            retained[selected] = incoming[selected]
            snapshot("solve_cutoff", p, retained, board, incoming, bot.prune, selected)
            snapshot(step.kind, p, updated, board, retained)
            trace[-1]["mapped_action"] = solve.tree.nodes[index].actions[choice]
            weights[p] = updated
    assert next(actions, None) is None
    return {"case": asdict(case), "steps": [asdict(step) for step in replay.steps],
            "advice": payload["advice"], "explanation": payload["explanation"], "trace": trace}


def arm(bot, case, profile, exact, style, ds):
    started = perf_counter()
    try:
        node, ds, advice = bot.trace(case.spot(), profile)
    except RuntimeError:
        if not bot.fallback_count:
            raise
        entry = bot.decision_trace[-1]
        if entry["action"] not in ds.legal_actions or (entry["target"] is not None and not
                ds.minimum_legal_target <= entry["target"] <= ds.maximum_legal_target):
            raise AssertionError("illegal fallback action")
        return {"failure": bot.last_explanation, "fallback_action": [entry["action"], entry["target"]],
                "seconds": perf_counter() - started}
    seconds = perf_counter() - started
    holdings = exact.holdings
    keys = check_menu(bot, node, ds, advice)
    mix = bot.probabilities
    assert np.isfinite(mix).all() and (mix >= 0).all() and abs(fsum(mix) - 1) < 1e-12
    weights, _, replies, hero_policy, values = modeled_continuation(bot, node, holdings)
    assert np.isfinite(weights).all() and (weights >= 0).all() and abs(fsum(weights) - 1) < 1e-12
    assert np.isfinite(values).all()
    state = reference(case, node)
    assert (state.pot, state.villain_commit) == (ds.pot, case.bet)
    assert abs(payoff_values(bot.river.tree, node, holdings, weights, replies, hero_policy)
               - values).max() < .003
    oracle_replies = {reply.index: oracle_response(reply, holdings, style, False)
                      for reply in reply_nodes(bot.river.tree, node)}
    action_ev = exact_values(exact, state, keys, style.call_probability)
    truth = np.array([h.weight for h in holdings])
    independent = payoff_values(bot.river.tree, node, holdings, truth, oracle_replies, hero_policy) / BIG_BLIND
    assert np.allclose(independent, list(action_ev.values()), atol=1e-10, rtol=0)
    win = np.array([(h.result + 1) / 2 for h in holdings])
    ev = float(mix @ list(action_ev.values()))
    equity = float(weights @ win)
    closing = set(keys) <= {"fold", "call", "all_in"} and len(keys) == 2 and state.villain_stack == 0
    threshold = (state.villain_commit - state.hero_commit) / (
        state.pot + state.villain_commit - state.hero_commit) if closing else None
    return {
        "keys": keys, "mix": dict(zip(keys, mix.tolist(), strict=True)), "exact_action_ev": action_ev, "ev": ev,
        "regret": max(action_ev.values()) - ev, "modeled_action_ev": dict(zip(keys, values / BIG_BLIND, strict=True)),
        "effective": float(1 / (weights @ weights)), "positive": int(np.count_nonzero(weights)),
        "equity": equity, "missing_reference_mass": float(truth[weights == 0].sum()),
        "closing_threshold": threshold,
        "closing_equity_margin": equity - threshold if closing else None,
        "seconds": seconds,
    }


def evaluate(case, name, stream, prefix, profile):
    # Geometry and public actions come from the independent engine replay,
    # even when the baseline solver cannot produce a strategy.
    status, _, engine = _replay(case.spot())
    assert status == "hero_to_act"
    ds = engine.decision_observation(HERO).decision_state
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    steps = [s for s in replay.steps if s.player == villain]
    pre_history = tuple(prior_reference.observations(replay, villain, case.seat == "button"))
    style = STYLES[name]
    universe = ExactRiverEV(case.hero, case.board, lambda *_: 1).holdings
    pairs = [h.combo for h in universe]
    prior = prior_reference.reference_weights(pairs, pre_history, case.depth, style)
    for step in steps[:-1]:
        if step.street != "preflop":
            board = list(case.board[:3 if step.street == "flop" else 4])
            prior *= [prior_reference.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                      for pair in pairs]
    before = steps[-1].before
    opening = Opening(before.pot, before.stack[villain], before.stack[1 - villain],
                      before.last_full_raise, case.line[1] != "check")
    observed, _, _ = opening.action(steps[-1].target)
    likelihood = [law(opening, hand_group(h.combo, case.board, h.rank), style)[observed] for h in universe]
    prior_by_pair = dict(zip(pairs, prior, strict=True))
    wager_by_pair = dict(zip(pairs, likelihood, strict=True))
    truth = posterior(case.hero, case.board, prior_by_pair.__getitem__, wager_by_pair.__getitem__)
    exact = ExactRiverEV(case.hero, case.board, lambda pair, _: prior_by_pair[pair] * wager_by_pair[pair])
    assert np.allclose(list(truth.values()), [h.weight for h in exact.holdings], atol=1e-14, rtol=0)
    arms = {key: arm(bot, case, profile, exact, style, ds)
            for key, bot in (("baseline", PriorTrace()), ("candidate", SupportReplay()))}
    baseline, candidate = arms.values()
    if "failure" not in baseline and "failure" not in candidate:
        assert baseline["keys"] == candidate["keys"] and baseline["exact_action_ev"] == candidate["exact_action_ev"]
    elif "failure" in baseline and "failure" not in candidate:
        action = label(Action(*baseline["fallback_action"]))
        baseline["fallback_exact_ev"] = candidate["exact_action_ev"].get(action)
    return {"case": asdict(case), "opponent": name, "stream": stream, "prefix": prefix,
            "true_equity": fsum(h.weight * (h.result + 1) / 2 for h in exact.holdings), **arms}


def historical_diagnostics(directory):
    """Replay archived inputs and stress the previously observed bad call posteriors."""
    specs = (("historical", ("Js", "3c"), "loose_aggressive", 91, "true", "baseline"),
             ("diagnostic-13", ("Kc", "As"), "tight_passive", 132, "production", "candidate"))
    results = []
    for filename, hero, name, stream, prior_kind, bad_arm in specs:
        archive = json.loads((directory / f"{filename}.json").read_text(encoding="utf-8-sig"))
        row = next(r for r in archive["rows"] if tuple(r["case"]["hero"]) == hero
                   and r["opponent"] == name and r["stream"] == stream)
        case_type = HistoricalCase if filename == "historical" else wager_reference.WagerCase
        case = case_type(**{**row["case"], "hero": hero, "board": tuple(row["case"]["board"]),
                            "line": tuple(row["case"]["line"])})
        profile = train(name, stream, (row["hands"],))[row["hands"]] if row["hands"] else None
        _, _, engine = _replay(case.spot())
        ds = engine.decision_observation(HERO).decision_state
        evidence = row["evidence"]
        bad = np.asarray(evidence["posterior"][prior_kind][bad_arm])
        oracle = np.asarray(evidence["posterior"][prior_kind]["oracle"])
        posterior_truth = dict(zip(map(tuple, evidence["combos"]), evidence["true_posterior"], strict=True))
        exact = ExactRiverEV(case.hero, case.board, lambda pair, _: posterior_truth[pair])
        payoff = {h.combo: (h.result + 1) / 2 for h in exact.holdings}
        outcomes = np.array([payoff[tuple(pair)] for pair in evidence["combos"]])
        threshold = case.bet / (case.pot + 2 * case.bet)
        tv = float(abs(bad - oracle).sum() / 2)
        curve = []
        for amount in (0, .01, .05, .10, .25, .50, 1):
            weights = (1 - amount) * bad + amount * oracle
            equity = float(weights @ outcomes)
            modeled_call = (equity * (case.pot + 2 * case.bet) - case.bet) / BIG_BLIND
            curve.append({"fraction_toward_wager_oracle": amount, "tv_from_bad": amount * tv,
                          "equity": equity, "modeled_call_ev": modeled_call,
                          "greedy_exact_regret": -row["exact_ev_bb"]["all_in"] if equity > threshold else 0})
        arms = {key: arm(bot, case, profile, exact, STYLES[name], ds)
                for key, bot in (("baseline", PriorTrace()), ("support_only", SupportReplay()))}
        assert np.isclose(row["exact_ev_bb"]["all_in"], min(arms["baseline"]["exact_action_ev"].values()),
                          atol=1e-12, rtol=0)
        results.append({"case": asdict(case), "opponent": name, "stream": stream,
                        "archive": {k: row[k] for k in ("exact_ev_bb", "decision", "posterior")},
                        "threshold": threshold, "perturbations": curve, **arms})
    return {"rows": results}


def summarize(rows):
    failures = [{"case": row["case"], "stream": row["stream"], "opponent": row["opponent"],
                 "arm": name, "details": row[name]["failure"]}
                for row in rows for name in ("baseline", "candidate") if "failure" in row[name]]
    pairs = [row for row in rows if all("failure" not in row[name] for name in ("baseline", "candidate"))]
    if not pairs:
        return {"matched": 0, "failures": failures, "gate": False}

    def delta(row):
        return row["candidate"]["ev"] - row["baseline"]["ev"]

    diffs = [delta(row) for row in pairs]
    board_ids = sorted({row["case"]["index"] for row in pairs})
    streams = sorted({row["stream"] for row in pairs})
    by_cell = {(board, stream): [delta(row) for row in pairs if row["case"]["index"] == board
                                and row["stream"] == stream] for board in board_ids for stream in streams}
    interval = None
    if not failures:
        matrix = np.array([[mean(by_cell[board, stream]) for stream in streams] for board in board_ids])
        rng = np.random.default_rng(43803)
        b = rng.integers(len(board_ids), size=(10000, len(board_ids), 1))
        s = rng.integers(len(streams), size=(10000, 1, len(streams)))
        interval = np.quantile(matrix[b, s].mean(axis=(1, 2)), (.025, .975)).tolist()
    summary = {
        "matched": len(pairs), "failures": failures, "mean_delta": mean(diffs), "interval": interval,
        "worst": min(diffs), "worst_key": {k: min(pairs, key=delta)[k] for k in ("case", "stream", "opponent")},
        "harm_over_0.01": sum(x < -.01 for x in diffs),
        "modal_changes": sum(max(r["baseline"]["mix"], key=r["baseline"]["mix"].get)
                             != max(r["candidate"]["mix"], key=r["candidate"]["mix"].get) for r in pairs),
        "by_opponent": {name: mean(delta(r) for r in pairs if r["opponent"] == name)
                        for name in sorted({r["opponent"] for r in pairs})},
    }
    for name in ("baseline", "candidate"):
        action_keys = sorted({k.split("_")[0] for row in pairs for k in row[name]["mix"]})
        margins = [abs(row[name]["closing_equity_margin"]) for row in pairs
                   if row[name]["closing_equity_margin"] is not None]
        summary[name] = {
            **{k: mean(row[name][k] for row in pairs)
               for k in ("ev", "regret", "effective", "positive", "missing_reference_mass")},
            "median_seconds": median(row[name]["seconds"] for row in pairs),
            "max_seconds": max(row[name]["seconds"] for row in pairs),
            "closing_margin_counts": {"rows": len(margins), "within_0.01": sum(v <= .01 for v in margins),
                                      "within_0.05": sum(v <= .05 for v in margins)},
            "action_shares": {kind: mean(fsum(v for k, v in row[name]["mix"].items() if k.split("_")[0] == kind)
                                         for row in pairs) for kind in action_keys},
        }
    summary["gate"] = bool(interval and interval[0] > 0 and mean(diffs) >= .05 and min(diffs) >= -.50
                           and summary["harm_over_0.01"] / len(pairs) <= .10
                           and min(summary["by_opponent"].values()) >= -.03
                           and summary["candidate"]["median_seconds"] <= 2 * summary["baseline"]["median_seconds"]
                           and summary["candidate"]["max_seconds"] <= 15)
    return summary


def run_panel(panel):
    seed, count, streams = PANELS[panel]
    cases = [list(wager_reference.cases(seed, count, orientation)) for orientation in range(len(streams))]
    profiles = {(stream, name): train(name, stream, PREFIXES[1:]) for stream in streams for name in STYLES}
    rows = []
    for index in range(count):
        for orientation, stream in enumerate(streams):
            prefix = PREFIXES[(index + orientation) % len(PREFIXES)]
            for name in STYLES:
                rows.append(evaluate(cases[orientation][index], name, stream, prefix,
                                     profiles[stream, name].get(prefix)))
        print(f"Board {index + 1}/{count}: {len(rows)} rows", flush=True)
    return {"rows": rows, "summary": summarize(rows)}


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("panel", choices=("failure", "historical", *PANELS))
    cli.add_argument("output", type=Path)
    cli.add_argument("--manifest", type=Path)
    cli.add_argument("--archive", type=Path)
    args = cli.parse_args()
    if args.output.exists():
        cli.error("output already exists")
    if args.panel == "holdout" and args.manifest is None:
        cli.error("holdout requires the frozen input manifest")
    if args.panel == "historical" and args.archive is None:
        cli.error("historical requires the Phase 4Q evidence directory")
    verified = verify_manifest(args.manifest) if args.manifest else None
    start = perf_counter()
    if args.panel == "failure":
        case = failed_case()
        profile = train("tight_aggressive", 131, (3,))[3]
        result = {"baseline": replay_trace(PriorTrace(), case, profile),
                  "candidate": replay_trace(SupportReplay(), case, profile),
                  "exact": evaluate(case, "tight_aggressive", 131, 3, profile)}
    elif args.panel == "historical":
        result = historical_diagnostics(args.archive)
    else:
        result = run_panel(args.panel)
    result.update(panel=args.panel, frozen_inputs_verified=verified, wall_seconds=perf_counter() - start,
                  process_peak_resident_bytes=peak_resident_bytes())
    if args.panel in PANELS:
        result["summary"]["gate"] &= result["process_peak_resident_bytes"] <= 768 * 1024**2
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
