"""Offline Phase 4O incoming-range support experiment."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from itertools import product
import json
from math import fsum
from pathlib import Path
from random import Random
from time import perf_counter

import numpy as np

from coach.service import Spot, SpotAction
from poker_analyzer import FULL_DECK
from research.holdem.phase_4k import BIG_BLIND, MISMATCH, RANKER, STYLES, peak_resident_bytes, strength, train
from research.holdem.phase_4l import (
    exact_values, fixed_value_mix, modeled_continuation, normalize, payoff_values,
    reference, response_means, weighted_ev,
)
from research.holdem.phase_4m import check_menu, measure_candidate, oracle_response, reply_nodes
from research.holdem.phase_4n import (
    ARMS, PROFILES, SETTINGS, Case as HistoricalCase, PreBetTrace, diff, gate, interval,
    range_metrics, read_prior, summarize, tv,
)
from research.holdem.river_bayes_reference import opening_actions, posterior
from research.holdem.river_bet_range import bet_update
from research.holdem.river_ev import ExactRiverEV
from solver.bot import map_action, replay_hand
from solver.combos import card_mask, combo_index


PANELS = {"development": (435_101, 6, (81,)), "holdout": (435_102, 12, (91, 92))}
LINES = (("check", "check"), ("lead", "check"), ("check", "call"))
DECK_ORDER = {card: i for i, card in enumerate(FULL_DECK)}


@dataclass(frozen=True)
class Case:
    index: int
    hero: tuple
    board: tuple
    depth: int
    open_to: int
    seat: str
    line: tuple
    shove: bool

    @property
    def pot(self):
        return 2 * self.open_to * (2 if self.line != LINES[0] else 1)

    @property
    def behind(self):
        return self.depth * BIG_BLIND - self.pot // 2

    @property
    def bet(self):
        return self.behind if self.shove else self.pot // 2

    @property
    def observed(self):
        return ("all_in" if self.shove else "bet", self.bet)

    def spot(self):
        button = self.seat == "button"
        actions = [] if button else [SpotAction("villain", "call")]
        actions += [SpotAction("hero", "raise", self.open_to), SpotAction("villain", "call")]
        first, second = ("villain", "hero") if button else ("hero", "villain")
        for line in self.line:
            if line == "check":
                actions += [SpotAction(first, "check"), SpotAction(second, "check")]
            else:
                aggressor, caller = ("villain", "hero") if line == "lead" else ("hero", "villain")
                if first != aggressor:
                    actions.append(SpotAction(first, "check"))
                actions += [SpotAction(aggressor, "bet", self.open_to), SpotAction(caller, "call")]
        if not button:
            actions.append(SpotAction("hero", "check"))
        kind, target = self.observed
        actions.append(SpotAction("villain", kind, None if self.shove else target))
        return Spot(list(self.hero), list(self.board), hero_position=self.seat,
                    hero_stack=self.depth * BIG_BLIND, villain_stack=self.depth * BIG_BLIND,
                    actions=actions)


def cases(seed, count, orientation):
    rng = Random(seed)
    for i in range(count):
        deal = rng.sample(FULL_DECK, 7)
        depth = (9, 15, 30)[(i // 2 + orientation) % 3]
        yield Case(i, tuple(deal[:2]), tuple(deal[2:]), depth,
                   200 if depth == 9 else (200, 250, 300)[i % 3],
                   ("button", "big_blind")[(i + orientation) % 2],
                   LINES[(i + orientation) % 3], bool((i // 3 + orientation) % 2))


class PriorTrace(PreBetTrace):
    """Capture read-only inputs from the production replay, without another solve."""

    def __init__(self):
        super().__init__(917)
        self.actions = []
        self.roots = {}

    def _preflop_policy(self, depth, opponent, locks):
        self.chart_depth = depth
        self.chart_locked = bool(locks)
        self.chart_policy = super()._preflop_policy(depth, opponent, locks)
        return self.chart_policy

    def _street_solve(self, key, state, board, ranges, hero_combo, hero, profile=None):
        self.roots[state.street] = (board, ranges[1 - hero], hero_combo)
        return super()._street_solve(key, state, board, ranges, hero_combo, hero, profile)

    def _apply_strategy(self, weights, solve, node, choice):
        updated = super()._apply_strategy(weights, solve, node, choice)
        self.actions.append((weights, solve, node, choice, updated))
        return updated


def action_row(weights, combo_ids, probabilities, blocked, legal_ids):
    """Use the retained reach-weighted action frequency for unavailable columns."""
    donors = np.where(blocked[combo_ids], 0.0, weights[combo_ids])
    if not donors.sum() > 0:
        raise ValueError("no compatible action donors")
    pooled = (donors @ probabilities) / donors.sum()
    extended = np.full(weights.shape, pooled)
    extended[combo_ids] = probabilities
    return extended[legal_ids]


def recover_prior(chart_reach, earlier_action_rows):
    """Keep positive chart reach through each observed villain action."""
    weights = normalize(chart_reach)
    for row in earlier_action_rows:
        weights = normalize(weights * row)
    return weights


def reference_likelihood(step, style, pair, rank):
    """Law for one actual observed Villain action in the public replay."""
    state = step.before
    if step.street == "preflop":
        if step.kind != "call" or state.highest <= state.commit[step.player]:
            raise AssertionError("reference preflop path requires a paid call")
        return style.participate(pair) * (1 - style.raise_probability)
    if step.kind == "check":
        return 1 - style.open_probability(rank)
    if step.kind == "call":
        cost = state.highest - state.commit[step.player]
        return style.call_probability(pair, rank, cost, state.pot)
    if step.kind in ("bet", "all_in") and state.highest == 0:
        return opening_actions(state.pot, BIG_BLIND, state.stack[step.player],
                               style.open_probability(rank), strength(rank)).get((step.kind, step.target), 0)
    raise AssertionError(f"unsupported reference action: {step}")


def reference_vectors(case, steps, style, holdings):
    """Evaluate causal prior products and cross-check the independent enumerator."""
    pairs = [h.combo for h in holdings]
    if pairs != sorted(pairs, key=lambda pair: tuple(DECK_ORDER[c] for c in pair)):
        raise AssertionError("reference enumerators use different pair order")
    ranks = {street: [RANKER.score(list(pair), list(case.board[:n])) for pair in pairs]
             for street, n in (("flop", 3), ("turn", 4))}
    ranks["river"] = [h.rank for h in holdings]
    rows = [np.array([reference_likelihood(step, style, pair, rank)
                      for pair, rank in zip(pairs, ranks.get(step.street, [None] * len(pairs)), strict=True)])
            for step in steps]
    prior_mass = np.prod(rows[:-1], axis=0)
    by_pair = dict(zip(pairs, prior_mass, strict=True))
    wager = dict(zip(pairs, rows[-1], strict=True))
    pre = np.array(list(posterior(case.hero, case.board, by_pair.__getitem__, lambda _: 1).values()))
    post = np.array(list(posterior(case.hero, case.board, by_pair.__getitem__, wager.__getitem__).values()))
    exact = ExactRiverEV(case.hero, case.board, lambda pair, _: by_pair[pair] * wager[pair])
    if not (np.allclose(pre, prior_mass / fsum(prior_mass), rtol=0, atol=1e-14)
            and np.allclose(post, [h.weight for h in exact.holdings], rtol=0, atol=1e-14)):
        raise AssertionError("reference probability enumerations disagree")
    return rows, pre, post, exact


def production_stages(bot, replay, villain, legal_ids, hero):
    """Map every loss on the same final legal cohort to its earliest cause."""
    depth = bot.chart_depth
    chart = bot.charts.trees[depth]
    node = chart.root
    reach = np.ones(len(legal_ids))
    unlocked = reach.copy()
    stages = []
    candidate_rows = []
    count = 0
    for step in (s for s in replay.steps if s.street == "preflop"):
        choice = map_action(chart, node, step.kind, step.target)
        if step.player == villain:
            count += 1
            reach = reach * bot.chart_policy(node)[choice, legal_ids]
            unlocked = unlocked * bot.charts.strategy(depth, node)[choice, legal_ids]
            stages.append((f"preflop_{count}_{step.kind}", count, reach))
        node = chart.nodes[node].children[choice]
    chart_reach = reach
    postflop = [s for s in replay.steps if s.street != "preflop"]
    streets = set()
    for step, (weights, solve, index, choice, updated) in zip(postflop, bot.actions, strict=True):
        if step.player != villain:
            continue
        node = solve.tree.nodes[index]
        if node.player != villain or not np.array_equal(weights[legal_ids], reach):
            raise AssertionError("inconsistent actor reach at observed action")
        keep = np.isin(legal_ids, solve.combos[villain])
        if step.street not in streets:
            streets.add(step.street)
            stages.append((f"{step.street}_prune", count, reach * keep))
        board, _, _ = bot.roots[step.street]
        row_args = (weights, solve.combos[villain], solve.average[index][choice],
                    card_mask(hero + board), legal_ids)
        if step is postflop[-1]:
            return stages, chart_reach, unlocked, candidate_rows, action_row(*row_args)
        count += 1
        reach = updated[legal_ids]
        stages.append((f"{step.street}_{count}_{step.kind}", count, reach))
        candidate_rows.append(row_args)
    raise AssertionError("missing observed river wager")


def audit_losses(stages, rows, true_prior, true_post, combos):
    first = np.full(len(combos), -1)
    audit = {}
    reference_reach = [np.full(len(combos), 1 / len(combos))]
    for row in rows[:-1]:
        reference_reach.append(normalize(reference_reach[-1] * row))
    for index, (label, steps, reach) in enumerate(stages):
        removed = (first < 0) & (reach == 0)
        first[removed] = index
        audit[label] = {
            "newly_absent": int(removed.sum()),
            "prior_mass": float(true_prior[removed].sum()),
            "posterior_mass": float(true_post[removed].sum()),
            "prefix_tv": tv(normalize(reach), reference_reach[steps]),
            "prefix_missing": float(reference_reach[steps][reach == 0].sum()),
        }
    if not np.array_equal(first >= 0, stages[-1][2] == 0):
        raise AssertionError("observed production reach recovered an absent combo")
    return audit, [stages[i][0] if i >= 0 else None for i in first]


def score_policies(bot, node, holdings, keys, ranges, responses, hero_policy, exact_evs):
    policies = {}
    for name, weights in ranges.items():
        if not np.array_equal(normalize(weights) > 0, weights > 0) or abs(fsum(weights) - 1) > 1e-12:
            raise AssertionError("invalid range probabilities")
        values = payoff_values(bot.river.tree, node, holdings, weights, responses, hero_policy)
        mix = fixed_value_mix(values, bot.iterations["river"])
        if not np.isfinite(values).all() or (mix < 0).any() or abs(fsum(mix) - 1) > 1e-12:
            raise AssertionError("invalid decision EV or frequencies")
        mix_by_key = dict(zip(keys, mix.tolist(), strict=True))
        ev = weighted_ev(mix_by_key, exact_evs)
        policies[name] = {
            "ev_bb": ev, "regret_bb": max(exact_evs.values()) - ev,
            "modal": max(mix_by_key, key=mix_by_key.get), "mix": mix_by_key,
            "modeled_ev_bb": dict(zip(keys, (values / BIG_BLIND).tolist(), strict=True)),
            "replies": {keys[node.children.index(reply.index)]:
                        response_means(reply.actions, responses[reply.index] @ weights)
                        for reply in reply_nodes(bot.river.tree, node)},
        }
    return policies


def evaluate(case, profile_name, stream, hands, profile, historical=False):
    start = perf_counter()
    bot = PriorTrace()
    node, ds, advice = bot.trace(case.spot(), profile)
    live_seconds = perf_counter() - start
    keys = check_menu(bot, node, ds, advice)
    state = reference(case, node)
    if (state.pot, state.villain_commit) != (case.pot + case.bet, case.bet):
        raise AssertionError("unexpected river pot or wager")
    holdings = ExactRiverEV(case.hero, case.board, lambda *_: 1).holdings
    combos = tuple(h.combo for h in holdings)
    if len(set(combos)) != 990 or any(set(pair) & set(case.hero + case.board) for pair in combos):
        raise AssertionError("illegal or duplicate holding")
    legal_ids = np.array([combo_index(pair) for pair in combos])
    replay = replay_hand(ds)
    villain = 1 - node.player
    steps = [step for step in replay.steps if step.player == villain]
    stages, chart, unlocked, earlier, fixed_wager = production_stages(bot, replay, villain, legal_ids, case.hero)
    _, prior, targets, likelihoods, mapped, mapped_label = read_prior(bot, holdings, case)
    if not np.allclose(prior, normalize(stages[-1][2]), rtol=0, atol=1e-14):
        raise AssertionError("traced stages differ from production pre-bet reach")
    baseline = normalize(prior * fixed_wager)
    actual, _, production, hero_policy, live_ev = modeled_continuation(bot, node, holdings)
    if not historical and not np.allclose(baseline, actual, rtol=0, atol=1e-12):
        raise AssertionError("holdout baseline must match final production reach")
    if not np.allclose(actual, normalize(prior * mapped * (actual > 0)), rtol=0, atol=1e-12):
        raise AssertionError("production reach does not match mapped Bayes update and final trim")
    candidate_prior, performance = measure_candidate(
        lambda: recover_prior(chart, (action_row(*args) for args in earlier)))
    candidate = normalize(candidate_prior * fixed_wager)
    tree = bot.river.tree
    parity = float(abs(payoff_values(tree, node, holdings, actual, production, hero_policy) - live_ev).max())
    if parity > .003:
        raise AssertionError(f"live EV discrepancy: {parity} chips")
    classes = np.array([strength(h.rank) for h in holdings])
    outcomes = np.array([(h.result + 1) / 2 for h in holdings])
    stat = profile.snapshot.street_statistics["river"]["bet"]
    rows = []
    for opponent in ((profile_name,) if historical else (profile_name, MISMATCH[profile_name])):
        style = STYLES[opponent]
        reference_rows, true_prior, truth, exact = reference_vectors(case, steps, style, holdings)
        exact_evs = exact_values(exact, state, keys, style.call_probability)
        fixed_oracle = {reply.index: oracle_response(reply, holdings, style, False)
                        for reply in reply_nodes(tree, node)}
        audited = payoff_values(tree, node, holdings, truth, fixed_oracle, hero_policy) / BIG_BLIND
        if not np.allclose(audited, list(exact_evs.values()), rtol=0, atol=1e-10):
            raise AssertionError("reference EV differs from independent tree traversal")
        ranges = dict(zip(ARMS, (baseline, candidate, normalize(true_prior * fixed_wager)), strict=True))
        vectors = {
            **ranges, "production_prior": prior, "candidate_prior": candidate_prior, "true_prior": true_prior,
            "true_posterior": truth, "production_final": actual,
            "production_prior_true_likelihood": normalize(prior * reference_rows[-1]),
            "candidate_prior_true_likelihood": normalize(candidate_prior * reference_rows[-1]),
        }
        if historical:
            old_candidate, relative, _ = bet_update(prior, targets, likelihoods, case.bet, stat.occurrences)
            ranges.update(phase_4n_candidate=old_candidate, phase_4n_true_prior=normalize(true_prior * relative),
                          production_final=actual, full_oracle=truth)
            vectors.update(ranges)
        metrics = {}
        for name, weights in vectors.items():
            target = true_prior if name in ("production_prior", "candidate_prior", "true_prior") else truth
            metrics[name] = range_metrics(weights, target, outcomes, classes)
            low = target < 1 / len(target)
            metrics[name].update(low_truth_reached=int((low & (weights > 0)).sum()),
                                 low_truth_excess=float(np.maximum(weights[low] - target[low], 0).sum()))
        audit, missing_at = audit_losses(stages, reference_rows, true_prior, truth, combos)
        settings = {setting: score_policies(bot, node, holdings, keys, ranges, responses, hero_policy, exact_evs)
                    for setting, responses in zip(SETTINGS, (fixed_oracle, production), strict=True)}
        rows.append({
            "case": asdict(case), "observed": case.observed, "mapped": mapped_label,
            "opponent": opponent, "profile": profile_name, "stream": stream, "hands": hands,
            "matched": profile_name == opponent, "size_confidence": 0, "bet_occurrences": stat.occurrences,
            "range": metrics, "decision": settings, "audit": audit, "chart_depth": bot.chart_depth,
            "chart_locked": bot.chart_locked,
            "unlocked_chart_missing_prior_mass": float(true_prior[unlocked == 0].sum()),
            "exact_ev_bb": exact_evs, "live_advice": advice, "live_mix": bot.probabilities.tolist(),
            "live_ev_bb": weighted_ev(dict(zip(keys, bot.probabilities, strict=True)), exact_evs),
            "solver_ev_max_error_chips": parity, "solver_fallbacks": bot.fallback_count,
            "performance": {**performance, "live_seconds": live_seconds},
            "_evidence": {"combos": combos, "missing_at": missing_at,
                          "weights": vectors, "fixed_wager": fixed_wager},
        })
    return rows


def extreme(row):
    evidence = row["_evidence"]
    return {
        **{k: v for k, v in row.items() if k != "_evidence"},
        "combos": evidence["combos"], "missing_at": evidence["missing_at"],
        "weights": {name: v.tolist() for name, v in evidence["weights"].items()},
        "fixed_wager": evidence["fixed_wager"].tolist(),
    }


def run(panel):
    if panel == "historical":
        case = HistoricalCase(6, ("Ad", "4h"), ("6s", "5d", "Th", "3c", "Qd"), 15, 210, 1.35, "button")
        profiles = train("tight_passive", 72, PROFILES)
        return {"panel": panel, "rows": [
            extreme(evaluate(case, "tight_passive", 72, n, profiles[n], historical=True)[0]) for n in (3, 30)
        ]}
    seed, count, streams = PANELS[panel]
    profiles = {(name, stream): train(name, stream, PROFILES) for name, stream in product(STYLES, streams)}
    rows = []
    for orientation, stream in enumerate(streams):
        for case, name, hands in product(cases(seed, count, orientation), STYLES, PROFILES):
            rows.extend(evaluate(case, name, stream, hands, profiles[name, stream][hands]))
    primary = [row for row in rows if row["matched"]]
    mismatch = [row for row in rows if not row["matched"]]
    extremes = {setting: {
        "worst": extreme(min(primary, key=lambda r: diff(r, setting))),
        "best": extreme(max(primary, key=lambda r: diff(r, setting))),
    } for setting in SETTINGS}
    for row in rows:
        del row["_evidence"]
    matched = summarize(primary)
    mismatched = summarize(mismatch)
    opponents = {name: summarize([r for r in primary if r["opponent"] == name]) for name in STYLES}
    strata = {key: summarize(group) for key, group in (
        *((f"profile_{n}", [r for r in primary if r["hands"] == n]) for n in PROFILES),
        *((f"depth_{n}", [r for r in primary if r["case"]["depth"] == n]) for n in (9, 15, 30)),
        *(("/".join(line), [r for r in primary if tuple(r["case"]["line"]) == line]) for line in LINES),
        *((seat, [r for r in primary if r["case"]["seat"] == seat]) for seat in ("button", "big_blind")),
        *((f"shove_{flag}", [r for r in primary if r["case"]["shove"] == flag]) for flag in (False, True)),
        ("no_opening_bet_observed", [r for r in primary if not r["bet_occurrences"]]),
    ) if group}
    result = dict(panel=panel, primary=matched, mismatch=mismatched, opponents=opponents,
                  strata=strata, extremes=extremes, rows=rows)
    if panel == "holdout":
        intervals = {setting: interval(primary, setting) for setting in SETTINGS}
        verdict = gate(matched, intervals, opponents, mismatched)
        a, b = (matched["range"][name] for name in ("production_prior", "candidate_prior"))
        verdict["checks"]["prior_tv_improves_0.01_and_missing_mass_does_not_increase"] = (
            a["tv"] - b["tv"] >= .01 and b["truth_mass_outside_support"] <= a["truth_mass_outside_support"]
        )
        verdict["pass"] = all(verdict["checks"].values())
        result.update(paired_ci95=intervals, gate=verdict)
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=(*PANELS, "historical"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    start = perf_counter()
    result = run(args.panel)
    result.update(wall_seconds=perf_counter() - start, process_peak_resident_bytes=peak_resident_bytes())
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
