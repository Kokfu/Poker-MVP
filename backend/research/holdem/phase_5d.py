"""Offline Phase 5D experiment. No production call site."""
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import asdict, replace
from hashlib import sha256
from itertools import combinations, product
import json
import os
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter
from unittest.mock import patch

import numpy as np

from coach import service as coach
from poker_analyzer import FULL_DECK
from research.holdem import action_ev_reference as ledger, phase_4p, phase_5b, river_shadow as shadow
from research.holdem.decoupled_replay import CFRWorkingSet, hand_tiers
from research.holdem.live_persistent import ReplayBeliefs
from research.holdem.phase_4k import RANKER, STYLES, peak_resident_bytes, strength, train
from research.holdem.reply_forecast import ResponseAssumptions, forecast
from research.holdem.river_ev import ExactRiverEV
from solver.bot import SolverBot, STREETS, _EQUITY_CACHE, map_action, replay_hand
from solver.combos import COMBOS, card_mask, combo_index
from solver.preflop import CHART_BB
from solver.tree import SizeMenu


REPO = phase_5b.REPO
WAGERS = {"checked": None, "quarter": .25, "half": .5, "pot": 1., "overbet": 1.25, "closing": None}
PREFIXES = (0, 3, 30, 100)
BOARD_LENGTH = dict(zip(STREETS, (0, 3, 4, 5), strict=True))
EPS = 1e-12
MATERIAL = .01
PROBE_MENU = SizeMenu(by_depth=((.25, .5, 1., 1.25), (.5, 1.), (1.,)))
BINS = (0., .0001, .001, .002, .005, .01, .05, .1, .2, .4, .6, .8, 1.000001)


def schedule():
    factors = list(product(STYLES, WAGERS, PREFIXES))
    Random(659203).shuffle(factors)
    for case, (style, wager, prefix) in zip(phase_4p.cases(659202, len(factors), 2), factors, strict=True):
        i = case.index
        if i % 6 in (0, 1):
            case = replace(case, path="limped", open_to=100)
        fraction = WAGERS[wager]
        if fraction and case.behind <= int(case.pot * fraction):
            case = replace(case, depth=30)
        case = replace(case, shove=wager == "closing")
        spot = case.spot()
        if case.path == "limped":
            sb, bb = ("hero", "villain") if case.seat == "button" else ("villain", "hero")
            spot.actions[:2 if case.seat == "button" else 3] = [
                coach.SpotAction(sb, "call"), coach.SpotAction(bb, "check")]
        if wager == "checked":
            if case.seat == "button":
                spot.actions[-1] = coach.SpotAction("villain", "check")
            else:
                spot.actions[-2:] = []
        elif fraction:
            spot.actions[-1] = coach.SpotAction("villain", "bet", max(100, int(case.pot * fraction)))
        yield case, spot, style, wager, prefix, 9600 + i, (-1 if i % 2 else 1)


def manifest():
    paths = [path for section in ("coach", "simulation", "solver", "research/holdem")
             for path in (REPO / "backend" / section).rglob("*.py")]
    paths += [REPO / name for name in ("PHASE_5D_PROTOCOL.md", "backend/poker_analyzer.py")]
    return {"sources": {path.relative_to(REPO).as_posix(): sha256(path.read_bytes()).hexdigest()
                        for path in sorted(paths)},
            "schedule": [[asdict(case), asdict(spot), *factors] for case, spot, *factors in schedule()]}


def probability(weights):
    assert np.isfinite(weights).all() and np.min(weights) >= 0 and weights.sum() > 0
    return weights / weights.sum()


def reliability(prediction, truth, weights):
    cells = []
    for lower, upper in zip(BINS[:-1], BINS[1:], strict=True):
        inside = (prediction >= lower) & (prediction < upper)
        if inside.any():
            cells.append([lower, float(weights[inside].sum()),
                          float((prediction * weights)[inside].sum()),
                          float((truth * weights)[inside].sum())])
    return cells


