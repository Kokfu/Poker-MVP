"""Offline river oracle decomposition. No production solver changes."""
from argparse import ArgumentParser
from dataclasses import asdict, dataclass, replace
from itertools import product
import json
from math import fsum, isclose
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import numpy as np

from coach.service import _replay
from research.holdem.phase_4k import (
    BIG_BLIND, CASES, HARM_TOLERANCE, STYLES, OffProbe, OnProbe, label,
    peak_resident_bytes, river_spot, to_action, train, weighted_ev,
)
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action
from solver.bot import map_action, replay_hand
from solver.cfr import ALPHA, BETA, GAMMA
from solver.combos import combo_index

ARMS = ("A", "B", "C", "D")
HOLDOUT = (
    ("overpair", "Jh Js", "9d 4d 2s Qh 6c", 0, 250),
    ("missed_draw", "As Ts", "Ks 8d 5s 3h 3c", 0, 300),
    ("two_pair", "Ah 7c", "Ad 7s 2h 9s Jd", 500, 250),
    ("second_pair", "Qd Jd", "Ks Qh 4c 8d 2s", 500, 350),
)


class RiverTrace:
    """Keep the final river solve used by the existing Coach replay."""

    explain_ev = True
    record_estimate = True

    def _solve(self, root_state, *args, **kwargs):
        solved = super()._solve(root_state, *args, **kwargs)
        if root_state.street == "river":
            self.river = solved
        return solved

    def trace(self, spot, profile=None):
        if profile:
            profile.attach(self)
        status, payload, engine = _replay(spot, self, profile.snapshot if profile else None)
        info = payload["explanation"]
        if status != "hero_to_act" or self.fallback_count or info["source"] != "postflop_solve":
            raise RuntimeError(f"unexpected Coach decision {status}: {info}")
        ds = self.decision_state
        replay = replay_hand(ds)
        tree = self.river.tree
        root = tree.root
        if tree.nodes[root].state != replay.current:
            for step in replay.steps:
                if step.street == "river":
                    choice = map_action(tree, root, step.kind, step.target)
                    root = tree.nodes[root].children[choice]
        node = tree.nodes[root]
        if node.state != replay.current or node.labels != info["labels"]:
            raise AssertionError("probe did not recover the live decision node")
        if sum(engine.state.stacks.values()) + engine.state.pot != spot.hero_stack + spot.villain_stack:
            raise AssertionError("replayed stacks and pot do not conserve chips")
        return node, ds, payload["advice"]


class Live(RiverTrace, OnProbe):
    pass


class Disabled(RiverTrace, OffProbe):
    pass


@dataclass(frozen=True)
class Case:
    name: str
    hero: str
    board: str
    bet: int
    open_to: int = 250

    def spot(self, depth):
        spot = river_spot(self.hero, self.board, self.bet)
        return replace(spot, hero_stack=depth * BIG_BLIND, villain_stack=depth * BIG_BLIND,
                       actions=[replace(spot.actions[0], amount=self.open_to), *spot.actions[1:]])


def reference(case, node):
    state = node.state
    hero = node.player
    villain = 1 - hero
    return RiverState(state.pot, state.commit[hero], state.commit[villain],
                      state.stack[hero], state.stack[villain], state.last_full_raise,
                      checked_to=case.bet == 0)


def normalize(weights):
    if not np.isfinite(weights).all() or (weights < 0).any() or not weights.sum() > 0:
        raise ValueError("invalid range")
    return weights / weights.sum()


def response_means(actions, probabilities):
    groups = {"fold": 0.0, "call": 0.0, "raise": 0.0}
    for (kind, _), probability in zip(actions, probabilities, strict=True):
        groups["raise" if kind == "all_in" else kind] += float(probability)
    return groups


