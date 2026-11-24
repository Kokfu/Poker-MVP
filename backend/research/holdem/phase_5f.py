"""Phase 5F's frozen, offline four-arm study and Phase 5E reconstruction."""
from argparse import ArgumentParser
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter
import tracemalloc

import numpy as np

from research.holdem import phase_5e as prior
from research.holdem.opponent_profile_v2 import forecast
from research.holdem.profile_v2_hybrid import EvidenceProfile, hybrid_forecast
from research.holdem.reply_forecast import reply_geometry

ROOT = prior.ROOT
ARMS = ("A", "B", "C", "D")
DEVELOPMENT = (890100, 891100, 1, 4)
HOLDOUT = (892100, 893100, 6, 12)
ARCHIVE = (785100, 786100, 4, 8)


def manifest():
    paths = [ROOT / "PHASE_5F_PROTOCOL.md"]
    backend = ROOT / "backend"
    paths += [Path(__file__).with_name(name + ".py") for name in (
        "phase_5f", "phase_5f_summary", "phase_5f_observer", "phase_5e", "phase_5e_timing",
        "profile_v2_hybrid", "opponent_profile_v2", "action_ev_reference",
        "reply_forecast", "river_ev", "river_shadow", "phase_5d", "phase_4k")]
    paths += [backend / name for name in (
        "coach/service.py", "simulation/history.py", "simulation/opponent_model.py", "solver/tree.py")]
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}


def truth_law(family, member, context, archive):
    if archive:
        return prior.law(family, member, context)
    high = member ^ context
    fold, raised = {
        0: ((.18, .66)[high], 0.),
        1: ((.25, .70)[high], 0.),
        2: ((.24, .63)[high], 0.),
        4: (.23, (.08, .48)[high]),
    }[family]
    return {"fold": fold, "call": 1 - fold - raised, "raise": raised}


def prediction(profile, snapshot, context, price, pot, reference):
    a = prior.incumbent(snapshot, context)
    b = forecast(profile.v2, context, True)
    c, evidence = hybrid_forecast(profile, context, price, pot, lambda: a)
    d = {action: reference.get(action, 0.) for action in context.legal}
    forecasts = dict(zip(ARMS, (a, b, c, d), strict=True))
    assert all(tuple(p) == context.legal and min(p.values()) >= 0
               and abs(sum(p.values()) - 1) < 1e-12 for p in forecasts.values())
    if evidence.coverage == "supported":
        assert c == b
    else:
        assert c is a
    return forecasts, evidence


def reply_row(context, price, pot, predictions, evidence, response, group):
    return {"context": asdict(context), "price": price, "pot": pot, "group": group,
            "coverage": evidence.coverage, "opportunities": evidence.opportunities,
            "replies": evidence.replies, "response": response, "probabilities": predictions,
            "scores": {arm: prior.scores(p, predictions["D"], response) for arm, p in predictions.items()}}