def range_metrics(guess, exact, tiers, outcomes):
    error = guess - exact
    return {"tv": float(abs(error).sum() / 2), "combo_mae": float(abs(error).mean()),
            "missing_mass": float(exact[guess == 0].sum()),
            "effective": [float(1 / (weights @ weights)) for weights in (guess, exact)],
            "tier_mass": [np.bincount(tiers, weights=weights, minlength=3).tolist() for weights in (guess, exact)],
            "showdown_mass": [np.bincount(outcomes + 1, weights=weights, minlength=3).tolist()
                              for weights in (guess, exact)] if outcomes is not None else None,
            "brier": float(1 + guess @ guess - 2 * guess @ exact),
            "log_loss": float(-exact @ np.log(guess.clip(EPS))),
            "excess_log_loss": float(exact @ (np.log(exact.clip(EPS)) - np.log(guess.clip(EPS)))),
            "reliability": reliability(guess, exact, np.ones(len(guess)) / len(guess))}


def price(state, actor):
    own, offered = state.commit[actor], state.commit[1 - actor]
    cost = min(offered - own, state.stack[actor])
    return cost, sum(state.base) + 2 * own, offered - own - cost


def continues(tiers, style, ratio, gradient, closing):
    base = np.array((.34, .69, .94) if not style.tight else (.20, .56, .91))[tiers]
    odds = base / (1 - base)
    # Gradient +1 is price-sensitive, -1 is relatively sticky above half pot.
    slope = .95 if gradient == 1 else .13
    odds *= ((ratio + .25) / .75) ** (-slope)
    if closing:
        odds *= .64 if gradient == 1 else 1.22
    return odds / (1 + odds)


def open_probability(tiers, style):
    return np.array((.34, .55, .79) if style.aggressive else (.07, .19, .48))[tiers]


def size_class(ratio, closing):
    if closing:
        return "closing"
    if ratio < .4:
        return "quarter"
    if ratio < .75:
        return "half"
    return "pot" if ratio <= 1.1 else "overbet"


def opening_size(tiers, category):
    choices = {"quarter": (.37, .29, .12), "half": (.33, .32, .19),
               "pot": (.17, .21, .26), "overbet": (.10, .12, .23), "closing": (.03, .06, .20)}
    return np.array(choices[category])[tiers]


def raise_mass(continuation, tiers, style, ratio):
    rates = (.12, .17, .43) if style.aggressive else (.02, .05, .18)
    return continuation * np.array(rates)[tiers] / (1 + .30 * ratio)


def reference_replies(node, tiers, style, gradient):
    state = node.state
    actor, other = node.player, 1 - node.player
    cost, matched_pot, _ = price(state, actor)
    result = np.zeros((len(node.actions), len(tiers)))
    kinds = [kind for kind, _ in node.actions]
    if not cost:
        if len(kinds) == 1:
            result[0] = 1
            return result
        betting = open_probability(tiers, style)
        raw = np.stack([opening_size(tiers, size_class(target / matched_pot, kind == "all_in"))
                        for kind, target in node.actions if kind != "check"])
        result[0] = 1 - betting
        result[1:] = betting * raw / raw.sum(axis=0)
    else:
        closing = state.stack[other] == 0 or state.stack[actor] <= cost
        continuation = continues(tiers, style, cost / matched_pot, gradient, closing)
        indexes = [i for i, kind in enumerate(kinds) if kind in ("raise", "all_in")]
        aggression = 0.
        if indexes:
            aggression = raise_mass(continuation, tiers, style, cost / matched_pot)
            raw = np.array([2 if kinds[i] == "all_in" and style.aggressive else 1 for i in indexes])
            result[indexes] = raw[:, None] / raw.sum() * aggression
        result[kinds.index("fold")] = 1 - continuation
        result[kinds.index("call")] = continuation - aggression
    shadow.check_mix(result)
    return result


def reference_observation(step, tiers, style, gradient):
    state, player = step.before, step.player
    if step.kind == "check":
        return 1 - open_probability(tiers, style)
    if step.kind == "call":
        cost, pot, _ = price(state, player)
        continuation = continues(tiers, style, cost / pot, gradient, False)
        return continuation - raise_mass(continuation, tiers, style, cost / pot)
    assert step.kind in ("bet", "all_in") and state.highest == 0
    return open_probability(tiers, style) * opening_size(
        tiers, size_class(step.target / state.pot, step.kind == "all_in"))


