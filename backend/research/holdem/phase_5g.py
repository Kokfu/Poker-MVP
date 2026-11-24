"""Offline coverage experiment using the frozen Phase 5F reply selector."""
from argparse import ArgumentParser
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
import json
import os
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter

import numpy as np

from research.holdem import phase_5e as prior, phase_5f as frozen
from research.holdem.opponent_profile_v2 import extract, forecast
from research.holdem.profile_v2_hybrid import EvidenceProfile, hybrid_forecast, wager_key
from research.holdem.reply_forecast import reply_geometry

BUDGETS = (30, 100, 300, 500, 1000, 1500)
PRICES = (125, 250, 500, 625, 1250)
DEVELOPMENT = (910100, 911100, 912100, 1, 3)
HOLDOUT = (916100, 917100, 918100, 6, 12)
CANDIDATES = tuple(f"H{n}" for n in BUDGETS)
ARMS = ("A", "B", "C", "D", "E")


def source_manifest():
    paths = ("PHASE_5G_PROTOCOL.md", "backend/research/holdem/phase_5g.py",
             "backend/research/holdem/phase_5g_summary.py",
             "backend/research/holdem/phase_5g_audit.py",
             "backend/research/holdem/phase_5g_observer.py",
             "backend/simulation/engine.py", "backend/test_research_holdem_phase_5g.py")
    return {**frozen.manifest(), **{
        name: sha256((prior.ROOT / name).read_bytes()).hexdigest() for name in paths}}


def law(family, member, price):
    if price in prior.PRICES[family]:
        return frozen.truth_law(family, member, prior.PRICES[family].index(price), False)
    fold = (.36, .44)[member]
    return {"fold": fold, "call": 1 - fold, "raise": 0.}


def replay(deal, price, response, *, bounded_overbet=False):
    """Replay Phase 5F geometry, with an optional short-raise 1.25-pot stratum."""
    actions = [("hero", "raise", 250), ("villain", "call")]
    actions += [("villain", "check"), ("hero", "check")] * 2
    actions.append(("villain", "check"))
    actions.append(("hero", "all_in") if price == 1250 else ("hero", "bet", price))
    actions.append(("villain", response, 2 * price) if response == "raise" else ("villain", response))
    if response == "raise":
        actions.append(("hero", "fold"))
    spot = prior.coach.Spot(deal[:2], deal[4:], hero_stack=1500,
                           villain_stack=1450 if bounded_overbet else 2500,
                           villain_cards=deal[2:4],
                           actions=[prior.coach.SpotAction(*action) for action in actions])
    status, payload, _ = prior.coach._replay(spot)
    assert status == "hand_complete" and not payload["result"]["illegal_actions"]
    return payload["result"]["history"]


