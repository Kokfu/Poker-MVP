"""Local, observational pricing of the Coach's finite river tree."""
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import combinations
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from types import MappingProxyType
from typing import Mapping

import numpy as np

from research.holdem.decoupled_replay import hand_tiers
from research.holdem import river_risk
from research.holdem.reply_forecast import ResponseAssumptions, forecast, holding_values, river_counts
from simulation.decision_state import DecisionState
from solver.combos import card_mask, combo_index
from solver.equity import rank_vector
from solver.tree import StreetState


FLAG = "POKER_COACH_RIVER_SHADOW"
TRACE_DIR = "POKER_COACH_RIVER_SHADOW_DIR"
CEILING = 15.0
BUDGET = .150
MAX_NODES = 128
MATERIAL = .01  # bb
RANGE_RELAXATION = .15


class Unsupported(ValueError):
    pass


@dataclass(frozen=True)
class FrozenNode:
    index: int
    kind: str
    player: int
    labels: tuple[str, ...]
    actions: tuple
    children: tuple[int, ...]
    contribution: tuple[int, int]
    state: StreetState


@dataclass(frozen=True)
class RiverEvaluationInput:
    """Snapshot of the chosen public tree and permitted decision-time model."""

    decision: DecisionState
    root: FrozenNode
    nodes: Mapping[int, FrozenNode]
    menu: tuple[tuple[str, int | None], ...]
    mix: tuple[float, ...]
    seeded: int
    cfr_ev_bb: tuple[float, ...] | None
    ids: np.ndarray
    outcomes: np.ndarray
    posterior: np.ndarray
    projected: np.ndarray
    replies: Mapping[int, np.ndarray]
    hero_tail: Mapping[int, np.ndarray]
    working_set: tuple[int, int]
    omitted_mass: float
    counts: tuple[int, int, int]


def frozen(array):
    return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)


def check_deadline(deadline):
    if perf_counter() >= deadline:
        raise TimeoutError


def check_mix(array):
    if (not np.isfinite(array).all() or (array < 0).any()
            or not np.allclose(array.sum(axis=0), 1., atol=1e-9, rtol=0)):
        raise ValueError("invalid action probabilities")


def snapshot(advisor, profile, deadline):
    ds, solve, root, hero_column, reach, mix, seeded, raw = advisor.river_shadow_context
    hero = root.player
    if (root.state.pot != ds.pot or root.state.stack != tuple(
            (ds.hero_stack, ds.opponent_stack)[int(p != hero)] for p in (0, 1))
            or root.state.commit[hero] != ds.hero_street_commitment
            or root.state.commit[1 - hero] != ds.opponent_street_commitment):
        raise Unsupported("decision_geometry")

    menu = []
    for abstract in root.actions:
        action = advisor._concrete_postflop(ds, abstract)
        kind, target = action.type, action.amount
        if kind not in ds.legal_actions or (kind in ("bet", "raise") and (
                target != abstract[1] or not ds.minimum_legal_target <= target <= ds.maximum_legal_target)):
            raise Unsupported("concrete_menu")
        if kind != abstract[0] and not (kind == "all_in" and abstract[0] == "call"
                                      and ds.hero_stack <= ds.amount_to_call):
            raise Unsupported("concrete_menu")
        menu.append((kind, target))
    if len(set(menu)) != len(menu):
        raise Unsupported("duplicate_actions")
    check_mix(mix)
    if raw is not None and not np.isfinite(raw).all():
        raise ValueError("invalid CFR values")

    nodes, pending = {}, [root.index]
    while pending:
        check_deadline(deadline)
        if len(nodes) >= MAX_NODES:
            raise Unsupported("tree_node_limit")
        node = solve.tree.nodes[pending.pop()]
        nodes[node.index] = FrozenNode(node.index, node.kind, node.player, tuple(node.labels), tuple(node.actions),
                                       tuple(node.children), node.contribution, node.state)
        pending.extend(reversed(node.children))

    ids = np.flatnonzero(~card_mask((*ds.board_cards, *ds.hole_cards)))
    hero_id = combo_index(ds.hole_cards)
    ranks = rank_vector(list(ds.board_cards), np.append(ids, hero_id))
    outcomes = np.sign(ranks[-1] - ranks[:-1])
    ranks = ranks[:-1]
    columns = solve.combos[1 - hero]
    positions = np.searchsorted(columns, ids).clip(0, len(columns) - 1)
    present = columns[positions] == ids
    weights = reach[ids]
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("invalid opponent reach")
    if not weights[present].any():
        raise Unsupported("empty_compatible_working_range")
    posterior = weights / weights.sum()
    projected = np.where(present, weights, 0.)
    projected /= projected.sum()

    # Phase 5A's deterministic nearest-showdown-rank extension. Real CFR
    # columns keep their own policies. Extension is only used outside them.
    levels, groups = np.unique(ranks[present], return_inverse=True)
    right = np.searchsorted(levels, ranks).clip(0, len(levels) - 1)
    left = (right - 1).clip(0)
    nearest = np.where(abs(ranks - levels[left]) <= abs(ranks - levels[right]), left, right)
    population = np.bincount(groups)
    replies, tail = {}, {}
    for node in nodes.values():
        check_deadline(deadline)
        if node.kind != "decision" or node.index == root.index:
            continue
        strategy = solve.average[node.index]
        if node.player == hero:
            policy = strategy[:, hero_column]
            check_mix(policy)
            tail[node.index] = frozen(policy)
        else:
            policy = strategy[:, positions].copy()
            for row in policy:
                by_rank = np.bincount(groups, weights=row[present], minlength=len(levels)) / population
                row[~present] = by_rank[nearest[~present]]
            check_mix(policy)
            replies[node.index] = frozen(policy)

    return RiverEvaluationInput(
        ds, nodes[root.index], MappingProxyType(nodes), tuple(menu), tuple(mix), seeded,
        None if raw is None else tuple(raw / ds.big_blind), frozen(ids), frozen(outcomes),
        frozen(posterior), frozen(projected), MappingProxyType(replies), MappingProxyType(tail),
        tuple(map(len, solve.combos)), float(posterior[~present].sum()), river_counts(profile),
    )