class Capture:
    """Observe the incumbent chart and actual legacy public likelihood updates."""

    def __init__(self):
        self.updates = []

    def run(self, spot, prefix, profile, trace_dir):
        chart, step = SolverBot._preflop_policy, SolverBot._apply_strategy
        capture = self

        def chart_probe(bot, depth, villain, locks):
            policy = chart(bot, depth, villain, locks)
            capture.tree = bot.charts.trees[depth]
            capture.chart = policy
            return policy

        def step_probe(weights, solve, node, choice):
            after = step(weights, solve, node, choice)
            actor = solve.tree.nodes[node].player
            capture.updates.append((solve.combos[actor], solve.average[node][choice].copy(), after))
            return after

        with patch.object(SolverBot, "_preflop_policy", chart_probe), \
                patch.object(SolverBot, "_apply_strategy", staticmethod(step_probe)):
            return phase_5b.run_coach(spot, prefix, profile, None, False, True, trace_dir)

    def likelihoods(self, replay, bb):
        idx = self.tree.root
        postflop = iter(self.updates)
        for step in replay.steps:
            if step.street == "preflop":
                choice = map_action(self.tree, idx, step.kind, step.target, CHART_BB / bb)
                yield np.arange(len(COMBOS)), self.chart(idx)[choice], None
                idx = self.tree.nodes[idx].children[choice]
            else:
                yield next(postflop)
        assert next(postflop, None) is None


def audit_range(model, capture, case, style, gradient):
    ds = model.decision
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    pairs = COMBOS
    reach, truth = np.ones(len(pairs)), np.ones(len(pairs))
    history = iter(phase_4p.observations(replay, villain, case.seat == "button"))
    steps = iter(zip(replay.steps, capture.likelihoods(replay, ds.big_blind), strict=True))
    upcoming = next(steps, None)
    stages, likelihoods = {}, []
    exact = ExactRiverEV(tuple(ds.hole_cards), tuple(ds.board_cards), lambda *_: 1.)
    river = {combo_index(h.combo): h for h in exact.holdings}
    assert set(river) == set(model.ids)
    for street in STREETS:
        board = ds.board_cards[:BOARD_LENGTH[street]]
        blocked = set(board) | set(ds.hole_cards)
        ids = np.array([i for i, pair in enumerate(pairs) if blocked.isdisjoint(pair)])
        assert len(ids) == {0: 1225, 3: 1081, 4: 1035, 5: 990}[len(board)]
        if street == "river":
            tiers = np.array([strength(river[i].rank) for i in ids])
            outcomes = np.array([river[i].result for i in ids])
        else:
            tiers = (np.array([strength(RANKER.score(list(pairs[i]), list(board))) for i in ids])
                     if board else (phase_4p.GROUPS[ids] <= 1).astype(int))
            outcomes = None
        stages[street + "_entry"] = range_metrics(probability(reach[ids]), probability(truth[ids]), tiers, outcomes)
        while upcoming and upcoming[0].street == street:
            step, (columns, likelihood, actual) = upcoming
            upcoming = next(steps, None)
            if step.player != villain:
                continue
            if street == "preflop":
                site, action = next(history)
                j = phase_4p.ACTIONS.index(action)
                oracle = np.array([phase_4p.reference_action_law(pairs[i], site, case.depth, style)[j] for i in ids])
            else:
                oracle = reference_observation(step, tiers, style, gradient)
            q = probability(truth[ids])
            row = np.zeros(len(pairs))
            row[columns] = likelihood
            actual_row = row[ids]
            error = actual_row - oracle
            likelihoods.append({"street": street, "action": step.kind,
                                "estimated": float(actual_row @ q), "reference": float(oracle @ q),
                                "mae": float(abs(error) @ q),
                                "brier": float((error ** 2 + oracle * (1 - oracle)) @ q),
                                "log_loss": float(-(oracle * np.log(actual_row.clip(EPS)) +
                                                   (1 - oracle) * np.log((1 - actual_row).clip(EPS))) @ q),
                                "column_mass_removed": float(probability(reach[ids])[~np.isin(ids, columns)].sum()),
                                "reference_off_columns": float(q[~np.isin(ids, columns)].sum())})
            truth[ids] *= oracle
            reach = reach * row if actual is None else actual
        stages[street] = range_metrics(probability(reach[ids]), probability(truth[ids]), tiers, outcomes)
    assert upcoming is None and next(history, None) is None
    np.testing.assert_array_equal(ids, model.ids)
    np.testing.assert_array_equal(outcomes, model.outcomes)
    np.testing.assert_allclose(probability(reach[ids]), model.posterior, rtol=0, atol=1e-14)
    q = probability(truth[ids])
    stages["projected"] = range_metrics(model.projected, q, tiers, outcomes)
    return q, tiers, stages, likelihoods


