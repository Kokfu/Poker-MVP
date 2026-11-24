"""Frozen, offline Phase 5E profile and finite river experiment."""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from math import log
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

import numpy as np

from coach import service as coach
from poker_analyzer import FULL_DECK
from research.holdem import action_ev_reference as ledger
from research.holdem.opponent_profile_v2 import ProfileV2, extract, forecast, predict, situation
from research.holdem.phase_4k import RANKER, peak_resident_bytes, strength
from research.holdem.reply_forecast import river_counts
from research.holdem.river_ev import ExactRiverEV
from simulation.opponent_model import OpponentModel
from solver.tree import SizeMenu, StreetState, StreetTree

ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ("small", "large", "closing", "preflop", "river_aggression", "position")
PRICES = ((125, 250), (500, 625), (125, 1250), (250, 500), (125, 500), (250, 250))
PREFIXES = (10, 30, 100, 300, 1000)
ARMS = ("A", "A*", "B", "C")
CLUSTERS = 4
HAND_SCORES = 32
MENU = SizeMenu(((.25, .5, 1., 1.25), (0., 1.)))
EV_FAMILIES = (0, 1, 2, 4)


def manifest():
    paths = [ROOT / "PHASE_5E_PROTOCOL.md", Path(__file__), Path(__file__).with_name("opponent_profile_v2.py"), Path(__file__).with_name("phase_5e_timing.py")]
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def law(family, member, context):
    high = member ^ context
    if family in (3, 4):
        fold, raised = .20, (.05, .55)[high]
    elif family == 2:
        fold, raised = (.22, .60)[high], 0.
    else:
        fold, raised = (.20, .65)[high], 0.
    return {"fold": fold, "raise": raised, "call": 1 - fold - raised}


def sample(law, draw):
    if draw < law["fold"]:
        return "fold"
    return "raise" if draw < law["fold"] + law["raise"] else "call"


def public_history(deal, family, context, reply):
    """Script a public wager and one reply; engine resolves the rest of the hand."""
    price = PRICES[family][context]
    button = not (family in (3, 5) and context)
    first, second = ("hero", "villain") if button else ("villain", "hero")
    street_checks = [(second, "check"), (first, "check")]
    if family == 3:
        actions = [("hero", "raise", price)] if not context else [
            ("villain", "raise", 250), ("hero", "raise", price)]
        actions += [("villain", reply, 2 * price) if reply == "raise" else ("villain", reply)]
        if reply == "call":
            actions += street_checks * 3
    else:
        actions = [(first, "raise", 250), (second, "call")] + street_checks * 2
        if button:
            actions.append(("villain", "check"))
        actions += [("hero", "all_in") if price == 1250 else ("hero", "bet", price),
                    ("villain", reply, 2 * price) if reply == "raise" else ("villain", reply)]
    if reply == "raise":
        actions.append(("hero", "fold"))
    spot = coach.Spot(deal[:2], deal[4:], hero_stack=1500, villain_stack=2500,
                      villain_cards=deal[2:4], hero_position="button" if button else "big_blind",
                      actions=[coach.SpotAction(*action) for action in actions])
    status, payload, _ = coach._replay(spot)
    if status != "hand_complete" or payload["result"]["illegal_actions"]:
        raise AssertionError("invalid synthetic hand")
    return payload["result"]["history"]


def target(history, family):
    street = "preflop" if family == 3 else "river"
    rows, unknown = extract(history, "b")
    assert unknown == 0
    return next(row for row in rows if row.situation.street == street and row.offered)


def incumbent(snapshot, context):
    if context.street == "river" and "fold" in context.legal:
        folds, calls, raises = river_counts(snapshot)
        aggression = {"raise", "shove"}.intersection(context.legal)
        counts = {"fold": folds, "call": calls}
        counts.update({action: raises / len(aggression) for action in aggression})
        return predict(context.legal, counts)
    raw = snapshot.statistics if context.street == "preflop" else snapshot.street_statistics[context.street]
    counts = {action: raw["all_in" if action == "shove" else action].occurrences
              for action in context.legal if ("all_in" if action == "shove" else action) in raw}
    return predict(context.legal, counts)


def scores(predicted, truth, observed):
    return {"brier": sum((p - (key == observed)) ** 2 for key, p in predicted.items()),
            "expected_brier": sum(p*p - 2*p*truth.get(key, 0) + truth.get(key, 0)
                                  for key, p in predicted.items()),
            "log_loss": -log(max(predicted[observed], 1e-12)),
            "expected_log_loss": -sum(truth.get(key, 0) * log(max(p, 1e-12))
                                      for key, p in predicted.items())}


def forecasts(profile, snapshot, context, reference):
    return {"A": incumbent(snapshot, context), "A*": forecast(profile, context, False),
            "B": forecast(profile, context, True),
            "C": {action: reference.get(action, 0.) for action in context.legal}}


