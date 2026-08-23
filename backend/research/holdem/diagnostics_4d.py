"""Audits and checkpoint reports for the bounded Phase 4D game."""
from __future__ import annotations

from collections import Counter
from time import perf_counter

from .cfr import HoldemSubgameCFRTrainer
from .subgame import HoldemSubgameState, chance_states, subgame_convention


def tree_diagnostics() -> dict[str, object]:
    roots = chance_states(); states: set[HoldemSubgameState] = set(); terminals: set[HoldemSubgameState] = set()
    infosets: dict[str, set[str]] = {}; max_depth = 0
    def visit(state: HoldemSubgameState) -> None:
        nonlocal max_depth
        states.add(state); max_depth = max(max_depth, len(state.history))
        if state.terminal:
            terminals.add(state); return
        key = state.information_set(); infosets.setdefault(key, {item.label for item in state.legal_actions})
        for action in state.legal_actions: visit(state.apply(action))
    for root in roots: visit(root)
    actions = Counter(len(value) for value in infosets.values())
    return {"convention": subgame_convention(), "chance_nodes": len(roots), "concrete_research_states": len(states),
            "abstract_states": len(infosets), "information_sets": len(infosets), "terminal_nodes": len(terminals),
            "max_tree_depth": max_depth, "actions_per_information_set": dict(sorted(actions.items())),
            "full_tree_node_count": len(states), "bounded": len(states) <= 10000}


def validate_tree() -> list[str]:
    errors: list[str] = []
    def visit(state: HoldemSubgameState) -> None:
        cards = state.player0_cards + state.player1_cards + tuple(state.decision_state().board_cards if not state.terminal else ("As", "Kd", "7c"))
        if len(cards) != len(set(cards)): errors.append("duplicate cards")
        if state.terminal:
            # Check the public game interface rather than the tautology
            # ``u != -(-u)``: every terminal must expose the same zero-sum
            # payoff through both player perspectives.
            if state.utility(0) != -state.utility(1): errors.append("terminal utility is not zero sum")
            return
        actions = state.legal_actions
        if not actions: errors.append("nonterminal state lacks legal actions")
        key = state.information_set()
        if any(card in key for card in ("Ah", "Ad", "Kh", "Kc", "Qs", "Js")): errors.append("information set leaks private cards")
        for action in actions:
            try: child = state.apply(action)
            except ValueError: errors.append("advertised impossible action")
            else: visit(child)
    for root in chance_states(): visit(root)
    return errors


def training_report(checkpoints: tuple[int, ...] = (1, 10, 100, 1000)) -> dict[str, object]:
    if tuple(sorted(set(checkpoints))) != checkpoints or not checkpoints or checkpoints[0] < 1: raise ValueError("checkpoints must be sorted positive unique values")
    result: dict[str, list[dict[str, object]]] = {}
    for algorithm in ("vanilla", "cfr_plus"):
        trainer = HoldemSubgameCFRTrainer(algorithm); rows = []; prior = 0; previous_policy = None
        for checkpoint in checkpoints:
            started = perf_counter(); trainer.train(checkpoint - prior); elapsed = perf_counter() - started; prior = checkpoint
            policy = trainer.average_strategy()
            rows.append({"iterations": checkpoint, "information_sets": len(trainer.infosets), "profile_ev_player0": trainer.profile_ev(),
                         "average_strategy_l1_change": None if previous_policy is None else _l1(previous_policy, policy),
                         "runtime_seconds": elapsed, "iterations_per_second": (checkpoint - (rows[-1]["iterations"] if rows else 0)) / elapsed if elapsed else float("inf")})
            previous_policy = policy
        result[algorithm] = rows
    return {"phase_4d_schema_version": "1.0", "tree": tree_diagnostics(), "algorithms": result,
            "best_response": "Not reported for this full abstraction: exhaustive information-set constrained pure-policy enumeration is intentionally intractable; profile EV is exact over all 90 chance deals.",
            "stability_convention": "L1 distance between successive average strategies; stabilization is a deterministic diagnostic, not proof of Nash convergence.",
            "checkpoint_limit": "1,000 iterations is the default matched horizon; 10,000 remains optional for this transparent full-tree Python prototype."}


def _l1(before: dict[str, dict[str, float]], after: dict[str, dict[str, float]]) -> float:
    return sum(abs(before[key][action] - after[key][action]) for key in before for action in before[key])