def ev_case(family, member, deal, closing, profile, snapshot, draw, archive, timings):
    state = prior.StreetState("river", 0, (0, 1250 if closing else 0),
                              (1250, 0 if closing else 2250), (250, 250),
                              1250 if closing else 100, (False, True), int(closing))
    tree = prior.StreetTree(state, prior.MENU)
    root = tree.nodes[tree.root]
    holdings = prior.ExactRiverEV(tuple(deal[:2]), tuple(deal[4:]), lambda *_: 1).holdings
    outcomes = np.array([item.result for item in holdings])
    assert len(outcomes) == 990
    replies = {arm: {} for arm in ARMS}
    tail = {node.index: [float(kind in ("fold", "check")) for kind, _ in node.actions]
            for node in tree.nodes if node.kind == "decision" and node.player == root.player}
    details = {}
    calibration = []
    for parent in tree.nodes:
        if parent.index not in tail:
            continue
        for label, (previous, _), index in zip(parent.labels, parent.actions, parent.children, strict=True):
            node = tree.nodes[index]
            if node.kind != "decision":
                continue
            context = prior.tree_context(node, previous)
            geometry = reply_geometry(node.state)
            price, pot = geometry.cost, geometry.pot_before_wager
            matched = previous in ("bet", "all_in") and price in prior.PRICES[family]
            fold = .40 if archive else (.36, .44)[member]
            law = (truth_law(family, member, prior.PRICES[family].index(price), archive)
                   if matched else {"fold": fold, "call": 1 - fold, "raise": 0.})
            started = perf_counter()
            predictions, evidence = prediction(profile, snapshot, context, price, pot, law)
            timings["forecast_panel"].append(perf_counter() - started)
            kinds = ["shove" if kind == "all_in" else kind for kind, _ in node.actions]
            for arm, p in predictions.items():
                replies[arm][index] = [p[kind] / kinds.count(kind) for kind in kinds]
            if parent.index == root.index:
                row = reply_row(context, price, pot, predictions, evidence, prior.sample(law, draw),
                                "trained_menu" if matched else "unseen_menu")
                calibration.append(row)
                cell = profile.v2.conditional.get(context)
                details[label] = {**row, "legal_targets": node.labels,
                                  "v2_bucket": cell.evidence() if cell is not None else None,
                                  "source": "V2" if evidence.coverage == "supported" else "incumbent"}
    cash = prior.ledger.Ledger(sum(state.base), state.commit, state.stack, 0, False)

    def evaluate(responses):
        return prior.ledger.evaluate_tree(tree, root, cash, outcomes, responses, tail).mean(axis=1) / 100

    values = {arm: evaluate(responses) for arm, responses in replies.items()}
    truth = values["D"]
    passive = [i for i, (kind, _) in enumerate(root.actions) if kind in ("check", "fold", "call")]
    best_passive = max(truth[passive])
    pairs = [(i, j) for i, j in combinations(range(len(truth)), 2) if abs(truth[i] - truth[j]) > .01]
    no_fold = {index: [p / (1 - mix[0]) if i else 0. for i, p in enumerate(mix)]
               for index, mix in replies["D"].items() if tree.nodes[index].labels[0] == "fold"}
    without_fold = evaluate({**replies["D"], **no_fold})
    action_types = {}
    for i, (label, (kind, _)) in enumerate(zip(root.labels, root.actions, strict=True)):
        if kind == "call":
            action_types[label] = "profitable_call" if truth[i] > 0 else "unprofitable_call"
        if i not in passive and without_fold[i] < best_passive - .01:
            action_types[label] = "profitable_bluff" if truth[i] > best_passive + .01 else "unprofitable_bluff"
    bad_shove = bool("all_in" in root.labels and truth[root.labels.index("all_in")] < best_passive - .01)
    answers = {}
    for arm, estimates in values.items():
        selected = max(range(len(estimates)), key=lambda i: (estimates[i], root.labels[i]))
        best_estimated_passive = max(estimates[passive])
        answers[arm] = {
            "values": dict(zip(root.labels, estimates.tolist(), strict=True)),
            "choice": root.labels[selected], "selected_type": action_types.get(root.labels[selected]),
            "regret": float(truth.max() - truth[selected]),
            "rank_ok": sum(int((estimates[i] - estimates[j]) * np.sign(truth[i] - truth[j]) > .01)
                           for i, j in pairs),
            "false_advantages": sum(int(estimates[i] > best_estimated_passive + .01
                                        and truth[i] < best_passive - .01)
                                    for i in range(len(truth)) if i not in passive),
            "unprofitable_shove_detected": bool(bad_shove and
                estimates[root.labels.index("all_in")] < best_estimated_passive - .01),
            "mae": float(abs(truth - estimates).mean()),
            "signed": float((estimates - truth).mean()),
        }
    for label, row in details.items():
        if row["source"] == "incumbent":
            assert answers["C"]["values"][label] == answers["A"]["values"][label]
    return {"closing": closing, "hero": deal[:2], "board": deal[4:],
            "state": asdict(state), "opportunities": dict(Counter(action_types.values())),
            "action_types": action_types, "bad_shove": bad_shove,
            "rank_pairs": len(pairs), "arms": answers, "reply_details": details}, calibration