def reply_study(family, member, holdout, profile, snapshot, prefix, timings):
    rows = []
    for context, deal, draw in holdout:
        truth = law(family, member, context)
        observed = sample(truth, draw)
        row = target(public_history(deal, family, context, observed), family)
        assert row.response == observed
        started = perf_counter()
        predictions = forecasts(profile, snapshot, row.situation, truth)
        timings.append(perf_counter() - started)
        for p in predictions.values():
            assert abs(sum(p.values()) - 1) < 1e-12 and min(p.values()) >= 0
        cell = profile.conditional.get(row.situation)
        rows.append({"prefix": prefix, "member": member, "context": context,
                     "opportunities": cell.opportunities if cell else 0, "response": observed,
                     "predictions": predictions,
                     "scores": {arm: scores(p, truth, observed) for arm, p in predictions.items()}})
    return rows


def tree_context(node, previous):
    state, actor = node.state, node.player
    own, their = state.commit[actor], state.commit[1 - actor]
    price = min(their - own, state.stack[actor])
    matched_pot = sum(state.base) + 2 * own
    effective = min(state.stack[actor], their - own + state.stack[1 - actor])
    return situation("river", "big_blind", previous, state.depth, price, matched_pot, effective, 100,
                     bool(price and (state.stack[1 - actor] == 0 or price == state.stack[actor])),
                     ["shove" if kind == "all_in" else kind for kind, _ in node.actions])


def ev_study(family, member, deal, closing, profile, snapshot):
    state = StreetState("river", 0, (0, 1250 if closing else 0),
                        (1250, 0 if closing else 2250), (250, 250),
                        1250 if closing else 100, (False, True), int(closing))
    tree = StreetTree(state, MENU)
    root = tree.nodes[tree.root]
    outcomes = ExactRiverEV(tuple(deal[:2]), tuple(deal[4:]), lambda *_: 1).holdings
    outcomes = np.array([item.result for item in outcomes])
    assert len(outcomes) == 990
    arm_matches = {arm: {} for arm in ARMS}
    tail = {}
    for node in tree.nodes:
        if node.kind != "decision":
            continue
        if node.player == root.player:
            tail[node.index] = [float(kind in ("fold", "check")) for kind, _ in node.actions]
    for parent in tree.nodes:
        if parent.player != root.player or parent.kind != "decision":
            continue
        for (previous, _), index in zip(parent.actions, parent.children, strict=True):
            node = tree.nodes[index]
            if node.kind != "decision":
                continue
            ctx = tree_context(node, previous)
            price = min(node.state.highest - node.state.commit[node.player], node.state.stack[node.player])
            reference = {"fold": .40, "call": .60} if price else {"check": 1.}
            if previous in ("bet", "all_in") and price in PRICES[family]:
                reference = law(family, member, PRICES[family].index(price))
            predictions = forecasts(profile, snapshot, ctx, reference)
            kinds = ["shove" if kind == "all_in" else kind for kind, _ in node.actions]
            for arm, p in predictions.items():
                assert abs(sum(p.values()) - 1) < 1e-12
                arm_matches[arm][index] = [p[kind] / kinds.count(kind) for kind in kinds]
    cash = ledger.Ledger(500, state.commit, state.stack, 0, False)
    def price_with(replies):
        return ledger.evaluate_tree(tree, root, cash, outcomes, replies, tail).mean(axis=1) / 100
    values = {arm: price_with(replies) for arm, replies in arm_matches.items()}
    truth = values["C"]
    passive = [i for i, (kind, _) in enumerate(root.actions) if kind in ("check", "fold", "call")]
    best_passive = max(truth[passive])
    pairs = [(i, j) for i, j in combinations(range(len(truth)), 2) if abs(truth[i] - truth[j]) > .01]
    no_fold = {index: [p / (1 - mix[0]) if i else 0. for i, p in enumerate(mix)]
               for index, mix in arm_matches["C"].items() if tree.nodes[index].labels[0] == "fold"}
    no_fold_values = price_with({**arm_matches["C"], **no_fold})
    available = {}
    for i, (kind, _) in enumerate(root.actions):
        if kind == "call":
            available[i] = "profitable_call" if truth[i] > 0 else "unprofitable_call"
        if i not in passive and no_fold_values[i] < best_passive - .01:
            available[i] = "profitable_bluff" if truth[i] > best_passive + .01 else "unprofitable_bluff"
    answers = {}
    for arm, estimates in values.items():
        selected = max(range(len(estimates)), key=lambda i: (estimates[i], root.labels[i]))
        answers[arm] = {"values": dict(zip(root.labels, estimates.tolist(), strict=True)),
                        "choice": root.labels[selected], "selected_type": available.get(selected),
                        "regret": float(truth.max() - truth[selected]),
                        "rank_ok": sum(int((estimates[i] - estimates[j]) * np.sign(truth[i] - truth[j]) > .01)
                                       for i, j in pairs),
                        "false_advantages": sum(int(estimates[i] > max(estimates[passive]) + .01
                                                    and truth[i] < best_passive - .01)
                                                for i in range(len(truth)) if i not in passive),
                        "mae": float(abs(truth - estimates).mean())}
    return {"closing": closing, "opportunities": dict(Counter(available.values())),
            "rank_pairs": len(pairs), "arms": answers}