def key(action):
    kind, target = action
    return kind if target is None else f"{kind}_{target}"


def summarize_replies(model, replies, weights):
    """Condition response frequencies on prior actions along each branch."""
    summary = {}

    def visit(index, reach):
        node = model.nodes[index]
        if node.kind != "decision":
            return
        if index in replies:
            policy = replies[index]
            total = float(reach.sum())
            summary[index] = {"actions": dict(zip(node.labels, (policy @ reach / total).tolist()))
                              if total > 0 else None, "reach": total}
        else:
            policy = model.hero_tail[index]
        for child, probability in zip(node.children, policy, strict=True):
            visit(child, reach * probability)

    for child in model.root.children:
        visit(child, weights)
    return summary


def evaluate(model, deadline):
    labels = tuple(map(key, model.menu))
    bb = model.decision.big_blind
    odd = model.decision.acting_player == "b"

    def payoff(replies):
        check_deadline(deadline)
        values = holding_values(model, model.root, model.outcomes, replies, model.hero_tail, odd) / bb
        check_deadline(deadline)
        return values

    def values_dict(values):
        return dict(zip(labels, values.tolist(), strict=True))

    def preferred(values):
        return max(sorted(labels), key=values.get)

    nominal = payoff(model.replies)
    estimated = values_dict(nominal @ model.posterior)
    projected = values_dict(nominal @ model.projected)
    cfr = None if model.cfr_ev_bb is None else dict(zip(labels, model.cfr_ev_bb, strict=True))
    seeded = labels[model.seeded]
    best = preferred(estimated)
    relaxed = (1 - RANGE_RELAXATION) * model.posterior + RANGE_RELAXATION / len(model.ids)
    scenarios = {"range_relaxation": values_dict(nominal @ relaxed)}
    reply_summary = {"coach": summarize_replies(model, model.replies, model.posterior)}
    assumptions = ResponseAssumptions.from_counts(*model.counts)
    live, tiers = hand_tiers(tuple(model.decision.board_cards))
    tiers = tiers[np.searchsorted(live, model.ids)]
    for name, indexes in (("lower_continue_raise", (0, 0)), ("higher_continue_raise", (2, 2))):
        check_deadline(deadline)
        replies = {i: forecast(model.nodes[i], tiers, assumptions, (*indexes, True, "uniform"))
                   if model.nodes[i].state.commit[0] != model.nodes[i].state.commit[1] else policy
                   for i, policy in model.replies.items()}
        payoffs = payoff(replies)
        scenarios[name] = values_dict(payoffs @ model.posterior)
        scenarios[f"{name}_relaxed"] = values_dict(payoffs @ relaxed)
        reply_summary[name] = summarize_replies(model, replies, model.posterior)
    check_deadline(deadline)

    ranking_differences = []
    if cfr is not None:
        def sign(delta):
            return int(delta > MATERIAL) - int(delta < -MATERIAL)

        ranking_differences = [[a, b] for a, b in combinations(labels, 2)
                               if sign(cfr[a] - cfr[b]) != sign(estimated[a] - estimated[b])]

    risk_started = perf_counter()
    closing = {}
    if {kind for kind, _ in model.root.actions} == {"fold", "call"} and not model.replies:
        for name, direction in (("closing_more_hero_wins", 1), ("closing_more_hero_losses", -1)):
            tilted = model.posterior * river_risk.CLOSING_ODDS_FACTOR ** (direction * model.outcomes / 2.)
            closing[name] = values_dict(nominal @ (tilted / tilted.sum()))
    risk = river_risk.evaluate(model, estimated, scenarios, reply_summary, closing, model.seeded)
    risk["closing_ev_bb"] = closing
    risk["stress_greedy_change_fraction"] = sum(
        preferred(values) != best for values in (*scenarios.values(), *closing.values())
    ) / (len(scenarios) + len(closing))
    check_deadline(deadline)

    return {
        "value_basis": "estimated Coach model, net bb relative to folding at this decision",
        "actions": [{"action": kind, "amount": target, "tree_target": abstract[1]}
                    for (kind, target), abstract in zip(model.menu, model.root.actions, strict=True)],
        "cfr_mix": dict(zip(labels, model.mix, strict=True)), "cfr_ev_bb": cfr,
        "bounded_ev_bb": estimated, "projected_ev_bb": projected,
        "modal": labels[int(np.argmax(model.mix))], "seeded": seeded,
        "cfr_preferred": preferred(cfr) if cfr is not None else None,
        "bounded_preferred": best, "incremental_ev_bb": estimated[best] - estimated[seeded],
        "ranking_differences": ranking_differences,
        "range": {"compatible": len(model.ids), "positive": int(np.count_nonzero(model.posterior)),
                  "effective": float(1 / (model.posterior @ model.posterior)),
                  "largest_probability": float(model.posterior.max()), "omitted_mass": model.omitted_mass},
        "reply_forecasts": reply_summary, "profile_river_fold_call_raise_counts": model.counts,
        "sensitivity_ev_bb": scenarios,
        "sensitivity_preferred": {name: preferred(values) for name, values in scenarios.items()},
        "sensitivity_delta_from_coach_bb": {name: {action: values[action] - estimated[action] for action in labels}
                                             for name, values in scenarios.items()},
        "working_set": model.working_set, "tree_nodes": len(model.nodes),
        "decision_risk": risk, "risk_seconds": perf_counter() - risk_started,
    }