def reply_class(node, kind, cost):
    if kind == "raise" and node.state.depth >= 2:
        return "reraise"
    if kind == "call" and cost == node.state.stack[node.player]:
        return "closing_call"
    return kind


def reply_scores(tree, root, reference, estimated, hero_tail, incoming):
    rows = []

    def walk(index, weights, root_action):
        node = tree.nodes[index]
        if node.kind != "decision":
            return
        if index in reference:
            reach = float(weights.sum())
            if reach <= EPS:
                return
            q = weights / reach
            p, r = estimated[index], reference[index]
            cost, pot, refund = price(node.state, node.player)
            kinds = [reply_class(node, kind, cost) for kind, _ in node.actions]
            closing = bool(cost and min(node.state.stack) == 0 or cost == node.state.stack[node.player])
            group = size_class(cost / pot, closing) if cost else "unopened"
            actions = {}
            pairs = []
            for kind in dict.fromkeys(kinds):
                chosen = np.array([name == kind for name in kinds])
                prediction, truth = p[chosen].sum(axis=0), r[chosen].sum(axis=0)
                actions[kind] = [float(prediction @ q), float(truth @ q), float(abs(prediction - truth) @ q)]
                pairs.extend(reliability(prediction, truth, q))
            rows.append({"index": index, "root": root_action, "size": group, "ratio": cost / pot,
                         "refund": refund, "reach": reach, "actions": actions, "reliability": pairs,
                         "brier": float((1 + (p*p).sum(axis=0) - 2*(p*r).sum(axis=0)) @ q),
                         "excess_brier": float(((p-r)**2).sum(axis=0) @ q),
                         "log_loss": float(-(r*np.log(p.clip(EPS))).sum(axis=0) @ q)})
            policy = r
        else:
            policy = hero_tail[index]
        for child, p in zip(node.children, policy, strict=True):
            walk(child, weights * p, root_action)

    for child, action in zip(root.children, root.actions, strict=True):
        walk(child, incoming, shadow.key(action))
    return rows


