"""Exact profile evaluation and imperfect-information best responses."""
from __future__ import annotations

from itertools import product
from typing import Mapping

from .game import Action, Card, DEALS, KuhnState

Policy = Mapping[str, Mapping[Action, float]]

def _distribution(state: KuhnState, policy: Policy) -> Mapping[Action, float]:
    actions = state.legal_actions; supplied = policy.get(state.information_set(), {})
    result = {a: float(supplied.get(a, 0.0)) for a in actions}
    if abs(sum(result.values()) - 1.0) > 1e-9 or any(p < 0 or p > 1 for p in result.values()):
        raise ValueError(f"invalid strategy at {state.information_set()}")
    return result

def expected_value(policy0: Policy, policy1: Policy) -> float:
    def walk(state: KuhnState) -> float:
        if state.terminal: return state.utility_p0()
        policy = policy0 if state.acting_player == 0 else policy1
        return sum(p * walk(state.apply(a)) for a, p in _distribution(state, policy).items())
    return sum(walk(KuhnState(deal)) for deal in DEALS) / len(DEALS)

def _keys_for(player: int) -> list[tuple[str, tuple[Action, ...]]]:
    states = [KuhnState(deal) for deal in DEALS]
    seen: dict[str, tuple[Action, ...]] = {}
    def visit(state: KuhnState) -> None:
        if state.terminal: return
        if state.acting_player == player: seen[state.information_set()] = state.legal_actions
        for action in state.legal_actions: visit(state.apply(action))
    for state in states: visit(state)
    return sorted(seen.items())

def best_response(fixed_policy: Policy, responding_player: int) -> tuple[float, dict[str, dict[Action, float]]]:
    """Brute-force legal pure behavioral policies (64 candidates), never deals-aware."""
    keys = _keys_for(responding_player)
    best_value = float("-inf") if responding_player == 0 else float("inf")
    best: dict[str, dict[Action, float]] = {}
    for selections in product((0, 1), repeat=len(keys)):
        response = {key: {actions[pick]: 1.0, actions[1 - pick]: 0.0} for (key, actions), pick in zip(keys, selections)}
        value = expected_value(response, fixed_policy) if responding_player == 0 else expected_value(fixed_policy, response)
        if (responding_player == 0 and value > best_value) or (responding_player == 1 and value < best_value):
            best_value, best = value, response
    return best_value, best

def metrics(policy0: Policy, policy1: Policy) -> dict[str, float]:
    value = expected_value(policy0, policy1)
    br0, _ = best_response(policy1, 0)
    br1_as_u0, _ = best_response(policy0, 1)
    return {"player0_ev": value, "player1_ev": -value, "br0": br0, "br1_as_u0": br1_as_u0,
            "nashconv": br0 - br1_as_u0, "exploitability": (br0 - br1_as_u0) / 2.0}
