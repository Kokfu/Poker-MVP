"""Phase 4Q isolated likelihood calibration, exact EV and historical replay."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
import json
from math import fsum
from pathlib import Path
from random import Random
from statistics import mean, median
from time import perf_counter

import numpy as np

from research.holdem import phase_4p as old
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, peak_resident_bytes, train
from research.holdem.phase_4l import exact_values, modeled_continuation, normalize, payoff_values, reference
from research.holdem.phase_4m import check_menu, measure_candidate, oracle_response, reply_nodes
from research.holdem.phase_4o import Case, LINES, PriorTrace, action_row, score_policies
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import (
    CLOSE, HALF, POT, LABELS, Opening, calibrate, empty_counts, hand_group,
)
from research.holdem.river_wager_reference import PROFILES, counts, law
from solver.bot import replay_hand
from solver.combos import card_mask, combo_index


PANELS = {"development": (437_201, 4, (121,)), "holdout": (437_202, 12, (131, 132, 133))}
SETTINGS = {"A": (False, False), "B": (False, True), "C": (True, False), "D": (True, True)}
ARMS = ("baseline", "candidate", "oracle")
HISTORICAL = (
    (5, 111, "tight_passive"), (5, 111, "tight_aggressive"),
    (6, 111, "tight_passive"), (6, 111, "loose_passive"), (6, 112, "tight_passive"),
    (0, 112, "tight_aggressive"), (5, 112, "loose_aggressive"),
    (2, 112, "tight_aggressive"), (2, 111, "tight_passive"), (1, 111, "tight_aggressive"),
)


@dataclass(frozen=True)
class WagerCase(old.CalibrationCase):
    pot_wager: bool

    @property
    def bet(self):
        return self.behind if self.shove else self.pot if self.pot_wager else self.pot // 2


def cases(seed, count, orientation):
    for case in old.cases(seed, count, orientation):
        opening = Opening(case.pot, case.behind, case.behind, BIG_BLIND, case.line[1] != "check")
        pick = (case.index + orientation) % 4
        want = CLOSE if pick in (0, 3) else POT if pick == 2 else HALF
        closing = want == CLOSE or opening.targets[want] is None
        yield WagerCase(**{**asdict(case), "shove": closing}, pot_wager=want == POT)


def population_counts():
    table = empty_counts()
    for index, style in enumerate(STYLES.values()):
        table += counts(style, 74_100_000 + index, (2048,))[2048]
    return table


def profile_counts(style, stream):
    return counts(STYLES[style], 75_100_000 + 100 * stream + tuple(STYLES).index(style), PROFILES)


def extract_opening(bot, replay, holdings):
    weights, solved, onode, mapped = bot.pre_bet
    step = replay.steps[-1]
    before = step.before
    v = step.player
    opening = Opening(before.pot, before.stack[v], before.stack[1 - v], before.last_full_raise,
                      any(p.street == "turn" and p.kind in ("bet", "raise", "all_in") for p in replay.steps))
    if before.highest or onode.player != v:
        raise AssertionError("not an unopened Villain river decision")
    combos = np.array([combo_index(h.combo) for h in holdings])
    donors = solved.combos[v]
    compatible = card_mask(tuple(bot.decision_state.hole_cards) + tuple(bot.decision_state.board_cards))
    incoming = normalize(weights[combos] * np.isin(combos, donors))
    production = np.zeros((4, len(holdings)))
    observed, exhausts, closes = opening.action(step.target)
    for index, (kind, target) in enumerate(onode.actions):
        category = 0 if kind == "check" else opening.targets.index(target)
        production[category] = action_row(weights, donors, solved.average[onode.index][index], compatible, combos)
        if index == mapped and category != observed:
            raise AssertionError("baseline observation did not map to its exact target")
    if not np.allclose(production.sum(axis=0), 1, atol=1e-12, rtol=0):
        raise AssertionError("production action law not normalized")
    return opening, incoming, production, observed, exhausts, closes


def calibration_metrics(laws, exact_prior, groups, held_out):
    reference_law = laws["oracle"]
    group_totals = exact_prior @ np.eye(6)[groups]
    out = {}
    for arm, predicted in laws.items():
        errors = predicted - reference_law
        event_mass = reference_law @ exact_prior
        eps = 1e-10
        out[arm] = {
            "log_loss": float((-np.log(predicted.clip(eps)) * reference_law).sum(axis=0) @ exact_prior),
            "brier": float(((errors ** 2).sum(axis=0) + 1 - (reference_law ** 2).sum(axis=0)) @ exact_prior),
            "sample_log_loss": float(-np.log(max(eps, predicted[held_out]))),
            "by_action": [
                {"expected": float(event_mass[i]), "predicted": float(predicted[i] @ exact_prior),
                 "mae": float(abs(errors[i]) @ exact_prior),
                 "brier": float((errors[i] ** 2 + reference_law[i] * (1 - reference_law[i])) @ exact_prior),
                 "supported": bool(np.any(reference_law[i] > 0))}
                for i in range(4)
            ],
            "by_strength": [
                {"mass": float(group_totals[2*i] + group_totals[2*i+1]), "closing_bias_mass":
                 float(errors[CLOSE, (groups // 2) == i] @ exact_prior[(groups // 2) == i]),
                 "closing_mae_mass": float(abs(errors[CLOSE, (groups // 2) == i]) @ exact_prior[(groups // 2) == i])}
                for i in range(3)
            ],
        }
    return out


def evaluate(case, name, stream, hands, profile, table, population, historical=False, archive=False):
    start = perf_counter()
    bot = PriorTrace()
    spot = case.spot()
    node, ds, advice = bot.trace(spot, profile)
    live_seconds = perf_counter() - start
    keys = check_menu(bot, node, ds, advice)
    state = reference(case, node)
    holdings = ExactRiverEV(case.hero, case.board, lambda *_: 1).holdings
    pairs = [h.combo for h in holdings]
    replay = replay_hand(ds)
    opening, prior, base, observed, exhausts, closes = extract_opening(bot, replay, holdings)
    if closes and reply_nodes(bot.river.tree, node):
        raise AssertionError("closing wager offered a further raise")
    if (state.pot, state.villain_commit) != (opening.pot + case.bet, case.bet):
        raise AssertionError("wrong replay geometry")
    villain = 1 - node.player
    steps = [step for step in replay.steps if step.player == villain]
    pre_history = tuple(old.observations(replay, villain, case.seat == "button"))
    style = STYLES[name]
    if archive:
        exact_prior, archived_truth, archived_exact, archived_likelihood = old.exact_ranges(
            case, pre_history, steps, style, holdings, historical
        )
    else:
        exact_prior = old.reference_weights(pairs, pre_history, case.depth, style)
        for step in steps[:-1]:
            if step.street == "preflop":
                continue
            board = list(case.board[:3 if step.street == "flop" else 4])
            exact_prior *= [old.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                            for pair in pairs]
        exact_prior = normalize(exact_prior)
    groups = np.array([hand_group(h.combo, case.board, h.rank) for h in holdings])
    candidate, perf = measure_candidate(lambda: calibrate(base, opening, groups, population, table))
    if archive:
        likelihoods = {"baseline": base[observed], "candidate": candidate[observed], "oracle": archived_likelihood}
        truth, exact = archived_truth, archived_exact
        scores = None
    else:
        truth_law = np.array([law(opening, int(group), style) for group in groups]).T
        laws = dict(zip(ARMS, (base, candidate, truth_law), strict=True))
        legal = np.array([target is not None for target in opening.targets])
        for probabilities in laws.values():
            if ((probabilities < 0).any() or (probabilities[~legal] != 0).any()
                    or not np.allclose(probabilities.sum(axis=0), 1, atol=1e-12, rtol=0)):
                raise AssertionError("invalid legal action law")
        likelihoods = {arm: probabilities[observed] for arm, probabilities in laws.items()}
        prior_by_pair = dict(zip(pairs, exact_prior, strict=True))
        oracle_by_pair = dict(zip(pairs, likelihoods["oracle"], strict=True))
        truth = np.array(tuple(posterior(case.hero, case.board, prior_by_pair.__getitem__,
                                         oracle_by_pair.__getitem__).values()))
        exact = ExactRiverEV(case.hero, case.board, lambda pair, _: prior_by_pair[pair] * oracle_by_pair[pair])
        if not np.allclose(truth, [h.weight for h in exact.holdings], atol=1e-14, rtol=0):
            raise AssertionError("Bayesian and direct enumerators disagree")
        rng = Random(76_100_000 + 100_000 * stream + 100 * case.index + tuple(STYLES).index(name))
        sampled_hand = rng.choices(range(len(holdings)), weights=exact_prior)[0]
        sampled_action = rng.choices(range(4), truth_law[:, sampled_hand])[0]
        scores = calibration_metrics(laws, exact_prior, groups, (sampled_action, sampled_hand))

    actual, _, production, hero_policy, live_values = modeled_continuation(bot, node, holdings)
    if not np.allclose(normalize(prior * likelihoods["baseline"]), actual, atol=1e-12, rtol=0):
        raise AssertionError("baseline differs from the final live posterior")
    tree = bot.river.tree
    parity = float(abs(payoff_values(tree, node, holdings, actual, production, hero_policy) - live_values).max())
    if parity > .003 or bot.fallback_count:
        raise AssertionError(f"value parity or fallback: {parity}")
    true_values = exact_values(exact, state, keys, style.call_probability)
    true_responses = {reply.index: oracle_response(reply, holdings, style, False) for reply in reply_nodes(tree, node)}
    audited = payoff_values(tree, node, holdings, truth, true_responses, hero_policy) / BIG_BLIND
    if not np.allclose(audited, list(true_values.values()), atol=1e-10, rtol=0):
        raise AssertionError("exact EV and independent payoff traversal disagree")

    outcome = np.array([(h.result + 1) / 2 for h in holdings])
    posts = {kind: {arm: normalize(weights * likelihood) for arm, likelihood in likelihoods.items()}
             for kind, weights in (("production", prior), ("true", exact_prior))}
    decisions = {setting: score_policies(bot, node, holdings, keys, posts["true" if true_prior else "production"],
                 true_responses if true_reply else production, hero_policy, true_values)
                 for setting, (true_prior, true_reply) in SETTINGS.items()}
    row = {
        "case": asdict(case), "opponent": name, "stream": stream, "hands": hands,
        "opening": asdict(opening), "spr": opening.spr, "spr_band": opening.cell[0],
        "observed": (*case.observed, LABELS[observed]), "wager_over_pot": case.bet / opening.pot,
        "bettor_all_in": exhausts, "closing": closes, "history": [asdict(action) for action in spot.actions],
        "decision": decisions, "exact_ev_bb": true_values, "live_advice": advice,
        "live_mix": dict(zip(keys, bot.probabilities.tolist(), strict=True)),
        "parity_chips": parity, "fallbacks": bot.fallback_count, "calibration": scores,
        "posterior": {kind: {arm: {"equity": float(weights @ outcome), "tv": old.tv(weights, truth)}
                             for arm, weights in policies.items()} for kind, policies in posts.items()},
        "performance": {**perf, "live_seconds": live_seconds},
    }
    if archive or min(old.delta(row, s) for s in SETTINGS) <= -.50:
        row["evidence"] = {
            "combos": pairs, "incoming": {"production": prior.tolist(), "true": exact_prior.tolist()},
            "posterior": {kind: {arm: weights.tolist() for arm, weights in policies.items()}
                          for kind, policies in posts.items()},
            "true_posterior": truth.tolist(), "observed_likelihood": {a: v.tolist() for a, v in likelihoods.items()},
            "replies": {"production": {str(k): v.tolist() for k, v in production.items()},
                        "reference": {str(k): v.tolist() for k, v in true_responses.items()}},
            "reply_menu": {str(reply.index): reply.actions for reply in reply_nodes(tree, node)},
        }
    return row


def decision_summary(rows, setting, arm):
    return {**old.decision_summary(rows, setting, arm), "max_regret_bb":
            max(r["decision"][setting][arm]["regret_bb"] for r in rows)}


def summarize(rows):
    calibration = {}
    for arm in ARMS:
        values = [r["calibration"][arm] for r in rows]
        calibration[arm] = {key: mean(v[key] for v in values) for key in ("log_loss", "brier", "sample_log_loss")}
        for i, label in enumerate(LABELS):
            items = [v["by_action"][i] for v in values if v["by_action"][i]["supported"]]
            if items:
                calibration[arm][label] = {key: mean(v[key] for v in items)
                                          for key in ("expected", "predicted", "mae", "brier")}
        calibration[arm]["strata_closing"] = [
            {key.removesuffix("_mass"): (total / mass if mass else None)
             for key in ("closing_bias_mass", "closing_mae_mass")
             for total in [fsum(v["by_strength"][i][key] for v in values)]}
            for i in range(3) for mass in [fsum(v["by_strength"][i]["mass"] for v in values)]
        ]
    return {"rows": len(rows), "calibration": calibration,
            "decisions": {s: {a: decision_summary(rows, s, a) for a in ARMS} for s in SETTINGS},
            "max_live_parity_chips": max(r["parity_chips"] for r in rows),
            "performance": {"median_ms": 1000 * median(r["performance"]["seconds"] for r in rows),
                            "peak_bytes": max(r["performance"]["traced_peak_bytes"] for r in rows),
                            "median_live_ms": 1000 * median(r["performance"]["live_seconds"] for r in rows)}}


def interval(rows, setting, arm):
    """Crossed resampling: keep all four fixed styles inside each board/stream cell."""
    boards = sorted({r["case"]["index"] for r in rows})
    streams = sorted({r["stream"] for r in rows})
    matrix = {(b, s): mean(old.delta(r, setting, arm) for r in rows
                           if (r["case"]["index"], r["stream"]) == (b, s))
              for b in boards for s in streams}
    rng = Random(43703)
    draws = []
    for _ in range(10_000):
        b_draw = rng.choices(boards, k=len(boards))
        s_draw = rng.choices(streams, k=len(streams))
        draws.append(mean(matrix[b, s] for b in b_draw for s in s_draw))
    draws.sort()
    return draws[249], draws[9749]


def run_historical(population):
    specs = [(Case(11, ("Js", "3c"), ("2d", "Ah", "Jh", "2h", "Kh"), 30, 300,
                   "big_blind", LINES[2], True), 91, "loose_aggressive", 30, True)]
    for index, stream, name in HISTORICAL:
        orientation = stream - 111
        case = list(old.cases(436_102, 12, orientation))[index]
        hands = old.PROFILES[(index // 4 + index + orientation) % len(old.PROFILES)]
        specs.append((case, stream, name, hands, False))
    results = []
    for case, stream, name, hands, original in specs:
        profile = train(name, stream, (hands,))[hands]
        phase4p = old.evaluate(case, name, stream, hands, profile,
                               old.sample_counts(name, 103 if original else stream)[hands], historical=original)
        row = evaluate(case, name, stream, hands, profile, profile_counts(name, stream)[hands],
                       population, historical=original, archive=True)
        row["phase_4p_replay"] = phase4p
        results.append(row)
    if abs(old.delta(results[0]["phase_4p_replay"], "A", "incoming_oracle") + 18.72031252) > .001:
        raise AssertionError("original Phase 4P loss no longer reproduces")
    return {"panel": "historical", "rows": results}


def run(panel):
    population = population_counts()
    if panel == "historical":
        return run_historical(population)
    seed, number, streams = PANELS[panel]
    rows = []
    for orientation, stream in enumerate(streams):
        for name in STYLES:
            profiles = train(name, stream, PROFILES[1:])
            snapshots = profile_counts(name, stream)
            for case in cases(seed, number, orientation):
                hands = PROFILES[(case.index // 4 + case.index + orientation) % len(PROFILES)]
                rows.append(evaluate(case, name, stream, hands, profiles.get(hands), snapshots[hands], population))
            print(f"{panel}: stream {stream}, {name}, {len(rows)} rows", flush=True)
    groups = {key: {str(value): summarize([r for r in rows if fn(r) == value])
                    for value in sorted({fn(r) for r in rows})}
              for key, fn in {
                  "opponent": lambda r: r["opponent"], "profile": lambda r: r["hands"],
                  "depth": lambda r: r["case"]["depth"], "spr": lambda r: r["spr_band"],
                  "wager": lambda r: r["observed"][2], "stream": lambda r: r["stream"],
                  "turn_pressure": lambda r: r["opening"]["turn_pressure"],
              }.items()}
    summary = summarize(rows)
    result = {"panel": panel, "summary": summary, "strata": groups, "rows": rows}
    if panel == "holdout":
        intervals = {s: {a: interval(rows, s, a) for a in ARMS[1:]} for s in SETTINGS}
        primary = summary["decisions"]["A"]["candidate"]
        checks = {
            "mean_ge_0.05_bb": primary["delta_bb"] >= .05,
            "paired_lower_gt_zero": intervals["A"]["candidate"][0] > 0,
            "worst_ge_minus_0.50_bb": primary["worst_delta_bb"] >= -.50,
            "harm_rate_le_10_percent": primary["harm_above_0.01"] <= .10 * len(rows),
            "opponent_floor_ge_minus_0.03_bb": all(
                values["decisions"]["A"]["candidate"]["delta_bb"] >= -.03 for values in groups["opponent"].values()),
            "proper_score_improves": summary["calibration"]["candidate"]["log_loss"]
                                     < summary["calibration"]["baseline"]["log_loss"],
            "median_lt_5_ms": summary["performance"]["median_ms"] < 5,
            "peak_lt_512_kib": summary["performance"]["peak_bytes"] < 512 * 1024,
            "zero_fallbacks": not any(row["fallbacks"] for row in rows),
        }
        result.update(intervals=intervals, gate={"checks": checks, "pass": all(checks.values())})
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
