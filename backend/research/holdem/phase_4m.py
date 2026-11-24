"""Offline, first-reply response calibration with fixed incoming river reach."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import product
import json
from math import fsum, isclose
from pathlib import Path
from statistics import mean, median
from time import perf_counter
import tracemalloc

import numpy as np

from coach.service import _replay
from research.holdem.phase_4k import (
    BIG_BLIND, CASES, HARM_TOLERANCE, STYLES, label, peak_resident_bytes,
    strength, to_action, train, weighted_ev,
)
from research.holdem.phase_4l import (
    HOLDOUT as CALIBRATION, Case, Disabled, Live, exact_values, fixed_value_mix,
    modeled_continuation, payoff_values, reference,
)
from research.holdem.river_ev import ExactRiverEV
from simulation.actions import Action
from simulation.decision_state import build_decision_state
from solver.bot import replay_hand
from solver.cfr import fit_frequencies
from solver.tree import POSTFLOP_MENU, StreetTree


TRAINING = (
    ("train1", "Ad Qd", "Ah 6c 5h 2s 9c", 0, 225),
    ("train2", "9c 8c", "Ts 7s 4c Qs 3d", 0, 325),
    ("train3", "Ks Js", "Kh 9c 2d 7d 5s", 0, 400),
    ("train4", "7s 7d", "7h 3c Qd 4s 8c", 150, 250),
    ("train5", "Ac Jd", "3s Qc 8h Th 6d", 275, 350),
    ("train6", "5s 4s", "9h 5c 4d Jh 2c", 350, 250),
)
HOLDOUT = (
    ("river_flush", "Ks Js", "As 8s 3s Qc 2d", 0, 225),
    ("underpair", "8c 8d", "Tc 6s 2h 4d Qs", 0, 325),
    ("missed_straight", "Jh 9h", "Ts 8c 3d 2s Kc", 0, 375),
    ("paired_top_pair", "Ac Kh", "Kd 7c 7h 4s 2d", 0, 275),
    ("bottom_pair", "Ad 4d", "Qs 8c 4h Jd 6s", 175, 250),
    ("river_set", "Td Tc", "Jh 6s 2d 4c Ts", 225, 350),
    ("king_high", "Kc Jc", "5s 8d Ah 7h 2c", 325, 300),
    ("turn_two_pair", "Qs 9d", "Qc 5d 4h 9s 6h", 425, 225),
)
DEPTHS = (9, 15, 30)
GROUPS = ("fold", "call", "raise")
COMPARISONS = ("baseline", "conditioned", "pooled", "oracle")
PRIORS = 20
LIVE_PRIOR = 32
DRAWS = 24


@dataclass(frozen=True)
class Reply:
    cost: int
    pot_before: int
    stack_at_risk: int
    raise_legal: bool
    facing_raise: bool

    @property
    def small(self):
        return self.cost <= self.pot_before

    @property
    def high_pressure(self):
        return 2 * self.cost >= self.stack_at_risk

    def report(self):
        return {
            **asdict(self), "price": "pot_or_less" if self.small else "over_pot",
            "pressure": "half_stack_or_more" if self.high_pressure else "under_half_stack",
            "price_ratio": self.cost / self.pot_before,
            "stack_ratio": self.cost / self.stack_at_risk,
            "spr": self.stack_at_risk / self.pot_before,
        }


def reply_context(node):
    state = node.state
    actor, other = node.player, 1 - node.player
    own, offered = state.commit[actor], state.commit[other]
    effective = min(own + state.stack[actor], offered + state.stack[other])
    cost = min(offered, effective) - own
    if cost <= 0:
        raise ValueError("expected a first reply facing aggression")
    # Remove the entire wager above the responder's investment, including uncallable excess.
    return Reply(cost, sum(state.base) + 2 * own, effective - own,
                 any(kind in ("raise", "all_in") for kind, _ in node.actions),
                 state.depth > 1)


def group_indices(node):
    groups = tuple(tuple(i for i, (kind, _) in enumerate(node.actions)
                         if kind == group or (group == "raise" and kind == "all_in"))
                   for group in GROUPS)
    if not groups[0] or not groups[1] or sum(map(len, groups)) != len(node.actions):
        raise AssertionError("invalid facing-wager response menu")
    return groups


class ResponseCounts:
    """Three public-context count tables, built solely from observed replies."""

    def __init__(self):
        self.cells = defaultdict(lambda: np.zeros(3, dtype=int))

    @staticmethod
    def keys(ctx):
        legal = (ctx.raise_legal,)
        price = (*legal, ctx.small)
        return legal, price, (*price, ctx.high_pressure, ctx.facing_raise)

    def observe(self, ctx, outcomes):
        if (outcomes < 0).any() or (not ctx.raise_legal and outcomes[2]):
            raise ValueError("illegal response observations")
        for key in self.keys(ctx):
            self.cells[key] += outcomes

    def target(self, ctx, live, conditioned):
        legal, *levels = self.keys(ctx)
        counts = self.cells.get(legal)
        if counts is None:
            return None
        n = int(counts.sum())
        if not n:
            return None
        estimate = counts / n
        if conditioned:
            for key in levels:
                local = self.cells.get(key)
                if local is not None:
                    estimate = (local + PRIORS * estimate) / (local.sum() + PRIORS)
        return (n * estimate + LIVE_PRIOR * live) / (n + LIVE_PRIOR)


def adjust(node, sigma, weights, counts, conditioned):
    groups = group_indices(node)
    legal_groups = [indices for indices in groups if indices]
    grouped = np.array([sigma[list(indices)].sum(axis=0) for indices in legal_groups])
    live = np.pad(grouped @ weights, (0, 3 - len(grouped)))
    target = counts.target(reply_context(node), live, conditioned)
    if target is None:
        return sigma
    fitted = fit_frequencies(grouped, weights, target[:len(grouped)], rounds=48)
    result = np.empty_like(sigma)
    for indices, original, updated in zip(legal_groups, grouped, fitted, strict=True):
        within = np.divide(sigma[list(indices)], original, where=original > 0,
                           out=np.full((len(indices), len(weights)), 1 / len(indices)))
        result[list(indices)] = within * updated
    return result


def reply_nodes(tree, root):
    return [tree.nodes[child] for (kind, _), child in zip(root.actions, root.children, strict=True)
            if kind in ("bet", "raise", "all_in") and tree.nodes[child].kind == "decision"]


def reference_probabilities(style, hand, ctx, can_shove):
    call = style.call_probability(hand.combo, hand.rank, ctx.cost, ctx.pot_before + ctx.cost)
    raise_rate = (.02, .10, .35)[strength(hand.rank)] if can_shove else 0.0
    if not ctx.small:
        raise_rate *= .5
    return ((1 - raise_rate) * (1 - call), (1 - raise_rate) * call, raise_rate)


def oracle_response(node, holdings, style, raising):
    ctx = reply_context(node)
    can_shove = raising and "all_in" in node.labels
    result = np.zeros((len(node.actions), len(holdings)))
    fold, call, raise_ = np.array([reference_probabilities(style, h, ctx, can_shove)
                                  for h in holdings]).T
    result[node.labels.index("fold")], result[node.labels.index("call")] = fold, call
    if can_shove:
        result[node.labels.index("all_in")] = raise_
    return result


def evaluator(case, spot, style):
    hero, board = tuple(spot.hero_cards), tuple(spot.board)
    return ExactRiverEV(hero, board, lambda cards, rank: style.path_likelihood(cards, board, rank, case.bet))


def train_responses(opponent, stream, raising):
    style = STYLES[opponent]
    rng = np.random.default_rng([74319, stream, list(STYLES).index(opponent), int(raising)])
    counts = ResponseCounts()
    for args in TRAINING:
        case = Case(*args)
        spot = case.spot(15)
        exact = evaluator(case, spot, style)
        weights = np.array([h.weight for h in exact.holdings])
        for depth in DEPTHS:
            status, _, engine = _replay(case.spot(depth))
            if status != "hero_to_act":
                raise AssertionError("training line did not reach the open decision")
            state = replay_hand(build_decision_state(engine, "a")).current
            tree = StreetTree(state, POSTFLOP_MENU)
            for node in reply_nodes(tree, tree.nodes[tree.root]):
                sigma = oracle_response(node, exact.holdings, style, raising)
                # Independent posterior draws followed by independent categorical replies.
                draws = rng.choice(len(weights), p=weights, size=DRAWS)
                actions = [rng.choice(len(node.actions), p=sigma[:, i]) for i in draws]
                action_counts = np.bincount(actions, minlength=len(node.actions))
                observed = np.array([action_counts[list(group)].sum() if group else 0
                                     for group in group_indices(node)])
                counts.observe(reply_context(node), observed)
    return counts


def validate_columns(matrix):
    if (matrix < 0).any() or not np.allclose(matrix.sum(axis=0), 1, rtol=0, atol=1e-10):
        raise AssertionError("invalid legal probability distribution")


def calibration(node, forecasts, oracle, weights):
    groups = group_indices(node)

    def grouped(matrix):
        validate_columns(matrix)
        return np.array([matrix[list(group)].sum(axis=0) if group else np.zeros(len(weights))
                         for group in groups])

    truth = grouped(oracle)
    marginal = truth @ weights
    output = {}
    for arm, forecast in forecasts.items():
        pred = grouped(forecast)
        overall = pred @ weights
        error = overall - marginal
        excess = float(error @ error)
        output[arm] = {
            "predicted": dict(zip(GROUPS, overall.tolist(), strict=True)),
            "absolute_error": dict(zip(GROUPS, abs(error).tolist(), strict=True)),
            "excess_brier": excess, "brier": float(1 - marginal @ marginal + excess),
            "holding_brier": float((1 - (truth ** 2).sum(axis=0) +
                                    ((pred - truth) ** 2).sum(axis=0)) @ weights),
        }
    return output


def check_menu(bot, node, ds, advice):
    keys = [label(bot._concrete_postflop(ds, act)) for act in node.actions]
    if len(set(keys)) != len(keys):
        raise AssertionError(f"duplicate concrete targets: {keys}")
    for key in keys:
        action = to_action(key)
        if action.type not in ds.legal_actions or (
            action.amount is not None and not ds.minimum_legal_target <= action.amount <= ds.maximum_legal_target
        ):
            raise AssertionError(f"illegal concrete action: {key}")
    if label(Action(advice["action"], advice["amount"])) not in keys:
        raise AssertionError("seeded recommendation left the concrete menu")
    return keys


def measure_candidate(operation):
    start = perf_counter()
    result = operation()
    seconds = perf_counter() - start
    tracemalloc.start()
    try:
        operation()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, {"seconds": seconds, "traced_peak_bytes": peak}


def score(case, depth, opponent, stream, profile, response_tables, historical=False):
    spot = case.spot(depth)
    live = Live(917)
    start = perf_counter()
    root, ds, advice = live.trace(spot, profile)
    live_seconds = perf_counter() - start
    keys = check_menu(live, root, ds, advice)
    tree = live.river.tree
    style = STYLES[opponent]
    exact = evaluator(case, spot, style)
    state = reference(case, root)
    weights, _, baseline, hero_policy, live_ev = modeled_continuation(live, root, exact.holdings)
    weights.setflags(write=False)
    true_weights = np.array([h.weight for h in exact.holdings])
    first_replies = reply_nodes(tree, root)

    def ev(response, reach=weights):
        return payoff_values(tree, root, exact.holdings, reach, response, hero_policy)

    baseline_ev = ev(baseline)
    parity = float(abs(baseline_ev - live_ev).max())
    if not np.isfinite(parity) or parity > .002:
        raise AssertionError(f"production EV audit discrepancy: {parity} chips")
    disabled = None
    if historical:
        off = Disabled(917)
        off_root, off_ds, off_advice = off.trace(spot)
        off_keys = check_menu(off, off_root, off_ds, off_advice)
        if off_keys != keys:
            raise AssertionError("historical disabled menu diverged")
        disabled = dict(zip(keys, off.probabilities.tolist(), strict=True))

    rows = []
    for raising, counts in response_tables.items():
        def predict(conditioned):
            forecast = dict(baseline)
            for node in first_replies:
                forecast[node.index] = adjust(node, baseline[node.index], weights, counts, conditioned)
            values = ev(forecast)
            mix = fixed_value_mix(values, live.iterations["river"])
            return forecast, values, mix

        (conditioned, conditioned_ev, conditioned_mix), performance = measure_candidate(lambda: predict(True))
        pooled, pooled_ev, pooled_mix = predict(False)
        oracle = dict(baseline)
        for node in first_replies:
            oracle[node.index] = oracle_response(node, exact.holdings, style, raising)
        true_ev = ev(oracle, true_weights)
        if not raising:
            independent = exact_values(exact, state, keys, style.call_probability)
            if not np.allclose(true_ev / BIG_BLIND, list(independent.values()), rtol=0, atol=1e-10):
                raise AssertionError("reference payoff engine disagrees with Phase 4J")
        oracle_ev = ev(oracle)
        true_evs = dict(zip(keys, (true_ev / BIG_BLIND).tolist(), strict=True))
        best = max(true_evs.values())

        def arm(values, probabilities):
            validate_columns(probabilities)
            if not np.isfinite(values).all():
                raise AssertionError("nonfinite action EV")
            mix = dict(zip(keys, probabilities.tolist(), strict=True))
            action_evs = dict(zip(keys, (values / BIG_BLIND).tolist(), strict=True))
            exact_ev = weighted_ev(mix, true_evs)
            return {"ev_bb": exact_ev, "regret_bb": best - exact_ev, "mix": mix,
                    "modeled_ev_bb": action_evs,
                    "mae_bb": mean(abs(action_evs[k] - true_evs[k]) for k in keys),
                    "modal_action": max(mix, key=mix.get)}

        models = dict(zip(COMPARISONS, (baseline, conditioned, pooled, oracle), strict=True))
        first_by_index = {node.index: node for node in first_replies}
        replies = {}
        for key, child in zip(keys, root.children, strict=True):
            if child not in first_by_index:
                continue
            node = first_by_index[child]
            ctx = reply_context(node)
            forecasts = {name: matrices[child] for name, matrices in models.items()}
            actual = oracle[child]
            replies[key] = {"context": ctx.report(), "legal_labels": node.labels,
                            "sample_counts": [counts.cells.get(k, np.zeros(3, dtype=int)).tolist()
                                              for k in counts.keys(ctx)],
                            "metrics": calibration(node, forecasts, actual, weights),
                            "true_posterior_response": calibration(node, {"oracle": actual}, actual, true_weights)
                            ["oracle"]["predicted"]}
        arms = {
            "baseline": arm(baseline_ev, fixed_value_mix(baseline_ev, live.iterations["river"])),
            "conditioned": arm(conditioned_ev, conditioned_mix),
            "pooled": arm(pooled_ev, pooled_mix),
            "oracle": arm(oracle_ev, fixed_value_mix(oracle_ev, live.iterations["river"])),
            "live": arm(baseline_ev, live.probabilities),
        }
        if disabled is not None:
            original_loss = arms["live"]["ev_bb"] - weighted_ev(disabled, true_evs)
            if not isclose(original_loss, -1.179285, abs_tol=1e-6):
                raise AssertionError(f"historical loss failed to reproduce: {original_loss}")
        rows.append({
            "case": case.name, "opponent": opponent, "depth": depth, "stream": stream,
            "raising": raising, "state": asdict(state), "hero": spot.hero_cards, "board": spot.board,
            "true_ev_bb": true_evs, "arms": arms, "replies": replies, "seeded_live_advice": advice,
            "disabled": None if disabled is None else {
                "mix": disabled, "ev_bb": weighted_ev(disabled, true_evs), "live_loss_bb": original_loss,
            },
            "payoff_error_chips": parity, "live_seconds": live_seconds, "performance": performance,
        })
    return rows


def paired(rows, arm="conditioned", control="baseline"):
    return [row["arms"][arm]["ev_bb"] - row["arms"][control]["ev_bb"] for row in rows]


def policy_summary(rows):
    output = {}
    for name in (*COMPARISONS, "live"):
        arms = [row["arms"][name] for row in rows]
        deltas = paired(rows, name)
        harms = [delta for delta in deltas if delta < -HARM_TOLERANCE]
        kinds = ("check", "fold", "call", "bet", "raise", "all_in")
        output[name] = {
            "mean_ev_bb": mean(arm["ev_bb"] for arm in arms), "delta_bb": mean(deltas),
            "mean_regret_bb": mean(arm["regret_bb"] for arm in arms),
            "mean_action_mae_bb": mean(arm["mae_bb"] for arm in arms),
            "harm_count": len(harms), "material_harm_count": sum(d < -.01 for d in deltas),
            "harm_cost_bb": -fsum(harms), "worst_delta_bb": min(deltas),
            "action_mass": {kind: mean(fsum(m for k, m in arm["mix"].items() if to_action(k).type == kind)
                                       for arm in arms) for kind in kinds},
        }
    return output


def calibration_summary(rows, field=None):
    buckets = defaultdict(list)
    for row in rows:
        for reply in row["replies"].values():
            key = "all" if field is None else str(row[field] if field in row else reply["context"][field])
            buckets[key].append(reply["metrics"])
    return {
        key: {"n": len(metrics), **{
            arm: {**{metric: mean(reply[arm][metric] for reply in metrics)
                      for metric in ("brier", "excess_brier", "holding_brier")},
                  "absolute_error": {kind: mean(reply[arm]["absolute_error"][kind] for reply in metrics)
                                     for kind in GROUPS}}
            for arm in COMPARISONS}}
        for key, metrics in sorted(buckets.items())
    }


def interval(rows, control="baseline"):
    blocks = defaultdict(list)
    for row, delta in zip(rows, paired(rows, control=control), strict=True):
        blocks[row["case"]].append(delta)
    board_deltas = np.array([mean(block) for block in blocks.values()])
    rng = np.random.default_rng(132837)
    draws = rng.choice(board_deltas, size=(10000, len(board_deltas)), replace=True).mean(axis=1)
    return np.percentile(draws, [2.5, 97.5]).tolist()


def panel_summary(rows, holdout):
    policy = policy_summary(rows)
    by_depth = {depth: policy_summary([r for r in rows if r["depth"] == depth])
                for depth in sorted({r["depth"] for r in rows})}
    by_opponent = {name: policy_summary([r for r in rows if r["opponent"] == name])
                   for name in sorted({r["opponent"] for r in rows})}
    return {
        "rows": len(rows), "policy": policy, "by_depth": by_depth, "by_opponent": by_opponent,
        "vs_pooled_delta_bb": mean(paired(rows, control="pooled")),
        "vs_pooled_ci_bb": interval(rows, "pooled") if holdout else None,
        "vs_baseline_ci_bb": interval(rows) if holdout else None,
        "primary_depth_ci_bb": interval([r for r in rows if r["depth"] == 15]) if holdout else None,
        "calibration": {field or "pooled": calibration_summary(rows, field)
                        for field in (None, "price", "pressure", "raise_legal", "opponent", "depth")},
        "performance": {"candidate_median_ms": 1000 * median(r["performance"]["seconds"] for r in rows),
                        "candidate_peak_traced_bytes": max(r["performance"]["traced_peak_bytes"] for r in rows),
                        "live_median_ms": 1000 * median(r["live_seconds"] for r in rows)},
    }


def gate(primary, stress):
    candidate = primary["policy"]["conditioned"]
    brier = primary["calibration"]["pooled"]["all"]
    checks = {
        "mean_gain": candidate["delta_bb"] >= .10,
        "mean_gain_15bb": primary["by_depth"][15]["conditioned"]["delta_bb"] >= .10,
        "paired_interval": primary["vs_baseline_ci_bb"][0] > 0,
        "opponents": all(s["conditioned"]["delta_bb"] >= 0 for s in primary["by_opponent"].values()),
        "depths": all(s["conditioned"]["delta_bb"] >= 0 for s in primary["by_depth"].values()),
        "raising_stress": stress["policy"]["conditioned"]["delta_bb"] >= 0,
        "worst_row": min(candidate["worst_delta_bb"], stress["policy"]["conditioned"]["worst_delta_bb"]) >= -.25,
        "material_harm_frequency": candidate["material_harm_count"] / primary["rows"] <= .10,
        "brier": brier["conditioned"]["brier"] < brier["baseline"]["brier"],
        "runtime": primary["performance"]["candidate_median_ms"] < 20,
        "memory": primary["performance"]["candidate_peak_traced_bytes"] < 2 * 1024 ** 2,
        "verified_integrity": True,
    }
    return {"passed": all(checks.values()), "criteria": checks}


def run(panel):
    if panel == "historical":
        work = [(Case(*CASES[-1]), 15, "loose_aggressive", 0)]
    else:
        args = CALIBRATION if panel == "calibration" else HOLDOUT
        streams = (41,) if panel == "calibration" else (51, 52)
        work = product((Case(*args_) for args_ in args), DEPTHS, STYLES, streams)
    profiles = {}
    tables = {}
    rows = []
    for case, depth, opponent, stream in work:
        key = (opponent, stream)
        if key not in profiles:
            profiles[key] = train(opponent, stream, (30,))[30]
            tables[key] = {False: train_responses(opponent, stream, False)}
            if panel != "historical" and STYLES[opponent].aggressive:
                tables[key][True] = train_responses(opponent, stream, True)
        rows.extend(score(case, depth, opponent, stream, profiles[key], tables[key], panel == "historical"))
    summary = {name: panel_summary([r for r in rows if r["raising"] == raised], panel == "holdout")
               for name, raised in (("primary", False), ("raising_stress", True))
               if any(r["raising"] == raised for r in rows)}
    if panel == "holdout":
        summary["gate"] = gate(summary["primary"], summary["raising_stress"])
    return {"panel": panel, "summary": summary, "rows": rows}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=("historical", "calibration", "holdout"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    start = perf_counter()
    result = run(args.panel)
    result["wall_seconds"] = perf_counter() - start
    result["process_peak_resident_bytes"] = peak_resident_bytes()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