def cluster_study(family, cluster, schedule, archive, timings):
    train_seed, test_seed, _, n_deals = schedule
    train = Random(train_seed + 100 * family + cluster)
    test = Random(test_seed + 100 * family + cluster)
    if archive:
        # Consume Phase 5E's 32 realized reply draws before the archived EV deals.
        for _ in range(32):
            test.sample(prior.FULL_DECK, 9)
            test.random()
        deals = [test.sample(prior.FULL_DECK, 9) for _ in range(n_deals)]
        draws = [test.random() for _ in deals]
    else:
        deals = [test.sample(prior.FULL_DECK, 9) for _ in range(n_deals)]
        draws = [test.random() for _ in deals]

    profiles = [EvidenceProfile(f"{family}:{cluster}:{member}") for member in range(2)]
    old = [prior.OpponentModel("b"), prior.OpponentModel("b")]
    rare = cluster % 2
    rare_count = 150 if archive else (150, 5, 0)[cluster // 2]
    for i in range(max(rare_count, 300 - rare_count)):
        deal, draw = train.sample(prior.FULL_DECK, 9), train.random()
        for member, profile in enumerate(profiles):
            for context in range(2):
                if i >= (rare_count if context == rare else 300 - rare_count):
                    continue
                reply = prior.sample(truth_law(family, member, context, archive), draw)
                started = perf_counter()
                hand = prior.public_history(deal, family, context, reply)
                timings["training_replay"].append(perf_counter() - started)
                started = perf_counter()
                assert profile.update(f"{i}:{context}", hand, "b")
                timings["indexed_aggregation"].append(perf_counter() - started)
                old[member].update(hand)

    ev = []
    reply = []
    for member, profile in enumerate(profiles):
        snapshot = old[member].snapshot()
        assert profile.v2.hands_observed == 300
        # Independent realized replies at both scripted prices, including sizes
        # outside the evaluator's finite Hero menu.
        for j, (deal, draw) in enumerate(zip(deals, draws, strict=True)):
            for context in range(2):
                law = truth_law(family, member, context, archive)
                observed = prior.sample(law, draw)
                row = prior.target(prior.public_history(deal, family, context, observed), family)
                assert row.response == observed
                p, evidence = prediction(profile, snapshot, row.situation, row.collectible, row.matched_pot, law)
                assert evidence.replies == (rare_count if context == rare else 300 - rare_count)
                reply.append({"member": member, "deal": j, **reply_row(
                    row.situation, row.collectible, row.matched_pot, p, evidence, observed, "scripted")})
            closing = j % (2 if archive else 3) == (1 if archive else 2)
            started = perf_counter()
            case, panel = ev_case(family, member, deal, closing, profile, snapshot, draw, archive, timings)
            timings["exact"].append(perf_counter() - started)
            ev.append({"member": member, "deal": j, **case})
            reply.extend({"member": member, "deal": j, **row} for row in panel)
    return {"family": prior.FAMILIES[family], "cluster": cluster, "rare_count": rare_count,
            "training_replies": [profile.v2.hands_observed for profile in profiles], "ev": ev, "reply": reply}


def memory_probe():
    rng = Random(891990)
    histories = [prior.public_history(rng.sample(prior.FULL_DECK, 9), 2, i % 2, "call")
                 for i in range(300)]
    result = {}
    for model in ("incumbent", "v2", "indexed_v2"):
        prior_times = []
        profile = (prior.OpponentModel("b") if model == "incumbent" else
                   prior.ProfileV2("allocation") if model == "v2" else EvidenceProfile("allocation"))
        tracemalloc.start()
        for i, hand in enumerate(histories):
            started = perf_counter()
            if model == "incumbent":
                profile.update(hand)
            else:
                profile.update(str(i), hand, "b")
            prior_times.append(perf_counter() - started)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result[model] = {"retained_bytes": retained, "peak_bytes": peak,
                         "instrumented_seconds": prior.latency(prior_times)}
    from research.holdem.reply_forecast import river_counts
    old = prior.OpponentModel("b")
    for hand in histories:
        old.update(hand)
    snapshot = old.snapshot()
    assert sum(river_counts(snapshot)) == len(histories)
    for state, hand in (("supported", histories[0]), ("unsupported", histories[1])):
        row = prior.target(hand, 2)
        price = row.collectible if state == "supported" else row.collectible - 1
        baseline = lambda: prior.incumbent(snapshot, row.situation)
        times = {"incumbent": [], "hybrid": []}
        for _ in range(1000):
            started = perf_counter()
            original = baseline()
            times["incumbent"].append(perf_counter() - started)
            started = perf_counter()
            predicted, evidence = hybrid_forecast(profile, row.situation, price, row.matched_pot, baseline)
            times["hybrid"].append(perf_counter() - started)
            assert evidence.coverage == state
            if state == "unsupported":
                assert predicted == original
        result[state] = {key: prior.latency(values) for key, values in times.items()}
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "holdout", "archive", "development", "memory"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    frozen = args.directory / "frozen.json"
    if args.stage == "freeze":
        if frozen.exists():
            raise FileExistsError(frozen)
        prior.write(frozen, manifest())
        return
    if args.stage == "holdout" and manifest() != json.loads(frozen.read_text(encoding="utf-8")):
        raise RuntimeError("study changed after freeze")
    if args.stage == "memory":
        prior.write(args.directory / "profile-memory.json", memory_probe())
        return
    schedule = {"holdout": HOLDOUT, "archive": ARCHIVE, "development": DEVELOPMENT}[args.stage]
    jobs = [(family, cluster) for family in prior.EV_FAMILIES for cluster in range(schedule[2])]
    timings = {key: [] for key in ("training_replay", "indexed_aggregation", "forecast_panel", "exact")}
    cells = []
    for family, cluster in reversed(jobs) if args.reverse else jobs:
        cells.append(cluster_study(family, cluster, schedule, args.stage == "archive", timings))
        print(prior.FAMILIES[family], cluster, flush=True)
    suffix = ("-31" if args.reverse else "-13") if args.stage == "holdout" else ""
    prior.write(args.directory / f"{args.stage}{suffix}.json",
                sorted(cells, key=lambda row: (row["family"], row["cluster"])))
    prior.write(args.directory / f"{args.stage}{suffix}-timing.json",
                {**{key: prior.latency(values) for key, values in timings.items()},
                 "peak_mib": prior.peak_resident_bytes() / 2**20})


if __name__ == "__main__":
    main()