def modeled_continuation(bot, node, holdings):
    """Extract the live conditional posterior and freeze the final policies.

    Give pruned hands a response by nearest showdown rank among compatible
    retained hands, averaging equal-rank columns. Their estimated reach is
    still zero, so this extension can affect only the range-oracle arm.
    """
    solved = bot.river
    solver = solved.solver
    tree = solved.tree
    hero = node.player
    hero_pos = int(np.searchsorted(solved.combos[hero], combo_index(bot.decision_state.hole_cards)))
    columns = {int(combo): i for i, combo in enumerate(solved.combos[1 - hero])}
    indices = [columns.get(combo_index(hand.combo), -1) for hand in holdings]
    retained = np.array([i >= 0 for i in indices])
    columns_here = np.array(indices)[retained]
    _, reach = solver._reaches(hero, lambda n: solved.average[n.index])
    weights = np.zeros(len(holdings))
    weights[retained] = reach[node.index, columns_here]
    weights = normalize(weights)
    ranks = np.array([hand.rank for hand in holdings])
    retained_ranks = ranks[retained]
    distance = abs(ranks[~retained, None] - retained_ranks)
    donors = distance == distance.min(axis=1, keepdims=True)
    donors = donors / donors.sum(axis=1, keepdims=True)

    responses = {}
    hero_policy = {}
    descendants = [node.index]
    while descendants:
        child = tree.nodes[descendants.pop()]
        if child.kind != "decision":
            continue
        descendants.extend(child.children)
        sigma = solved.average[child.index]
        if child.player == hero:
            hero_policy[child.index] = sigma[:, hero_pos]
        else:
            fitted = np.empty((len(child.actions), len(holdings)))
            fitted[:, retained] = sigma[:, columns_here]
            fitted[:, ~retained] = fitted[:, retained] @ donors.T
            if (fitted < 0).any() or not np.allclose(fitted.sum(axis=0), 1, rtol=0, atol=1e-10):
                raise AssertionError("invalid modeled response")
            responses[child.index] = fitted
    return weights, retained, responses, hero_policy, solver.action_values(node, hero_pos)


