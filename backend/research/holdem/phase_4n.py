"""Bounded, offline range-only experiment with two fixed response settings."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from itertools import product
import json
from math import fsum
from pathlib import Path
from random import Random
from statistics import mean, median
from time import perf_counter

import numpy as np

from coach.service import Spot, SpotAction
from poker_analyzer import FULL_DECK
from research.holdem.phase_4k import BIG_BLIND, MISMATCH, RANKER, STYLES, peak_resident_bytes, strength, train
from research.holdem.phase_4l import (
    Live, exact_values, fixed_value_mix, modeled_continuation, normalize, payoff_values,
    reference, response_means, weighted_ev,
)
from research.holdem.phase_4m import check_menu, measure_candidate, oracle_response, reply_nodes
from research.holdem.river_bayes_reference import SIZES, opening_actions, posterior
from research.holdem.river_bet_range import bet_update
from research.holdem.river_ev import ExactRiverEV
from solver.bot import map_action
from solver.combos import combo_index


PROFILES = (3, 30, 100)
SPLITS = {"calibration": (434_901, 4, (61,)), "holdout": (434_902, 12, (71, 72))}
ARMS = ("baseline", "candidate", "range_oracle")
SETTINGS = ("response_oracle", "production_response")


class PreBetTrace(Live):
    """Read the existing prior and bet policy at the first river aggression."""

    def _apply_strategy(self, weights, solve, node, choice):
        current = solve.tree.nodes[node]
        if current.state.street == "river" and current.actions[choice][0] in ("bet", "all_in"):
            if current.state.highest != 0 or hasattr(self, "pre_bet"):
                raise AssertionError("expected one opening river wager")
            self.pre_bet = (weights.copy(), solve, current, choice)
        return super()._apply_strategy(weights, solve, node, choice)


@dataclass(frozen=True)
class Case:
    index: int
    hero: tuple
    board: tuple
    depth: int
    open_to: int
    fraction: float | None
    seat: str

    @property
    def pot(self):
        return 2 * self.open_to

    @property
    def behind(self):
        return self.depth * BIG_BLIND - self.open_to

    @property
    def bet(self):
        return self.behind if self.fraction is None else round(self.fraction * self.pot)

    @property
    def observed(self):
        return ("all_in" if self.fraction is None else "bet", self.bet)

    def spot(self):
        button = self.seat == "button"
        preflop = ([] if button else [SpotAction("villain", "call")])
        preflop += [SpotAction("hero", "raise", self.open_to), SpotAction("villain", "call")]
        first, second = ("villain", "hero") if button else ("hero", "villain")
        postflop = [SpotAction(first, "check"), SpotAction(second, "check")] * 2
        if not button:
            postflop.append(SpotAction("hero", "check"))
        kind, target = self.observed
        postflop.append(SpotAction("villain", kind, target if kind == "bet" else None))
        return Spot(list(self.hero), list(self.board), hero_position=self.seat,
                    hero_stack=self.depth * BIG_BLIND, villain_stack=self.depth * BIG_BLIND,
                    actions=preflop + postflop)


def cases(seed, count, orientation):
    rng = Random(seed)
    for i in range(count):
        deal = rng.sample(FULL_DECK, 7)
        size = i % 4
        yield Case(i, tuple(deal[:2]), tuple(deal[2:]),
                   (9, 15, 30)[(i // 4 + size + orientation) % 3],
                   (200, 230, 200, 300)[size] + 10 * (i // 4),
                   (*SIZES, None)[size],
                   ("button", "big_blind")[(i // 2 + orientation) % 2])


def reference_ranges(case, style, holdings, earlier_ranks):
    rank = {h.combo: h.rank for h in holdings}
    strength_by_pair = {pair: strength(value) for pair, value in rank.items()}
    checks = {pair: (1 - style.open_probability(flop)) * (1 - style.open_probability(turn))
              for pair, (flop, turn) in earlier_ranks.items()}
    calls = 1 if case.seat == "button" else 2

    def prior(pair):
        contest = style.participate(pair) * (1 - style.raise_probability)
        return contest ** calls * checks[pair]

    observed = {pair: opening_actions(case.pot, BIG_BLIND, case.behind,
                                      style.open_probability(rank[pair]), bucket).get(case.observed, 0)
                for pair, bucket in strength_by_pair.items()}
    true_prior = posterior(case.hero, case.board, prior, lambda _: 1)
    true_posterior = posterior(case.hero, case.board, prior, observed.__getitem__)
    independent = ExactRiverEV(case.hero, case.board, lambda pair, _: prior(pair) * observed[pair])
    vector = np.array(list(true_posterior.values()))
    if not np.allclose(vector, [h.weight for h in independent.holdings], rtol=0, atol=1e-14):
        raise AssertionError("independent posterior disagreed with direct weighting")
    return (independent, np.array(list(true_prior.values())), vector,
            np.array(list(observed.values())))


def read_prior(trace, holdings, case):
    raw, solved, node, mapped = trace.pre_bet
    targets, rows = zip(*((target, solved.average[node.index][i])
                          for i, (kind, target) in enumerate(node.actions)
                          if kind in ("bet", "all_in")), strict=True)
    combo_ids = np.array([combo_index(h.combo) for h in holdings])
    index = {int(combo): i for i, combo in enumerate(solved.combos[node.player])}
    columns = np.array([index.get(combo, -1) for combo in combo_ids])
    present = columns >= 0
    full = normalize(raw[combo_ids])
    incoming = normalize(full * present)
    bet_likelihoods = np.zeros((len(rows), len(holdings)))
    bet_likelihoods[:, present] = np.asarray(rows)[:, columns[present]]
    mapped_likelihood = np.zeros(len(holdings))
    mapped_likelihood[present] = solved.average[node.index][mapped, columns[present]]
    # A pure audit at the actual decision: the first opening likelihood must
    # be applied once. The final re-solve can then remove more support.
    observed_kind, observed_size = case.observed
    if map_action(solved.tree, node.index, observed_kind, observed_size) != mapped:
        raise AssertionError("observed wager and reported mapping differ")
    return full, incoming, targets, bet_likelihoods, mapped_likelihood, node.labels[mapped]


def tv(a, b):
    return float(abs(a - b).sum() / 2)


def range_metrics(weights, truth, outcomes, classes):
    delta = weights - truth
    return {
        "tv": tv(weights, truth),
        # Expected multiclass Brier minus irreducible outcome variance.
        "brier_excess": float(delta @ delta),
        "equity": float(weights @ outcomes),
        "equity_error": float((weights - truth) @ outcomes),
        "composition": [float(weights[classes == i].sum()) for i in range(3)],
        "effective_combos": float(1 / (weights @ weights)),
        "truth_mass_outside_support": float(truth[weights == 0].sum()),
    }


def evaluate(case, profile_name, stream, hands, profile):
    start = perf_counter()
    bot = PreBetTrace(917)
    node, ds, advice = bot.trace(case.spot(), profile)
    live_seconds = perf_counter() - start
    keys = check_menu(bot, node, ds, advice)
    state = reference(case, node)
    if state.pot != case.pot + case.bet or state.villain_commit != case.bet:
        raise AssertionError("replay wager/pot differs from stimulus")
    tree = bot.river.tree
    known = ExactRiverEV(case.hero, case.board, lambda *_: 1)
    holdings = known.holdings
    if len(holdings) != 990 or any(set(h.combo) & set(case.hero + case.board) for h in holdings):
        raise AssertionError("illegal holding")
    baseline, _, production, hero_policy, live_ev = modeled_continuation(bot, node, holdings)
    full, prior, targets, likelihoods, mapped, mapped_label = read_prior(bot, holdings, case)
    stat = profile.snapshot.street_statistics["river"]["bet"]
    (candidate, relative, confidence), performance = measure_candidate(
        lambda: bet_update(prior, targets, likelihoods, case.bet, stat.occurrences))
    after_mapped = normalize(prior * mapped)
    # The solver only re-prunes by removing entries; it does not otherwise
    # alter the conditioned villain reach at this decision.
    if not np.allclose(baseline, normalize(after_mapped * (baseline > 0)), rtol=0, atol=1e-12):
        raise AssertionError("observed wager reach differs from one Bayes update and pruning")
    prod_values = payoff_values(tree, node, holdings, baseline, production, hero_policy)
    parity = float(abs(prod_values - live_ev).max())
    if parity > .003:
        raise AssertionError(f"live EV discrepancy: {parity} chips")
    classes = np.array([strength(h.rank) for h in holdings])
    outcomes = np.array([(h.result + 1) / 2 for h in holdings])
    earlier = {h.combo: tuple(RANKER.score(list(h.combo), list(case.board[:n])) for n in (3, 4))
               for h in holdings}
    replies = reply_nodes(tree, node)
    rows = []
    for opponent in (profile_name, MISMATCH[profile_name]):
        style = STYLES[opponent]
        exact, true_prior, truth, true_likelihood = reference_ranges(case, style, holdings, earlier)
        fixed_oracle = {reply.index: oracle_response(reply, holdings, style, False) for reply in replies}
        exact_evs = exact_values(exact, state, keys, style.call_probability)
        audited = payoff_values(tree, node, holdings, truth, fixed_oracle, hero_policy) / BIG_BLIND
        if not np.allclose(audited, list(exact_evs.values()), rtol=0, atol=1e-10):
            raise AssertionError("reference action values disagree with independent tree traversal")
        best = max(exact_evs.values())
        ranges = dict(zip(ARMS, (baseline, candidate, truth), strict=True))
        vectors = {
            **ranges, "production_prior": prior, "unpruned_prior": full, "true_prior": true_prior,
            "mapped_before_reprune": after_mapped,
            "estimated_prior_true_likelihood": normalize(prior * true_likelihood),
            "true_prior_candidate_likelihood": normalize(true_prior * relative),
        }
        metrics = {name: range_metrics(w, true_prior if name.endswith("_prior") else truth,
                                       outcomes, classes) for name, w in vectors.items()}
        settings = {}
        for setting, responses in zip(SETTINGS, (fixed_oracle, production), strict=True):
            policies = {}
            for arm, weights in ranges.items():
                if (weights < 0).any() or not np.isclose(weights.sum(), 1, rtol=0, atol=1e-12):
                    raise AssertionError("invalid posterior mass")
                values = payoff_values(tree, node, holdings, weights, responses, hero_policy)
                mix = fixed_value_mix(values, bot.iterations["river"])
                if not np.isfinite(values).all() or (mix < 0).any() or not np.isclose(mix.sum(), 1, atol=1e-12, rtol=0):
                    raise AssertionError("invalid decision values or frequencies")
                mix_by_key = dict(zip(keys, mix.tolist(), strict=True))
                ev = weighted_ev(mix_by_key, exact_evs)
                policies[arm] = {
                    "ev_bb": ev, "regret_bb": best - ev,
                    "modal": max(mix_by_key, key=mix_by_key.get), "mix": mix_by_key,
                    "modeled_ev_bb": dict(zip(keys, (values / BIG_BLIND).tolist(), strict=True)),
                    "replies": {keys[node.children.index(reply.index)]:
                                response_means(reply.actions, responses[reply.index] @ weights)
                                for reply in replies},
                }
            settings[setting] = policies
        rows.append({
            "case": asdict(case), "observed": case.observed, "pre_bet_pot": case.pot,
            "pre_bet_spr": case.behind / case.pot, "mapped": mapped_label,
            "on_grid": (f"bet_{case.bet}" if case.fraction else "all_in") == mapped_label,
            "board_paired": len({c[0] for c in case.board}) < 5,
            "board_three_suited": max(sum(c[1] == suit for c in case.board) for suit in "cdhs") >= 3,
            "opponent": opponent, "profile": profile_name, "matched": profile_name == opponent,
            "stream": stream, "hands": hands, "bet_opportunities": stat.opportunities,
            "bet_occurrences": stat.occurrences, "size_confidence": confidence,
            "range": metrics, "decision": settings, "exact_ev_bb": exact_evs, "live_advice": advice,
            "solver_ev_max_error_chips": parity, "solver_fallbacks": bot.fallback_count,
            "performance": {**performance, "live_seconds": live_seconds},
            "_vectors": (tuple(h.combo for h in holdings), vectors),
        })
    return rows


def diff(row, setting, arm="candidate"):
    policies = row["decision"][setting]
    return policies[arm]["ev_bb"] - policies["baseline"]["ev_bb"]


def interval(rows, setting):
    # Conditional inference over the board panel, holding the independent
    # profile streams fixed. All seats, styles and prefixes travel with a board.
    grouped = {}
    for row in rows:
        grouped.setdefault(row["case"]["index"], []).append(diff(row, setting))
    block_means = np.array([mean(v) for v in grouped.values()])
    indices = np.random.default_rng(3349).integers(len(block_means), size=(10000, len(block_means)))
    return np.quantile(block_means[indices].mean(axis=1), [.025, .975]).tolist()


def policy_summary(rows, setting):
    stats = {}
    for arm in ARMS:
        estimates = [r["decision"][setting][arm] for r in rows]
        deltas = [diff(r, setting, arm) for r in rows]
        labels = ("fold", "call", "raise", "all_in")
        stats[arm] = {
            "ev_bb": mean(a["ev_bb"] for a in estimates),
            "regret_bb": mean(a["regret_bb"] for a in estimates),
            "delta_bb": mean(deltas), "worst_delta_bb": min(deltas),
            "harm": sum(d < -1e-6 for d in deltas),
            "practical_harm": sum(d < -.01 for d in deltas),
            "harm_cost_bb": -fsum(d for d in deltas if d < -1e-6),
            "mix": {k: mean(fsum(v for raw, v in a["mix"].items() if raw.split("_")[0] == k
                                  or raw == k) for a in estimates) for k in labels},
            "modal_switches": sum(a["modal"] != r["decision"][setting]["baseline"]["modal"]
                                  for a, r in zip(estimates, rows, strict=True)),
        }
    return stats


def summarize(rows):
    range_summary = {}
    for name in rows[0]["range"]:
        values = [r["range"][name] for r in rows]
        range_summary[name] = {
            **{field: mean(v[field] for v in values) for field in
               ("tv", "brier_excess", "equity", "effective_combos", "truth_mass_outside_support")},
            "equity_mae": mean(abs(v["equity_error"]) for v in values),
            "composition": [mean(v["composition"][i] for v in values) for i in range(3)],
        }
    return {"rows": len(rows), "range": range_summary,
            "settings": {setting: policy_summary(rows, setting) for setting in SETTINGS},
            "size_confidence": mean(r["size_confidence"] for r in rows),
            "bet_occurrences": mean(r["bet_occurrences"] for r in rows),
            "median_ms": median(r["performance"]["seconds"] for r in rows) * 1000,
            "peak_bytes": max(r["performance"]["traced_peak_bytes"] for r in rows),
            "live_median_ms": median(r["performance"]["live_seconds"] for r in rows) * 1000}


def gate(primary, intervals, opponents, mismatch):
    prod = primary["settings"]["production_response"]["candidate"]
    oracle = primary["settings"]["response_oracle"]["candidate"]
    a, b = (primary["range"][arm] for arm in ARMS[:2])
    checks = {
        "production_gain_at_least_0.05_bb": prod["delta_bb"] >= .05,
        "production_interval_positive": intervals["production_response"][0] > 0,
        "oracle_response_gain_at_least_0.02_bb": oracle["delta_bb"] >= .02,
        "each_opponent_at_least_minus_0.03_bb": all(
            group["settings"][s]["candidate"]["delta_bb"] >= -.03
            for group in opponents.values() for s in SETTINGS),
        "worst_loss_at_most_0.50_bb": min(prod["worst_delta_bb"], oracle["worst_delta_bb"]) >= -.50,
        "practical_harm_at_most_10_percent": max(prod["practical_harm"], oracle["practical_harm"]) / primary["rows"] <= .10,
        "mismatch_production_mean_at_least_minus_0.05_bb":
            mismatch["settings"]["production_response"]["candidate"]["delta_bb"] >= -.05,
        "tv_improves_0.01_and_scores_do_not_regress":
            a["tv"] - b["tv"] >= .01 and b["brier_excess"] <= a["brier_excess"]
            and b["equity_mae"] <= a["equity_mae"],
        "under_5ms_and_256kib": primary["median_ms"] < 5 and primary["peak_bytes"] < 256 * 1024,
    }
    return {"checks": checks, "pass": all(checks.values())}


def run(panel):
    seed, count, streams = SPLITS[panel]
    profiles = {(name, stream): train(name, stream, PROFILES) for name, stream in product(STYLES, streams)}
    rows = []
    for orientation, stream in enumerate(streams):
        for case, name, hands in product(cases(seed, count, orientation), STYLES, PROFILES):
            rows.extend(evaluate(case, name, stream, hands, profiles[name, stream][hands]))
    primary = [row for row in rows if row["matched"]]
    mismatch = [row for row in rows if not row["matched"]]
    match_summary = summarize(primary)
    mismatch_summary = summarize(mismatch)
    opponents = {k: summarize([r for r in primary if r["opponent"] == k]) for k in STYLES}
    strata = {
        key: summarize(group) for key, group in (
            *((f"profile_{n}", [r for r in primary if r["hands"] == n]) for n in PROFILES),
            *((f"depth_{n}", [r for r in primary if r["case"]["depth"] == n]) for n in (9, 15, 30)),
            *((f"size_{n}", [r for r in primary if r["case"]["fraction"] == n]) for n in (*SIZES, None)),
            *((seat, [r for r in primary if r["case"]["seat"] == seat]) for seat in ("button", "big_blind")),
            ("paired_board", [r for r in primary if r["board_paired"]]),
            ("unpaired_board", [r for r in primary if not r["board_paired"]]),
            ("three_suited_board", [r for r in primary if r["board_three_suited"]]),
            ("under_1_spr", [r for r in primary if r["pre_bet_spr"] < 1]),
        ) if group
    }
    extremes = {}
    for setting in SETTINGS:
        ordered = sorted(primary, key=lambda r: diff(r, setting))
        extremes[setting] = {}
        for key, row in (("worst", ordered[0]), ("best", ordered[-1])):
            combos, vectors = row["_vectors"]
            extremes[setting][key] = {**{k: v for k, v in row.items() if k != "_vectors"},
                                      "combos": combos,
                                      "weights": {name: v.tolist() for name, v in vectors.items()}}
    for row in rows:
        del row["_vectors"]
    result = {"panel": panel, "primary": match_summary, "mismatch": mismatch_summary,
              "opponents": opponents, "strata": strata, "extremes": extremes, "rows": rows}
    if panel == "holdout":
        intervals = {s: interval(primary, s) for s in SETTINGS}
        result.update(paired_ci95=intervals, gate=gate(match_summary, intervals, opponents, mismatch_summary))
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=SPLITS)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    start = perf_counter()
    result = run(args.panel)
    result["wall_seconds"] = perf_counter() - start
    result["process_peak_resident_bytes"] = peak_resident_bytes()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, allow_nan=False, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