def train(family, member, cluster, original_seed, additional_seed, limit):
    """Yield the live profile at each prefix; the consumer scores before the next update."""
    identity = f"{family}:{cluster}:{member}"
    profile = EvidenceProfile(identity)
    old = prior.OpponentModel("b")
    original = Random(original_seed)
    additional = Random(additional_seed)
    rare = cluster % 2
    rare_count = (150, 5, 0)[cluster // 2]
    counts = tuple(rare_count if context == rare else 300 - rare_count for context in range(2))
    allocations = Counter()
    hands = 0
    elapsed = 0.

    def record(stream, index, price, deal, draw, *, bounded_overbet=False):
        nonlocal hands, elapsed
        started = perf_counter()
        response = prior.sample(law(family, member, price), draw)
        hand = replay(deal, price, response, bounded_overbet=bounded_overbet)
        source = f"{identity}:{stream}:{index}"
        assert profile.update(source, hand, "b")
        if stream == "original":
            old.update(hand)
        allocations[stream, price] += 1
        hands += 1
        elapsed += perf_counter() - started

    # Build the same original 300-hand exposure schedule, in its original order.
    # Smaller prefix forecasts use the frozen 300-hand A comparator, assembled below.
    for i in range(max(counts)):
        deal, draw = original.sample(prior.FULL_DECK, 9), original.random()
        for context, count in enumerate(counts):
            if i < count:
                price = prior.PRICES[family][context]
                record("original", f"{i}:{context}", price, deal, draw)
                if hands in BUDGETS:
                    yield hands, profile, old.snapshot() if hands == 300 else None, allocations.copy(), elapsed
                if hands == limit:
                    return
    seen_deals = set()
    for i in range(limit - 300):
        price = PRICES[i % len(PRICES)]
        deal = additional.sample(prior.FULL_DECK, 9)
        fingerprint = (frozenset(deal[:2]), frozenset(deal[2:4]), tuple(deal[4:]))
        assert fingerprint not in seen_deals
        seen_deals.add(fingerprint)
        bounded = price == 625 and i % (2 * len(PRICES)) >= len(PRICES)
        record("additional_bounded" if bounded else "additional", i, price, deal,
               additional.random(), bounded_overbet=bounded)
        if hands in BUDGETS:
            yield hands, profile, None, allocations.copy(), elapsed


def checked_tree(closing):
    state = prior.StreetState("river", 0, (0, 1250 if closing else 0),
                              (1250, 0 if closing else 2250), (250, 250),
                              1250 if closing else 100, (False, True), int(closing))
    tree = prior.StreetTree(state, prior.MENU)
    root = tree.nodes[tree.root]
    tail = {node.index: [float(kind in ("fold", "check")) for kind, _ in node.actions]
            for node in tree.nodes if node.kind == "decision" and node.player == root.player}
    specs = {}
    roots = {}
    for index in tail:
        parent = tree.nodes[index]
        for label, (previous, _), child in zip(parent.labels, parent.actions, parent.children, strict=True):
            node = tree.nodes[child]
            if node.kind == "decision":
                geo = reply_geometry(node.state)
                specs[child] = (prior.tree_context(node, previous), geo.cost, geo.pot_before_wager)
                if index == root.index:
                    roots[label] = child
    return state, tree, root, tail, specs, roots


def panel(profile, specs, *, pure):
    result = {}
    for key, (context, price, pot) in specs.items():
        mix, evidence = hybrid_forecast(profile, context, price, pot, lambda: None)
        if pure:
            result[key] = (mix, evidence, forecast(profile.v2, context, True))
        else:
            result[key] = (mix, evidence)
        assert (mix is None) == (evidence.coverage != "supported")
    return result


def reference(family, member, context, price):
    if context.previous in ("bet", "all_in"):
        result = law(family, member, price)
    else:
        fold = (.36, .44)[member]
        result = {"fold": fold, "call": 1 - fold, "raise": 0.}
    return {action: result.get(action, 0.) for action in context.legal}


def predictions(key, specs, panels, snapshot, family, member):
    context, price, _ = specs[key]
    base = prior.incumbent(snapshot, context)
    exact = reference(family, member, context, price)
    mixes = {"A": base, "B": panels[1500][key][2], "E": exact}
    evidence = {}
    for count, candidate in zip(BUDGETS, CANDIDATES, strict=True):
        mix, info = panels[count][key][:2]
        mixes[candidate] = base if mix is None else mix
        evidence[candidate] = info
    mixes.update(C=mixes["H300"], D=mixes["H1500"])
    assert all(tuple(mix) == context.legal and min(mix.values()) >= 0
               and abs(sum(mix.values()) - 1) < 1e-12 for mix in mixes.values())
    return mixes, evidence


def reply_record(spec, mixes, evidence, draw, group):
    context, price, pot = spec
    realized = prior.sample({"raise": 0., **mixes["E"]}, draw)
    return {"context": asdict(context), "price": price, "pot": pot, "group": group,
            "observed": realized, "probabilities": mixes,
            "coverage": {arm: info._asdict() for arm, info in evidence.items()},
            "scores": {arm: prior.scores(mix, mixes["E"], realized) for arm, mix in mixes.items()}}


def ev_case(tree_data, predictions_by_node, deal):
    state, tree, root, tail, _, roots = tree_data
    holdings = prior.ExactRiverEV(tuple(deal[:2]), tuple(deal[4:]), lambda *_: 1).holdings
    outcomes = np.array([item.result for item in holdings])
    assert len(outcomes) == 990
    cash = prior.ledger.Ledger(sum(state.base), state.commit, state.stack, 0, False)
    arm_names = (*ARMS, *(arm for arm in CANDIDATES if arm not in ("H300", "H1500")))
    replies = {}
    for arm in arm_names:
        replies[arm] = {}
        for index, (mixes, _) in predictions_by_node.items():
            p = mixes[arm]
            kinds = ["shove" if kind == "all_in" else kind for kind, _ in tree.nodes[index].actions]
            replies[arm][index] = [p[kind] / kinds.count(kind) for kind in kinds]

    def evaluate(response):
        return prior.ledger.evaluate_tree(tree, root, cash, outcomes, response, tail).mean(axis=1) / 100

    # Exact-equal models reuse the same ledger result. This also covers no-reply controls.
    evaluated = {}
    values = {}
    for arm, response in replies.items():
        key = tuple((index, tuple(reply)) for index, reply in response.items())
        if key not in evaluated:
            evaluated[key] = evaluate(response)
        values[arm] = evaluated[key]
    values.update(H300=values["C"], H1500=values["D"])
    truth = values["E"]
    passive = [i for i, (kind, _) in enumerate(root.actions) if kind in ("check", "fold", "call")]
    best_passive = max(truth[passive])
    pairs = [(i, j) for i, j in combinations(range(len(truth)), 2) if abs(truth[i] - truth[j]) > .01]
    no_fold = {index: [p / (1 - mix[0]) if i else 0. for i, p in enumerate(mix)]
               for index, mix in replies["E"].items() if tree.nodes[index].labels[0] == "fold"}
    without_fold = evaluate({**replies["E"], **no_fold})
    kinds = {}
    for i, (label, (kind, _)) in enumerate(zip(root.labels, root.actions, strict=True)):
        if kind == "call":
            kinds[label] = "profitable_call" if truth[i] > 0 else "unprofitable_call"
        if i not in passive and without_fold[i] < best_passive - .01:
            kinds[label] = "profitable_bluff" if truth[i] > best_passive + .01 else "unprofitable_bluff"
    bad_shove = "all_in" in root.labels and truth[root.labels.index("all_in")] < best_passive - .01
    answers = {}
    for arm, estimates in values.items():
        selected = max(range(len(estimates)), key=lambda i: (estimates[i], root.labels[i]))
        estimated_passive = max(estimates[passive])
        answers[arm] = {
            "values": dict(zip(root.labels, estimates.tolist(), strict=True)),
            "choice": root.labels[selected], "selected_type": kinds.get(root.labels[selected]),
            "regret": float(truth.max() - truth[selected]),
            "rank_ok": sum(int((estimates[i] - estimates[j]) * np.sign(truth[i] - truth[j]) > .01)
                           for i, j in pairs),
            "false_advantages": sum(int(estimates[i] > estimated_passive + .01
                                        and truth[i] < best_passive - .01)
                                    for i in range(len(truth)) if i not in passive),
            "harmful_shove": bool(bad_shove and root.labels[selected] == "all_in"),
            "mae": float(abs(truth - estimates).mean()),
        }
    for label, node_id in roots.items():
        _, evidence = predictions_by_node[node_id]
        for arm, info in evidence.items():
            if info.coverage != "supported":
                assert answers[arm]["values"][label] == answers["A"]["values"][label]
    return {"closing": not bool(roots), "hero": deal[:2], "board": deal[4:], "arms": answers,
            "rank_pairs": len(pairs), "action_types": kinds, "bad_shove": bool(bad_shove)}


def study(family, cluster, schedule, timings, *, verify=False):
    original, additional, evaluation, _, deals_per_member = schedule
    offset = 100 * family + cluster
    rng = Random(evaluation + offset)
    deals = [rng.sample(prior.FULL_DECK, 9) for _ in range(deals_per_member)]
    draws = [rng.random() for _ in deals]
    checked, closing = checked_tree(False), checked_tree(True)
    specs = dict(checked[4])
    scripted = {}
    members = []
    for member in range(2):
        for price in prior.PRICES[family]:
            history = replay(deals[0], price, "call")
            row = prior.target(history, family)
            assert row.collectible == price
            scripted[price] = (row.situation, price, row.matched_pot)
        queries = {**specs, **{("scripted", price): data for price, data in scripted.items()}}
        panels = {}
        audits = {}
        for n, profile, old, allocations, elapsed in train(
                family, member, cluster, original + offset, additional + offset, BUDGETS[-1]):
            started = perf_counter()
            panels[n] = panel(profile, queries, pure=n == BUDGETS[-1])
            if n == 300:
                snapshot = old
                if verify:
                    original_case, _ = frozen.ev_case(family, member, deals[0], False, profile, old,
                                                      draws[0], False, CounterLists())
            keys = {wager_key(*query) for query in queries.values()}
            audits[n] = {
                "allocations": {f"{stream}:{price}": count for (stream, price), count in allocations.items()},
                "all_wager_opportunities": sum(profile._opportunities.values()),
                "all_wager_responses": sum(profile._replies.values()),
                "unique_query_opportunities": sum(profile._opportunities[key] for key in keys),
                "unique_query_responses": sum(profile._replies[key] for key in keys),
                "unknown_turns": profile.v2.unknown,
            }
            timings[f"panel_{n}"].append(perf_counter() - started)
            timings[f"training_{n}"].append(elapsed)
            assert profile.v2.hands_observed == n and sum(allocations.values()) == n
        predictions_by_key = {key: predictions(key, queries, panels, snapshot, family, member)
                              for key in queries}
        cases = []
        reply_rows = []
        for j, (deal, draw) in enumerate(zip(deals, draws, strict=True)):
            is_closing = j % 3 == 2
            started = perf_counter()
            case = ev_case(closing if is_closing else checked,
                           {} if is_closing else {key: predictions_by_key[key] for key in specs}, deal)
            timings["exact"].append(perf_counter() - started)
            if verify and j == 0:
                for arm, old_arm in (("A", "A"), ("C", "C"), ("E", "D")):
                    assert case["arms"][arm]["choice"] == original_case["arms"][old_arm]["choice"]
                    assert case["arms"][arm]["values"] == original_case["arms"][old_arm]["values"]
            case["wagers"] = {label: reply_record(specs[key], *predictions_by_key[key], draw, "menu")
                              for label, key in checked[5].items()} if not is_closing else {}
            cases.append(case)
            reply_rows.append([reply_record(queries[key], *predictions_by_key[key], draw, "scripted")
                               for key in (("scripted", price) for price in scripted)])
        members.append({"member": member, "training": audits, "cases": cases, "scripted": reply_rows})
    return {"family": prior.FAMILIES[family], "cluster": cluster, "rare_count": (150, 5, 0)[cluster // 2],
            "seeds": {"original": original + offset, "additional": additional + offset,
                      "evaluation": evaluation + offset}, "members": members}


class CounterLists(dict):
    def __missing__(self, key):
        self[key] = []
        return self[key]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("development", "freeze", "holdout"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    lock = args.output / "frozen.json"
    if args.stage == "freeze":
        if lock.exists():
            raise FileExistsError(lock)
        prior.write(lock, source_manifest())
        return
    holdout = args.stage == "holdout"
    suffix = "31" if args.reverse else "13"
    if holdout:
        if os.environ.get("PYTHONHASHSEED") != suffix:
            raise ValueError("start Python with the designated hash seed")
        if json.loads(lock.read_text(encoding="utf-8")) != source_manifest():
            raise RuntimeError("study sources changed after freeze")
    schedule = HOLDOUT if holdout else DEVELOPMENT
    jobs = [(family, cluster) for family in prior.EV_FAMILIES for cluster in range(schedule[3])]
    timings = CounterLists()
    results = []
    for family, cluster in reversed(jobs) if args.reverse else jobs:
        results.append(study(family, cluster, schedule, timings, verify=not holdout))
        print(prior.FAMILIES[family], cluster, flush=True)
    label = f"holdout-{suffix}" if holdout else "development"
    prior.write(args.output / f"{label}.json", sorted(results, key=lambda row: (row["family"], row["cluster"])))
    prior.write(args.output / f"{label}-timing.json",
                {**{key: prior.latency(values) for key, values in timings.items()},
                 "peak_mib": prior.peak_resident_bytes() / 2**20})


if __name__ == "__main__":
    main()