def four_arms(model, trace, exact, reference):
    root, ds = model.root, model.decision
    cash = ledger.root_ledger(ds, root.player)
    keys = tuple(map(shadow.key, model.menu))
    estimate = ledger.evaluate_tree(model, root, cash, model.outcomes, model.replies, model.hero_tail) / ds.big_blind
    truth = ledger.evaluate_tree(model, root, cash, model.outcomes, reference, model.hero_tail) / ds.big_blind
    cells = dict(zip("ABCD", (estimate @ model.posterior, estimate @ exact,
                             truth @ model.posterior, truth @ exact), strict=True))
    cfr = np.array([trace["cfr_ev_bb"][k] for k in keys])
    projected = estimate @ model.projected
    np.testing.assert_allclose(projected, [trace["projected_ev_bb"][k] for k in keys], rtol=0, atol=1e-10)
    np.testing.assert_allclose(cells["A"], [trace["bounded_ev_bb"][k] for k in keys], rtol=0, atol=1e-10)
    cfr_gap = float(abs(projected - cfr).max())
    assert cfr_gap <= 1e-4, cfr_gap
    d = cells["D"]
    pairs = [(i, j) for i, j in combinations(range(len(d)), 2) if abs(d[i] - d[j]) > MATERIAL]
    passive = [i for i, (kind, _) in enumerate(root.actions) if kind in ("check", "call", "fold")]
    arms = {}
    for arm, values in cells.items():
        chosen = max(range(len(keys)), key=lambda i: (values[i], keys[i]))
        arms[arm] = {"values": dict(zip(keys, values.tolist(), strict=True)), "action": keys[chosen],
                     "regret": float(d.max() - d[chosen]), "mae": float(abs(values - d).mean()),
                     "rank_ok": sum(bool((values[i] - values[j]) * np.sign(d[i] - d[j]) > MATERIAL) for i, j in pairs),
                     "rank_n": len(pairs), "false_advantages": sum(
                         bool(values[i] - max(values[passive]) > MATERIAL and d[i] - max(d[passive]) < -MATERIAL)
                         for i in range(len(keys)) if i not in passive)}
    reference_root = shadow.summarize_replies(model, reference, exact)
    estimated_root = shadow.summarize_replies(model, model.replies, exact)
    fold_checks = []
    for i, child in enumerate(root.children):
        if child not in reference or "fold" not in model.nodes[child].labels:
            continue
        fold_bb = root.state.pot / ds.big_blind
        entry = {"action": keys[i]}
        for label, p, values in (("estimated", estimated_root, cells["B"]), ("reference", reference_root, d)):
            fold = p[child]["actions"]["fold"]
            target = max(values[passive])
            nonfold = (values[i] - fold * fold_bb) / (1 - fold) if fold < 1 - EPS else None
            crossing = (target - nonfold) / (fold_bb - nonfold) if nonfold is not None and fold_bb > nonfold else None
            entry[label] = {"fold": fold, "margin_bb": float(values[i] - target),
                            "nonfold_bb": float(nonfold) if nonfold is not None else None,
                            "threshold": float(crossing) if crossing is not None and 0 <= crossing <= 1 else None}
        fold_checks.append(entry)
    return {"arms": arms, "interaction": (d - cells["B"] - cells["C"] + cells["A"]).tolist(),
            "cfr_gap": cfr_gap, "projection_gap": float(abs(projected - cells["A"]).max()),
            "seeded": keys[model.seeded], "seeded_regret": float(d.max() - d[model.seeded]),
            "modal": keys[int(np.argmax(model.mix))], "modal_regret": float(d.max() - d[np.argmax(model.mix)]),
            "fold_checks": fold_checks}


def expanded_probe(model, exact, tiers, style, gradient, profile):
    ds, hero = model.decision, model.root.player
    # Use common fixed reaches and one evaluated Hero holding for every root action.
    bot = SolverBot(seed=917)
    bot.postflop_menu = PROBE_MENU
    ranges = [np.zeros(len(COMBOS)), np.zeros(len(COMBOS))]
    hero_combo = combo_index(ds.hole_cards)
    ranges[hero][~card_mask(ds.board_cards)] = 1.
    ranges[1 - hero][model.ids] = exact
    solve = bot._solve(model.root.state, tuple(ds.board_cards), ranges, hero_combo, hero,
                       profile.snapshot if profile is not None else None,
                       working_ids=tuple(np.flatnonzero(r) for r in ranges))
    tree = solve.tree
    estimates, reference, pooled, hero_tail = {}, {}, {}, {}
    assumptions = ResponseAssumptions.from_counts(*model.counts)
    live, incumbent_tiers = hand_tiers(tuple(ds.board_cards))
    incumbent_tiers = incumbent_tiers[np.searchsorted(live, model.ids)]
    for node in tree.nodes:
        if node.kind != "decision" or node.index == tree.root:
            continue
        if node.player == hero:
            hero_tail[node.index] = solve.average[node.index][:, np.searchsorted(solve.combos[hero], hero_combo)]
        else:
            reference[node.index] = reference_replies(node, tiers, style, gradient)
            estimates[node.index] = solve.average[node.index]
            if "fold" in node.labels:
                pooled[node.index] = forecast(node, incumbent_tiers, assumptions)
            else:
                pooled[node.index] = estimates[node.index]
    root = tree.nodes[tree.root]
    return {"fixed_cfr": reply_scores(tree, root, reference, estimates, hero_tail, exact),
            "pooled_count": [row for row in reply_scores(tree, root, reference, pooled, hero_tail, exact)
                             if row["size"] != "unopened"]}


