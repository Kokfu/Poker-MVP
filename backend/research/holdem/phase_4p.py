"""Isolated Phase 4P preflop-weight calibration and river factorial."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from itertools import combinations, product
import json
from math import fsum, sqrt
from pathlib import Path
from random import Random
from statistics import mean, median
from time import perf_counter

import numpy as np

from coach.service import SpotAction
from poker_analyzer import FULL_DECK, RANK_VALUE
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, peak_resident_bytes, strength, train
from research.holdem.phase_4l import exact_values, modeled_continuation, normalize, payoff_values, reference
from research.holdem.phase_4m import check_menu, measure_candidate, oracle_response, reply_nodes
from research.holdem.phase_4n import PROFILES, read_prior, tv
from research.holdem.phase_4o import (
    Case, LINES, PriorTrace, production_stages, reference_likelihood, reference_vectors, score_policies,
)
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV
from simulation.range_intelligence import HoleCardCombo, describe_preflop
from solver.bot import map_action, replay_hand
from solver.combos import COMBOS, combo_index
from solver.preflop import CHART_BB, load_charts


DEPTHS = (9, 15, 30)
PATHS = ("open_call", "limp_call", "bb_threebet", "sb_call_threebet")
CONTEXTS = ("sb_first", "bb_open", "bb_limp", "sb_limp_raise", "sb_threebet")
LEVELS = ("premium", "strong", "playable", "speculative", "weak")
ACTIONS = ("fold", "call", "raise")
GROUPS = np.array([LEVELS.index(describe_preflop(HoleCardCombo(*pair)).category) for pair in COMBOS])
PANELS = {"development": (436_101, 4, (101,)), "holdout": (436_102, 12, (111, 112))}
CALIBRATION_DRAWS = {3: 4, 30: 32, 100: 128}
CONFIGURATIONS = {"A": (False, False), "B": (True, False), "C": (False, True), "D": (True, True)}
ARMS = ("baseline", "candidate", "incoming_oracle")


@dataclass(frozen=True)
class CalibrationCase(Case):
    path: str

    def spot(self):
        spot = super().spot()
        if self.path == "bb_threebet":
            spot.actions[:2] = [SpotAction("hero", "raise", 200),
                                SpotAction("villain", "raise", self.open_to), SpotAction("hero", "call")]
        elif self.path == "sb_call_threebet":
            spot.actions[:3] = [SpotAction("villain", "raise", 200),
                                SpotAction("hero", "raise", self.open_to), SpotAction("villain", "call")]
        return spot


def cases(seed, count, orientation):
    rng = Random(seed)
    for index in range(count):
        deal = rng.sample(FULL_DECK, 7)
        path_index = (index + orientation) % len(PATHS)
        depth = DEPTHS[(index + 2 * orientation) % len(DEPTHS)]
        path = PATHS[path_index]
        opening = (200, 250, 300)[(index // 4 + orientation) % 3]
        if path_index >= 2:
            opening = 350 if depth == 9 else 500
        line_number = (index // 4 + 2 * orientation) % 3 if path_index < 2 else 0
        line = LINES[line_number]
        contribution = opening * (1 if line == LINES[0] else 2)
        shove = bool((index // 2 + orientation) % 2) or depth * BIG_BLIND <= 2 * contribution
        yield CalibrationCase(index, tuple(deal[:2]), tuple(deal[2:]), depth, opening,
                              "button" if path_index % 2 == 0 else "big_blind",
                              line, shove, path)


def context(button, limped, raises):
    """Public state before the action, using real, unabstracted replay."""
    if button:
        if not raises:
            return "sb_first"
        return "sb_limp_raise" if limped else "sb_threebet"
    return "bb_limp" if limped and not raises else "bb_open"


def action_group(kind):
    if kind in ("call", "check"):
        return "call"
    if kind in ("raise", "all_in"):
        return "raise"
    return kind


def observations(replay, villain, hero_button):
    limped, raises = False, 0
    for step in replay.steps:
        if step.street != "preflop":
            break
        actor_button = (step.player == villain) != hero_button
        if step.player == villain:
            yield context(actor_button, limped, raises), action_group(step.kind)
        if step.kind == "call" and actor_button and not raises:
            limped = True
        if step.kind == "raise":
            raises += 1


def reference_action_law(pair, site, depth, style):
    """Explicit synthetic fold/passive/aggression law in action-group order."""
    high, low = sorted((RANK_VALUE[card[0]] for card in pair), reverse=True)
    strong = high == low or (high == 14 and low >= 10)
    suited = pair[0][1] == pair[1][1]
    # Rows are SB first, BB vs open, BB vs limp, SB vs isolation, SB vs three-bet.
    contest_strong = (.96, .88, 1., .89, .83)
    contest_weak = (.55, .28, 1., .47, .20)
    raise_strong = (.53, .32, .50, .17, .15)
    raise_weak = (.17, .09, .20, .05, .04)
    index = CONTEXTS.index(site)
    stretch = (depth - 15) / 15
    contest = (contest_strong if strong else contest_weak)[index]
    if site != "bb_limp":
        contest += (.14 if not style.tight else -.12) * (1 if not strong else .25)
        contest += (.09 if suited else 0) + .06 * stretch * (1 if not strong else -.25)
        contest = min(.99, max(.035, contest))
    aggression = (raise_strong if strong else raise_weak)[index]
    aggression *= 1.50 if style.aggressive else .48
    aggression *= 1 + (.19 if suited or not strong else -.12) * stretch
    return (1 - contest, contest * (1 - aggression), contest * aggression)


def reference_weights(pairs, history, depth, style):
    """Independent direct products over independently enumerated legal pairs."""
    masses = [1.0] * len(pairs)
    for site, action in history:
        group = ACTIONS.index(action)
        masses = [mass * reference_action_law(pair, site, depth, style)[group]
                  for pair, mass in zip(pairs, masses, strict=True)]
    return np.array(masses) / fsum(masses)


def sample_counts(name, stream):
    """Generate separate labeled simulator opportunities, then retain counts only."""
    rng = Random(63_000_000 + stream * 100 + tuple(STYLES).index(name))
    style = STYLES[name]
    counts = np.zeros((len(CONTEXTS), len(DEPTHS), len(LEVELS), len(ACTIONS)), dtype=np.int64)
    snapshots = {n: np.zeros_like(counts) for n in CALIBRATION_DRAWS}
    for si, site in enumerate(CONTEXTS):
        for di, depth in enumerate(DEPTHS):
            for sample in range(1, max(CALIBRATION_DRAWS.values()) + 1):
                pair = rng.sample(FULL_DECK, 2)
                # A later SB opportunity requires its own earlier action. Hero's
                # intervening action is scripted and independent of Villain cards.
                prior_action = {"sb_limp_raise": 1, "sb_threebet": 2}.get(site)
                while prior_action is not None and rng.random() >= reference_action_law(
                    pair, "sb_first", depth, style
                )[prior_action]:
                    pair = rng.sample(FULL_DECK, 2)
                action = rng.choices(range(len(ACTIONS)), weights=reference_action_law(pair, site, depth, style))[0]
                counts[si, di, GROUPS[combo_index(pair)], action] += 1
                for n, draws in CALIBRATION_DRAWS.items():
                    if sample == draws:
                        snapshots[n][si, di] = counts[si, di]
    return snapshots


def calibrated_row(chart, groups, menu, observed, local, other_depths):
    """Smooth grouped counts, project to chart support, preserve size splits."""
    action_ids = np.array([ACTIONS.index(action_group(kind)) for kind, _ in menu])
    base = np.stack([chart[action_ids == group].sum(axis=0) for group in range(len(ACTIONS))])
    pooled = other_depths[groups].T
    pooled_total = pooled.sum(axis=0)
    # At most eight pseudo-observations from other depths, with eight more
    # chart observations damping the cross-depth estimate when data are scarce.
    pooled = 8 * pooled / (pooled_total + 8)
    pseudo_counts = (local[groups].T + pooled) * (base > 0)
    posterior_counts = pseudo_counts + 8 * base
    fitted = posterior_counts / posterior_counts.sum(axis=0)
    group = action_ids[observed]
    split = np.divide(chart[observed], base[group], out=np.zeros_like(chart[observed]), where=base[group] > 0)
    return fitted[group] * split


def chart_actions(bot, replay, villain, history, ids, unlocked=False):
    tree = bot.charts.trees[bot.chart_depth]
    node = tree.root
    scale = CHART_BB / BIG_BLIND
    contexts = iter(history)
    output = []
    for step in replay.steps:
        if step.street != "preflop":
            break
        choice = map_action(tree, node, step.kind, step.target, scale)
        current = tree.nodes[node]
        if step.player == villain:
            site, _ = next(contexts)
            strategy = bot.charts.strategy(bot.chart_depth, node) if unlocked else bot.chart_policy(node)
            output.append((site, strategy[:, ids], current.actions, choice))
        node = current.children[choice]
    return output


def prefixes(rows, ids, depth, counts=None):
    reach = np.ones(len(ids))
    distributions = []
    for site, chart, menu, observed in rows:
        weights = chart[observed]
        if counts is not None:
            table = counts[CONTEXTS.index(site)]
            di = DEPTHS.index(depth)
            weights = calibrated_row(chart, GROUPS[ids], menu, observed, table[di], table.sum(axis=0) - table[di])
        reach = reach * weights
        distributions.append(normalize(reach))
    return distributions


def range_accuracy(weights, truth, ids):
    return {
        "tv": tv(weights, truth), "coverage": float(np.mean(weights > 0)),
        "missing_mass": float(truth[weights == 0].sum()),
        "effective_combos": float(1 / (weights @ weights)),
        "category_mass": [float(weights[GROUPS[ids] == k].sum()) for k in range(len(LEVELS))],
        "category_tv": [float(abs(weights - truth)[GROUPS[ids] == k].sum() / 2) for k in range(len(LEVELS))],
    }


def candidate_ranges(rows, ids, river_ids, depth, counts, baseline_pre, prior):
    calibrated = prefixes(rows, ids, depth, counts)
    reweighted = calibrated[-1][river_ids]
    original = baseline_pre[-1][river_ids]
    if not np.array_equal(reweighted > 0, original > 0) or np.any((prior > 0) & (original == 0)):
        raise AssertionError("preflop reweighting changed chart support or lost production reach")
    ratio = np.divide(reweighted, original, out=np.zeros_like(prior), where=original > 0)
    result = normalize(prior * ratio)
    if not np.array_equal(result > 0, prior > 0):
        raise AssertionError("candidate changed production river support")
    return calibrated, result


def exact_ranges(case, history, steps, style, holdings, historical):
    if historical:
        rows, prior, post, exact = reference_vectors(case, steps, style, holdings)
        return prior, post, exact, rows[-1]
    pairs = [holding.combo for holding in holdings]
    initial = reference_weights(pairs, history, case.depth, style)
    remaining = [step for step in steps if step.street != "preflop"]
    if len(remaining) < 1:
        raise AssertionError("missing observed river action")
    prior_mass = initial.copy()
    for step in remaining[:-1]:
        board = case.board[:3 if step.street == "flop" else 4]
        prior_mass *= [reference_likelihood(step, style, pair, RANKER.score(list(pair), list(board)))
                       for pair in pairs]
    wager = np.array([reference_likelihood(remaining[-1], style, h.combo, h.rank) for h in holdings])
    by_pair = dict(zip(pairs, prior_mass, strict=True))
    by_wager = dict(zip(pairs, wager, strict=True))
    bayes = posterior(case.hero, case.board, by_pair.__getitem__, by_wager.__getitem__)
    exact = ExactRiverEV(case.hero, case.board, lambda pair, _: by_pair[pair] * by_wager[pair])
    if not np.allclose(tuple(bayes.values()), [h.weight for h in exact.holdings], atol=1e-14, rtol=0):
        raise AssertionError("independent reference enumerators disagree")
    return normalize(prior_mass), np.array(tuple(bayes.values())), exact, wager
def evaluate(case, name, stream, hands, profile, counts, historical=False):
    start = perf_counter()
    bot = PriorTrace()
    spot = case.spot()
    node, ds, advice = bot.trace(spot, profile)
    live_seconds = perf_counter() - start
    keys = check_menu(bot, node, ds, advice)
    state = reference(case, node)
    if (state.pot, state.villain_commit) != (case.pot + case.bet, case.bet):
        raise AssertionError("unexpected river geometry")

    holdings = ExactRiverEV(case.hero, case.board, lambda *_: 1).holdings
    pre_pairs = list(combinations((card for card in FULL_DECK if card not in case.hero), 2))
    ids = np.array([combo_index(pair) for pair in pre_pairs])
    pairs = [h.combo for h in holdings]
    legal_ids = np.array([combo_index(pair) for pair in pairs])
    pre_lookup = {cid: i for i, cid in enumerate(ids)}
    cohort = np.array([pre_lookup[cid] for cid in legal_ids])
    if len(set(ids)) != 1225 or len(set(legal_ids)) != 990 or any(
        set(pair).intersection(case.hero + case.board) for pair in pairs
    ):
        raise AssertionError("wrong blocker support")

    replay = replay_hand(ds)
    villain = 1 - node.player
    steps = [step for step in replay.steps if step.player == villain]
    history = tuple(observations(replay, villain, case.seat == "button"))
    chart_rows = chart_actions(bot, replay, villain, history, ids)
    baseline_pre = prefixes(chart_rows, ids, case.depth)
    unlocked = prefixes(chart_actions(bot, replay, villain, history, ids, unlocked=True), ids, case.depth)
    _, chart, _, _, extended_wager = production_stages(bot, replay, villain, legal_ids, case.hero)
    if not np.allclose(normalize(chart), normalize(baseline_pre[-1][cohort]), atol=1e-14, rtol=0):
        raise AssertionError("preflop trace differs from production")
    _, prior, _, _, mapped, mapped_label = read_prior(bot, holdings, case)
    if not np.array_equal(extended_wager[prior > 0], mapped[prior > 0]):
        raise AssertionError("production likelihood changed on supported hands")

    (candidate_pre, candidate_prior), metrics = measure_candidate(
        lambda: candidate_ranges(chart_rows, ids, cohort, case.depth, counts, baseline_pre, prior)
    )
    actual, _, production, hero_policy, live_values = modeled_continuation(bot, node, holdings)
    if not np.allclose(normalize(prior * extended_wager), actual, atol=1e-12, rtol=0):
        raise AssertionError("controlled baseline differs from actual production posterior")
    tree = bot.river.tree
    parity = float(abs(payoff_values(tree, node, holdings, actual, production, hero_policy) - live_values).max())
    if parity > .003 or bot.fallback_count:
        raise AssertionError(f"production value discrepancy or fallback: {parity} chips")
    style = STYLES[name]
    exact_prior, truth, exact, true_wager = exact_ranges(case, history, steps, style, holdings, historical)
    true_values = exact_values(exact, state, keys, style.call_probability)
    true_responses = {reply.index: oracle_response(reply, holdings, style, False)
                      for reply in reply_nodes(tree, node)}
    audited = payoff_values(tree, node, holdings, truth, true_responses, hero_policy) / BIG_BLIND
    if not np.allclose(audited, list(true_values.values()), atol=1e-10, rtol=0):
        raise AssertionError("exact EV and independent payoff traversal disagree")

    estimate = (prior, candidate_prior, exact_prior)
    decisions = {}
    posterior_ranges = {}
    for setting, (wager_oracle, response_oracle) in CONFIGURATIONS.items():
        likelihood = true_wager if wager_oracle else extended_wager
        ranges = {arm: normalize(weights * likelihood) for arm, weights in zip(ARMS, estimate, strict=True)}
        decisions[setting] = score_policies(bot, node, holdings, keys, ranges,
                                            true_responses if response_oracle else production,
                                            hero_policy, true_values)
        posterior_ranges[setting] = ranges

    preflop = []
    weights_at_decision = (baseline_pre, candidate_pre, unlocked)
    for index, (site, action) in enumerate(history):
        if historical:
            probability = np.array([style.participate(pair) * (1 - style.raise_probability) for pair in pre_pairs])
            target = normalize(probability ** (index + 1))
        else:
            target = reference_weights(pre_pairs, history[:index + 1], case.depth, style)
        preflop.append({"context": site, "action": action, **{
            arm: range_accuracy(weights[index], target, ids)
            for arm, weights in zip(("baseline", "candidate", "unlocked"), weights_at_decision, strict=True)
        }, "oracle": range_accuracy(target, target, ids)})
    outcome = np.array([(h.result + 1) / 2 for h in holdings])
    classes = np.array([strength(h.rank) for h in holdings])
    row = {
        "case": asdict(case), "opponent": name, "stream": stream, "hands": hands,
        "pot_before_river_bet": case.pot, "observed": case.observed, "mapped": mapped_label,
        "history": [asdict(action) for action in spot.actions], "chart_depth": bot.chart_depth,
        "chart_locked": bot.chart_locked, "preflop": preflop,
        "exact_ev_bb": true_values, "decision": decisions, "live_advice": advice,
        "live_mix": dict(zip(keys, bot.probabilities.tolist(), strict=True)),
        "parity_chips": parity, "fallbacks": bot.fallback_count,
        "incoming": {arm: range_accuracy(weights, exact_prior, legal_ids)
                     for arm, weights in zip(ARMS, estimate, strict=True)},
        "posterior": {setting: {arm: {
            "tv": tv(weights, truth), "equity": float(weights @ outcome),
            "made_hand_mass": [float(weights[classes == k].sum()) for k in range(3)]
        } for arm, weights in ranges.items()} for setting, ranges in posterior_ranges.items()},
        "performance": {**metrics, "live_seconds": live_seconds},
    }
    if historical or min(delta(row, cfg) for cfg in CONFIGURATIONS) <= -.50:
        row["evidence"] = {
            "combos": pairs, "incoming": {arm: weights.tolist() for arm, weights in zip(ARMS, estimate, strict=True)},
            "true_posterior": truth.tolist(), "production_wager": extended_wager.tolist(),
            "true_wager": true_wager.tolist(),
            "replies": {"production": {str(k): v.tolist() for k, v in production.items()},
                        "reference": {str(k): v.tolist() for k, v in true_responses.items()}},
            "reply_menu": {str(reply.index): reply.actions for reply in reply_nodes(tree, node)},
        }
    return row


def delta(row, setting, arm="candidate"):
    scores = row["decision"][setting]
    return scores[arm]["ev_bb"] - scores["baseline"]["ev_bb"]


def calibration_summary(items):
    return {arm: {
        **{stat: mean(row[arm][stat] for row in items)
           for stat in ("tv", "coverage", "missing_mass", "effective_combos")},
        **{stat: [mean(row[arm][stat][k] for row in items) for k in range(len(LEVELS))]
           for stat in ("category_mass", "category_tv")},
    } for arm in ("baseline", "candidate", "unlocked", "oracle")}


def decision_summary(rows, setting, arm):
    changes = [delta(row, setting, arm) for row in rows]
    policies = [row["decision"][setting][arm] for row in rows]
    frequencies = {}
    for policy in policies:
        for label, probability in policy["mix"].items():
            kind = label.split("_", 1)[0] if label.startswith("raise_") else label
            frequencies[kind] = frequencies.get(kind, 0.) + probability / len(rows)
    losses = [change for change in changes if change < -1e-6]
    return {
        "ev_bb": mean(policy["ev_bb"] for policy in policies), "delta_bb": mean(changes),
        "regret_bb": mean(policy["regret_bb"] for policy in policies),
        "harm_count": len(losses), "harm_above_0.01": sum(change < -.01 for change in changes),
        "harm_cost_bb": -fsum(losses), "worst_delta_bb": min(0., *changes), "mix": frequencies,
        "modal_changes": sum(policy["modal"] != row["decision"][setting]["baseline"]["modal"]
                             for row, policy in zip(rows, policies, strict=True)),
    }


def summarize(rows):
    return {
        "rows": len(rows), "preflop": calibration_summary([row["preflop"][-1] for row in rows]),
        "incoming_tv": {arm: mean(row["incoming"][arm]["tv"] for row in rows) for arm in ARMS},
        "decisions": {setting: {arm: decision_summary(rows, setting, arm) for arm in ARMS}
                      for setting in CONFIGURATIONS},
        "performance": {
            "median_ms": median(row["performance"]["seconds"] for row in rows) * 1000,
            "peak_bytes": max(row["performance"]["traced_peak_bytes"] for row in rows),
            "live_median_ms": median(row["performance"]["live_seconds"] for row in rows) * 1000,
        },
    }


def paired_interval(rows, setting):
    blocks = sorted({row["case"]["index"] for row in rows})
    board_means = [mean(delta(row, setting) for row in rows if row["case"]["index"] == block) for block in blocks]
    rng = Random(4349)
    distribution = sorted(mean(rng.choices(board_means, k=len(blocks))) for _ in range(10_000))
    return distribution[249], distribution[9749]


def chart_discontinuities():
    charts = load_charts()
    results = []
    for low, high in zip(charts.depths, charts.depths[1:]):
        boundary = sqrt(low * high)
        before, after = (charts.nearest_depth(boundary + offset) for offset in (-.001, .001))
        trees = charts.trees
        blind_call = []
        for depth in (before, after):
            tree = trees[depth]
            index = tree.nodes[tree.root].children[map_action(tree, tree.root, "raise", 250)]
            choice = map_action(tree, index, "call", None)
            blind_call.append(normalize(charts.strategy(depth, index)[choice]))
        results.append({"boundary_bb": boundary, "before": before, "after": after,
                        "unblocked_bb_call_tv": tv(*blind_call)})
    return results


def run(panel, progress=False):
    if panel == "historical":
        case = Case(11, ("Js", "3c"), ("2d", "Ah", "Jh", "2h", "Kh"), 30, 300,
                    "big_blind", LINES[2], True)
        name, stream, hands = "loose_aggressive", 91, 30
        row = evaluate(case, name, stream, hands, train(name, stream, (hands,))[hands],
                       sample_counts(name, 103)[hands], historical=True)
        oracle_loss = delta(row, "A", "incoming_oracle")
        if abs(oracle_loss + 18.72031252) > .001:
            raise AssertionError(f"historical exact-prior loss drifted: {oracle_loss}")
        return {"panel": panel, "rows": [row]}
    seed, count, streams = PANELS[panel]
    rows = []
    for orientation, stream in enumerate(streams):
        for name in STYLES:
            profiles = train(name, stream, PROFILES)
            counts = sample_counts(name, stream)
            for case in cases(seed, count, orientation):
                hands = PROFILES[(case.index // 4 + case.index + orientation) % len(PROFILES)]
                rows.append(evaluate(case, name, stream, hands, profiles[hands], counts[hands]))
            if progress:
                print(f"{panel} stream {stream}, {name}, {len(rows)} decisions", flush=True)
    main = summarize(rows)
    groups = {}
    for key, extract in {
        "opponent": lambda row: row["opponent"], "stream": lambda row: row["stream"],
        "profile_hands": lambda row: row["hands"], "position": lambda row: row["case"]["seat"],
        "depth": lambda row: row["case"]["depth"], "path": lambda row: row["case"]["path"],
    }.items():
        values = {extract(row) for row in rows}
        groups[key] = {value: summarize([r for r in rows if extract(r) == value]) for value in sorted(values)}
    prefixes_by_site = {}
    for site in CONTEXTS:
        examples = [entry for row in rows for entry in row["preflop"] if entry["context"] == site]
        if examples:
            prefixes_by_site[site] = calibration_summary(examples)
    result = {"panel": panel, "summary": main, "strata": groups,
              "preflop_by_context": prefixes_by_site, "chart_discontinuities": chart_discontinuities(), "rows": rows}
    if panel == "holdout":
        intervals = {setting: paired_interval(rows, setting) for setting in CONFIGURATIONS}
        primary = main["decisions"]["A"]["candidate"]
        checks = {
            "mean_at_least_0.05_bb": primary["delta_bb"] >= .05,
            "paired_ci_lower_above_zero": intervals["A"][0] > 0,
            "worst_loss_at_most_0.50_bb": primary["worst_delta_bb"] >= -.50,
            "harm_rate_at_most_10_percent": primary["harm_above_0.01"] / len(rows) <= .10,
            "each_opponent_at_least_minus_0.03_bb": all(
                stratum["decisions"]["A"]["candidate"]["delta_bb"] >= -.03
                for stratum in groups["opponent"].values()),
            "preflop_tv_improves_at_least_0.01": (
                main["preflop"]["baseline"]["tv"] - main["preflop"]["candidate"]["tv"] >= .01),
            "median_under_5_ms": main["performance"]["median_ms"] < 5,
            "peak_under_256_kib": main["performance"]["peak_bytes"] < 256 * 1024,
            "zero_fallbacks": not any(row["fallbacks"] for row in rows),
        }
        result.update(paired_ci95=intervals, gate={"checks": checks, "pass": all(checks.values())})
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=(*PANELS, "historical"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    start = perf_counter()
    result = run(args.panel, progress=True)
    result.update(wall_seconds=perf_counter() - start, process_peak_resident_bytes=peak_resident_bytes())
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