def write_trace(record):
    directory = os.environ.get(TRACE_DIR)
    if directory is None:
        local = Path(os.environ["LOCALAPPDATA"]) if "LOCALAPPDATA" in os.environ else Path.home() / ".local/state"
        directory = local / "PokerAnalyzer" / "research" / "river-shadow"
    folder = Path(directory)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(record, sort_keys=True, allow_nan=False)
    temp = None
    try:
        with NamedTemporaryFile(dir=folder, prefix="river-", suffix=".pending", delete=False,
                                mode="w", encoding="utf-8") as output:
            temp = Path(output.name)
            output.write(payload + "\n")
        temp.replace(temp.with_suffix(".json"))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def observe(ds, advisor, profile, advisor_started):
    started = perf_counter()
    public = ds.as_dict()
    hero = public.pop("hole_cards")
    record = {"version": 1, "decision_id": sha256(json.dumps(public, sort_keys=True).encode()).hexdigest(),
              "hero": hero, "board": public["board_cards"], "pot": ds.pot,
              "effective_stack": ds.effective_stack, "big_blind": ds.big_blind,
              "hero_stack": ds.hero_stack, "opponent_stack": ds.opponent_stack,
              "street_commitments": [ds.hero_street_commitment, ds.opponent_street_commitment],
              "amount_to_call": ds.amount_to_call,
              "legal_actions": ds.legal_actions, "target_bounds": [ds.minimum_legal_target, ds.maximum_legal_target],
              "advisor_seconds_before_shadow": started - advisor_started}
    deadline = min(started + BUDGET, advisor_started + CEILING)
    try:
        if advisor.river_shadow_context is None:
            raise Unsupported("no_incumbent_river_solve")
        check_deadline(deadline)
        model = snapshot(advisor, profile, deadline)
        record.update(evaluate(model, deadline), status="complete")
        record["decision_risk"]["profile_hands_observed"] = profile.hands_observed if profile is not None else 0
    except Unsupported as error:
        record.update(status="unsupported", reason=str(error))
    except TimeoutError:
        record.update(status="timeout", reason="shadow_budget")
    except Exception as error:
        record.update(status="error", reason=type(error).__name__)
    record["shadow_seconds"] = perf_counter() - started
    write_trace(record)