def payoff_values(tree, node, holdings, weights, responses, hero_policy):
    """Validate the solver's EV via Treys ranks and stack receipts at leaves."""
    hero = node.player
    results = np.array([holding.result for holding in holdings])

    def value(index, reach):
        branch = tree.nodes[index]
        spent = branch.contribution[hero] - node.state.contribution(hero)
        if branch.kind == "fold":
            award = sum(branch.contribution) if branch.player != hero else 0
            return reach.sum() * (award - spent)
        if branch.kind == "leaf":
            pot = sum(branch.contribution)
            # This panel uses equal sunk contributions and a matched river.
            if pot % 2:
                raise AssertionError("odd pot needs a seat-aware split")
            award = np.where(results > 0, pot, np.where(results == 0, pot // 2, 0))
            return float(reach @ (award - spent))
        policy = hero_policy[branch.index] if branch.player == hero else responses[branch.index]
        return fsum(value(child, reach * probability)
                    for child, probability in zip(branch.children, policy, strict=True))

    return np.array([value(child, weights) for child in node.children])


def fixed_value_mix(values, iterations):
    """Production DCFR discounts at a single Hero choice with fixed action EVs."""
    regret = np.zeros_like(values, dtype=float)
    average = np.zeros_like(regret)
    for t in range(1, iterations + 1):
        positive = np.maximum(regret, 0)
        total = positive.sum()
        current = positive / total if total > 0 else np.full(len(values), 1 / len(values))
        regret *= np.where(regret > 0, t ** ALPHA / (t ** ALPHA + 1), t ** BETA / (t ** BETA + 1))
        regret += values - current @ values
        average *= (t / (t + 1)) ** GAMMA
        average += current
    return normalize(average)


def exact_values(evaluator, state, keys, call_probability):
    return {key: evaluator.action_ev(state, to_action(key), call_probability) / BIG_BLIND for key in keys}


def legal_optimum(exact, state, ds, keys, call_probability, modeled_keys):
    """Search the endpoints of the two affine pricing regions and the stack cap."""
    candidates = set(modeled_keys)
    if "all_in" in ds.legal_actions:
        candidates.add("all_in")
    kind = "bet" if "bet" in keys else "raise" if "raise" in keys else None
    if kind:
        effective_cap = state.villain_commit + state.villain_stack
        low, high = ds.minimum_legal_target, min(ds.maximum_legal_target, effective_cap)
        # The reference's small call condition is 2*cost <= pot + Hero's increment.
        boundary = state.pot + 2 * state.villain_commit - state.hero_commit
        candidates.update(f"{kind}_{target}" for target in (low, high, boundary, boundary + 1)
                          if low <= target <= high)
    values = exact_values(exact, state, sorted(candidates), call_probability)
    best = max(values, key=values.get)
    return best, values[best]


def true_response(exact, state, key, call_probability):
    hero, villain, reply = state.branch(to_action(key))
    if not reply:
        return None
    matched = min(hero, villain)
    cost = matched - state.villain_commit
    pot = state.pot + matched - state.hero_commit
    call = fsum(h.weight * call_probability(h.combo, h.rank, cost, pot) for h in exact.holdings)
    return {"fold": 1 - call, "call": call, "raise": 0.0}


def score(case, depth, opponent, profile, disabled_mix=None):
    started = perf_counter()
    spot = case.spot(depth)
    live = Live(917)
    node, ds, advice = live.trace(spot, profile)
    live_seconds = perf_counter() - started
    keys = [label(live._concrete_postflop(ds, act)) for act in node.actions]
    if len(set(keys)) != len(keys) or any(to_action(k).type not in ds.legal_actions for k in keys):
        raise AssertionError(f"unexpected concretized action set {keys}")
    for key in keys:
        target = to_action(key).amount
        if target is not None and not ds.minimum_legal_target <= target <= ds.maximum_legal_target:
            raise AssertionError(f"illegal total {key}")
    if label(Action(advice["action"], advice["amount"])) not in keys:
        raise AssertionError("seeded recommendation left the legal menu")

    board, hero = tuple(spot.board), tuple(spot.hero_cards)
    style = STYLES[opponent]
    exact = ExactRiverEV(hero, board, lambda cards, rank: style.path_likelihood(cards, board, rank, case.bet))
    state = reference(case, node)
    true = exact_values(exact, state, keys, style.call_probability)
    weights, kept, responses, hero_policy, live_values = modeled_continuation(live, node, exact.holdings)
    tree = live.river.tree
    true_weights = np.array([hand.weight for hand in exact.holdings])
    if live.estimate is None:
        raise AssertionError("missing live range estimate")
    report_weights = np.array([live.estimate[combo_index(hand.combo)] for hand in exact.holdings])
    # The range card reports pre-pruning reach on an off-tree re-solve.
    # Factorial range inputs must use the actual final solve's conditioned reach.
    weight_by_combo = {combo_index(hand.combo): weight for hand, weight in zip(exact.holdings, weights, strict=True)}
    inferred = ExactRiverEV(hero, board, lambda cards, _: float(weight_by_combo[combo_index(cards)]))
    best = max(true, key=true.get)
    best_legal, best_legal_ev = legal_optimum(exact, state, ds, ds.legal_actions, style.call_probability, keys)
    a = payoff_values(tree, node, exact.holdings, weights, responses, hero_policy)
    if not np.allclose(a, live_values, rtol=0, atol=0.002):
        raise AssertionError(f"payoff parity: independent {a}, solver {live_values}")
    b = payoff_values(tree, node, exact.holdings, true_weights, responses, hero_policy)
    c = exact_values(inferred, state, keys, style.call_probability)
    modeled = (dict(zip(keys, a / BIG_BLIND, strict=True)),
               dict(zip(keys, b / BIG_BLIND, strict=True)), c, true)

    def arm(values, probabilities, evaluator, range_weights, known_response):
        mix = dict(zip(keys, map(float, probabilities), strict=True))
        if min(mix.values()) < 0 or not isclose(fsum(mix.values()), 1, rel_tol=0, abs_tol=1e-10):
            raise AssertionError("invalid policy mix")
        ev = weighted_ev(mix, true)
        response = {}
        for key, child in zip(keys, node.children, strict=True):
            if known_response:
                response[key] = true_response(evaluator, state, key, style.call_probability)
            elif child in responses:
                response[key] = response_means(tree.nodes[child].actions, responses[child] @ range_weights)
            else:
                response[key] = None
        return {"modeled_ev_bb": values, "mix": mix, "recommendation": max(mix, key=mix.get),
                "responses": response, "ev_bb": ev, "regret_bb": true[best] - ev,
                "mae_bb": mean(abs(values[k] - true[k]) for k in keys),
                "ranking_regret_bb": true[best] - true[max(values, key=values.get)]}

    arms = {}
    for name, values, evaluator, range_weights, known_response in zip(
        ARMS, modeled, (inferred, exact, inferred, exact),
        (weights, true_weights, weights, true_weights), (False, False, True, True), strict=True
    ):
        mix = fixed_value_mix(np.array([values[key] for key in keys]), live.iterations["river"])
        arms[name] = arm(values, mix, evaluator, range_weights, known_response)
    production = arm(modeled[0], live.probabilities, inferred, weights, False)
    production["seeded_advice"] = advice
    greedy = max(modeled[0], key=modeled[0].get)
    candidate_started = perf_counter()
    candidate_index = int(np.argmax(live_values))
    candidate_seconds = perf_counter() - candidate_started
    if keys[candidate_index] != greedy and abs(modeled[0][keys[candidate_index]] - modeled[0][greedy]) > 0.00002:
        raise AssertionError("candidate EV ranking differs from audited model")
    candidate_ev = true[keys[candidate_index]]
    return {
        "case": case.name, "depth": depth, "opponent": opponent, "hero": hero, "board": board,
        "state": asdict(state), "legal": list(ds.legal_actions),
        "target_interval": [ds.minimum_legal_target, ds.maximum_legal_target],
        "effective_stack": min(state.hero_stack + state.hero_commit, state.villain_stack + state.villain_commit)
                           - state.hero_commit,
        "true_evs_bb": true, "best_supported": best, "best_legal": best_legal,
        "abstraction_regret_bb": best_legal_ev - true[best],
        "true_responses": {key: true_response(exact, state, key, style.call_probability) for key in keys},
        "production": production, "arms": arms,
        "disabled": None if disabled_mix is None else {"mix": disabled_mix, "ev_bb": weighted_ev(disabled_mix, true)},
        "candidate": {"action": keys[candidate_index], "ev_bb": candidate_ev,
                      "regret_bb": true[best] - candidate_ev, "selection_seconds": candidate_seconds},
        "range_tv": float(abs(weights - true_weights).sum() / 2),
        "display_vs_solver_range_tv": float(abs(weights - report_weights).sum() / 2),
        "estimated_equity": inferred.equity, "true_equity": exact.equity,
        "true_mass_outside_retained_support": float(true_weights[~kept].sum()),
        "holdings": {"combos": [h.combo for h in exact.holdings],
                     "estimated": weights.tolist(), "true": true_weights.tolist()},
        "live_payoff_max_error_chips": float(abs(a - live_values).max()),
        "live_seconds": live_seconds,
    }


def summary(rows):
    metrics = {}
    for name in (*ARMS, "production", "candidate"):
        policies = [row["arms"][name] if name in ARMS else row[name] for row in rows]
        ev = [policy["ev_bb"] for policy in policies]
        delta = [value - row["arms"]["A"]["ev_bb"] for row, value in zip(rows, ev, strict=True)]
        against_live = [value - row["production"]["ev_bb"] for row, value in zip(rows, ev, strict=True)]
        harm = [value for value in delta if value < -HARM_TOLERANCE]
        frequencies = {kind: 0.0 for kind in ("fold", "check", "call", "bet", "raise", "all_in")}
        for policy in policies:
            mix = policy["mix"] if "mix" in policy else {policy["action"]: 1.0}
            for key, mass in mix.items():
                frequencies[to_action(key).type] += mass / len(rows)
        metrics[name] = {
            "mean_ev_bb": mean(ev), "median_ev_bb": median(ev), "worst_ev_bb": min(ev),
            "delta_vs_a_bb": mean(delta), "worst_delta_vs_a_bb": min(delta), "harm_vs_a": len(harm),
            "mean_delta_vs_live_bb": mean(against_live),
            "worst_delta_vs_live_bb": min(against_live),
            "harm_vs_live": sum(d < -HARM_TOLERANCE for d in against_live),
            "mean_regret_bb": mean(p["regret_bb"] for p in policies),
            "max_regret_bb": max(p["regret_bb"] for p in policies),
            "frequencies": frequencies,
            **{key: mean(p[key] for p in policies) for key in ("mae_bb", "ranking_regret_bb") if key in policies[0]},
        }
    a, b, c, d = [metrics[name]["mean_ev_bb"] for name in ARMS]
    return {"count": len(rows), "policies": metrics,
            "range_at_estimated_response_bb": b - a, "range_at_true_response_bb": d - c,
            "response_at_estimated_range_bb": c - a, "response_at_true_range_bb": d - b,
            "interaction_bb": d - c - b + a}


def run(workload):
    if workload == "development":
        cases, depths, streams = tuple(Case(*case) for case in CASES), (15,), (0,)
    else:
        cases, depths, streams = tuple(Case(*case) for case in HOLDOUT), (15, 9, 30), (9, 10)
    profiles = {(name, stream): train(name, stream, (30,))[30]
                for name, stream in product(STYLES, streams)}
    rows = []
    for depth, case in product(depths, cases):
        off_mix = None
        if workload == "development":
            bot = Disabled(917)
            node, ds, _ = bot.trace(case.spot(depth))
            off_mix = dict(zip((label(bot._concrete_postflop(ds, a)) for a in node.actions),
                               map(float, bot.probabilities), strict=True))
        for name, stream in product(STYLES, streams):
            rows.append({"stream": stream, **score(case, depth, name, profiles[name, stream], off_mix)})
        print(f"{workload} {depth} bb {case.name}: {len(rows)} rows", flush=True)
    return {
        "rows": rows, "overall": summary(rows),
        "by_depth": {str(depth): summary([row for row in rows if row["depth"] == depth]) for depth in depths},
        "by_opponent": {name: summary([row for row in rows if row["opponent"] == name]) for name in STYLES},
        "by_case": {case.name: summary([row for row in rows if row["case"] == case.name]) for case in cases},
        "by_stream": {str(stream): summary([row for row in rows if row["stream"] == stream]) for stream in streams},
    }


class TimingTrace(Live):
    """Retain the river solver only when the research policy needs its values."""

    explain_ev = False
    retain_values = False

    def _solve(self, root_state, *args, **kwargs):
        self.explain_ev = self.retain_values and root_state.street == "river"
        try:
            solved = super()._solve(root_state, *args, **kwargs)
        finally:
            self.explain_ev = False
        if root_state.street == "river":
            self.value_solver = solved.solver
            solved.solver = None
        return solved


def time_policy(candidate):
    # Separate CLI processes allow an isolated peak working set for each arm.
    stream = 9
    profiles = {name: train(name, stream, (30,))[30] for name in STYLES}
    rows = []
    for values in HOLDOUT:
        case = Case(*values)
        for name in STYLES:
            started = perf_counter()
            bot = TimingTrace(917)
            bot.retain_values = candidate
            node, ds, advice = bot.trace(case.spot(15), profiles[name])
            selection_seconds = value_seconds = 0.0
            if candidate:
                value_started = perf_counter()
                position = int(np.searchsorted(bot.river.combos[node.player], combo_index(ds.hole_cards)))
                action_evs = bot.value_solver.action_values(node, position)
                value_seconds = perf_counter() - value_started
                selection_started = perf_counter()
                choice = int(np.argmax(action_evs))
                action = bot._concrete_postflop(ds, node.actions[choice])
                selection_seconds = perf_counter() - selection_started
            else:
                action = Action(advice["action"], advice["amount"])
            if (action.type not in ds.legal_actions or
                    action.amount is not None and not ds.minimum_legal_target <= action.amount <= ds.maximum_legal_target):
                raise AssertionError(f"illegal timed recommendation {action}")
            rows.append({"case": case.name, "opponent": name, "action": label(action),
                         "seconds": perf_counter() - started, "value_seconds": value_seconds,
                         "selection_seconds": selection_seconds})
    return {"rows": rows, "mean_decision_seconds": mean(row["seconds"] for row in rows),
            "mean_value_seconds": mean(row["value_seconds"] for row in rows),
            "mean_selection_seconds": mean(row["selection_seconds"] for row in rows)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("workload", choices=("development", "holdout", "time-live", "time-greedy"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    started = perf_counter()
    result = (time_policy(args.workload == "time-greedy") if args.workload.startswith("time-")
              else run(args.workload))
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({**result, "seconds": perf_counter() - started, "peak_resident_bytes": peak_resident_bytes()},
                  output, separators=(",", ":"), allow_nan=False)


if __name__ == "__main__":
    main()