def audit_projection(model, profile):
    ds = model.decision
    replay = replay_hand(ds)
    hero_combo = combo_index(ds.hole_cards)
    beliefs = ReplayBeliefs(replay.current.to_act, ds.hole_cards)
    beliefs.replay_postflop(replay, ds.board_cards, profile.snapshot if profile is not None else None)
    before = (beliefs.opponent.tobytes(), *(item.weights.tobytes() for item in beliefs.public_reaches))
    omitted = [beliefs.project(hero_combo, CFRWorkingSet(cap)).omitted_opponent_mass for cap in (64, 384, 896)]
    after = (beliefs.opponent.tobytes(), *(item.weights.tobytes() for item in beliefs.public_reaches))
    assert before == after and not beliefs.opponent.flags.writeable
    assert set(np.flatnonzero(beliefs.opponent)) <= set(model.ids)
    assert omitted == sorted(omitted, reverse=True)
    return omitted


def holding_digest(model, q, reference):
    def digest(array):
        return sha256(array.tobytes()).hexdigest()

    return {"estimated": digest(model.posterior), "projected": digest(model.projected), "reference": digest(q),
            "cfr_replies": {i: digest(p) for i, p in model.replies.items()},
            "reference_replies": {i: digest(p) for i, p in reference.items()}}


def run_case(case, spot, name, wager, prefix, stream, gradient, trace_dir, reverse):
    style = STYLES[name]
    profile = train(name, stream, (prefix,))[prefix] if prefix else None
    paired = case.index % 16 == 0
    _EQUITY_CACHE.clear()
    if paired and not reverse:
        baseline = phase_5b.run_coach(spot, prefix, profile, None, False, False, trace_dir)[0]
        _EQUITY_CACHE.clear()
    capture = Capture()
    advised, trace, model, coach_seconds = capture.run(spot, prefix, profile, trace_dir)
    assert advised["response"]["explanation"]["source"] == "postflop_solve", advised["response"]
    assert trace and trace["status"] == "complete", trace
    if paired and reverse:
        _EQUITY_CACHE.clear()
        baseline = phase_5b.run_coach(spot, prefix, profile, None, False, False, trace_dir)[0]
    if paired:
        assert baseline == advised
    started = perf_counter()
    q, tiers, ranges, observed = audit_range(model, capture, case, style, gradient)
    reference = {i: reference_replies(model.nodes[i], tiers, style, gradient) for i in model.replies}
    decision = four_arms(model, trace, q, reference)
    replies = reply_scores(model, model.root, reference, model.replies, model.hero_tail, q)
    expanded = expanded_probe(model, q, tiers, style, gradient, profile) if wager == "checked" else {}
    projection = audit_projection(model, profile) if paired else None
    return {"index": case.index, "style": name, "wager": wager, "prefix": prefix, "stream": stream,
            "gradient": gradient, "depth": case.depth, "seat": case.seat, "path": case.path,
            "native_counts": model.counts, "ranges": ranges, "observed": observed,
            "replies": replies, "expanded": expanded, "decision": decision, "advice": advised,
            "inputs": holding_digest(model, q, reference), "projection_audit": projection, "paired": paired,
            "coach_seconds": coach_seconds, "shadow_seconds": trace["shadow_seconds"],
            "offline_seconds": perf_counter() - started}


def canonical(row):
    return {k: v for k, v in row.items() if not k.endswith("_seconds")}


def run_holdout(output, expected, shard):
    assert expected == json.loads(json.dumps(manifest()))
    hash_seed = os.environ.get("PYTHONHASHSEED")
    assert hash_seed in ("13", "31")
    number, total = shard
    assert 0 <= number < total
    rows = [row for row in schedule() if row[0].index % total == number]
    if hash_seed == "31":
        rows.reverse()
    started = perf_counter()
    evidence = []
    with output.with_suffix(".jsonl").open("x", encoding="utf-8") as journal:
        for row in rows:
            record = run_case(*row, output.parent / f"traces-{output.stem}", hash_seed == "31")
            evidence.append(record)
            print(record["index"], record["wager"], "complete", flush=True)
            journal.write(json.dumps(record, allow_nan=False) + "\n")
            journal.flush()
    return {"rows": sorted(evidence, key=lambda r: r["index"]),
            "peak_mib": peak_resident_bytes() / 2 ** 20, "elapsed_seconds": perf_counter() - started}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "holdout"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--shard", type=int, nargs=2, default=(0, 1))
    args = parser.parse_args()
    result = manifest() if args.mode == "freeze" else run_holdout(
        args.output, json.loads(args.manifest.read_text(encoding="utf-8")), args.shard)
    phase_5b.write(args.output, result)


if __name__ == "__main__":
    main()