def cluster_study(family, cluster, timings):
    train = Random(785100 + 100 * family + cluster)
    test = Random(786100 + 100 * family + cluster)
    holdout = [(context, deal, draw) for deal, draw in
               [(test.sample(FULL_DECK, 9), test.random()) for _ in range(HAND_SCORES)] for context in range(2)]
    ev_deals = [test.sample(FULL_DECK, 9) for _ in range(8)]
    v2 = [ProfileV2(f"{family}:{cluster}:{member}") for member in range(2)]
    old = [OpponentModel("b"), OpponentModel("b")]
    rows, ev = [], []
    for i in range(1, 501):
        deal, draw = train.sample(FULL_DECK, 9), train.random()
        for member in range(2):
            for context in range(2):
                reply = sample(law(family, member, context), draw)
                hand = public_history(deal, family, context, reply)
                started = perf_counter()
                v2[member].update(f"{i}:{context}", hand, "b")
                timings["aggregation"].append(perf_counter() - started)
                old[member].update(hand)
        if i * 2 in PREFIXES:
            for member in range(2):
                snapshot = old[member].snapshot()
                rows.extend(reply_study(family, member, holdout, v2[member], snapshot, i * 2, timings["forecast"]))
                if family in EV_FAMILIES and i * 2 == 300:
                    for j, deal in enumerate(ev_deals):
                        started = perf_counter()
                        ev.append(ev_study(family, member, deal, j % 2 == 1, v2[member], snapshot))
                        timings["exact"].append(perf_counter() - started)
    return {"family": FAMILIES[family], "cluster": cluster, "rows": rows, "ev": ev,
            "pooled_equal_1000": old[0].snapshot().as_dict() == old[1].snapshot().as_dict(),
            "cells": [len(profile.conditional) for profile in v2]}


def historical():
    rng = Random(659207)
    old = [OpponentModel("b"), OpponentModel("b")]
    profiles = [ProfileV2("historical:0"), ProfileV2("historical:1")]
    snapshots = {}
    contexts = {}
    for n in range(1, 501):
        deal = rng.sample(FULL_DECK, 9)
        tier = strength(RANKER.score(deal[2:4], deal[4:]))
        draw = rng.random()
        for member, profile in enumerate(profiles):
            for context in range(2):
                folded = draw < (.68, .28)[member ^ context] + (.13, 0., -.22)[tier]
                hand = public_history(deal, 2, context, "fold" if folded else "call")
                old[member].update(hand)
                profile.update(f"{n}:{context}", hand, "b")
                contexts[context] = target(hand, 2).situation
        if 2*n in PREFIXES:
            snapshots[2*n] = {"pooled_equal": old[0].snapshot().as_dict() == old[1].snapshot().as_dict(),
                              "cells": [[profile.conditional[contexts[c]].evidence() for c in range(2)]
                                        for profile in profiles]}
    return snapshots


def interval(differences):
    strata = {}
    for family, value in differences:
        strata.setdefault(family, []).append(value)
    rng = Random(787100)
    replicates = [mean(v for values in strata.values() for v in rng.choices(values, k=len(values)))
                  for _ in range(2000)]
    return {"delta": mean(v for _, v in differences), "ci95": np.quantile(replicates, [.025, .975]).tolist()}


def latency(samples):
    return {"first": samples[0], "median": float(np.median(samples)),
            "p95": sorted(samples)[int(np.ceil(.95 * len(samples))) - 1], "max": max(samples)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "holdout", "diagnostic"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    frozen = args.directory / "frozen.json"
    if args.stage == "freeze":
        if frozen.exists():
            raise FileExistsError(frozen)
        write(frozen, manifest())
        return
    assert manifest() == json.loads(frozen.read_text(encoding="utf-8"))
    if args.stage == "diagnostic":
        write(args.directory / "historical.json", historical())
        return
    jobs = [(family, cluster) for family in range(len(FAMILIES)) for cluster in range(CLUSTERS)]
    timings = {key: [] for key in ("aggregation", "forecast", "exact")}
    result = []
    for family, cluster in reversed(jobs) if args.reverse else jobs:
        result.append(cluster_study(family, cluster, timings))
        print(FAMILIES[family], cluster, flush=True)
    suffix = "31" if args.reverse else "13"
    write(args.directory / f"holdout-{suffix}.json", sorted(result, key=lambda cell: (cell["family"], cell["cluster"])))
    write(args.directory / f"timing-{suffix}.json",
          {**{key: latency(values) for key, values in timings.items()},
           "peak_mib": peak_resident_bytes() / 2**20})


if __name__ == "__main__":
    main()
