"""Tree and invariant diagnostics for the bounded Phase 4F research game."""
from __future__ import annotations

from collections import Counter

from .turn_subgame import MAX_EXACT_TREE_NODES, FIXED_FLOP, TurnHoldemState, turn_chance_states, turn_subgame_convention


def turn_tree_diagnostics(roots: tuple[TurnHoldemState, ...] | None = None) -> dict[str, object]:
    roots = roots or turn_chance_states()
    states: set[TurnHoldemState] = set(); terminals: set[TurnHoldemState] = set(); chance_nodes = set()
    infosets: dict[str, set[str]] = {}; street_infosets: Counter[str] = Counter(); max_depth = 0

    def visit(state: TurnHoldemState) -> None:
        nonlocal max_depth
        states.add(state)
        max_depth = max(max_depth, len(state.flop_history) + len(state.turn_history) + (1 if state.turn_card else 0))
        if state.terminal:
            terminals.add(state); return
        if state.chance:
            chance_nodes.add(state)
            for _, child, _ in state.chance_outcomes(): visit(child)
            return
        key = state.information_set()
        if key not in infosets: street_infosets[state.street] += 1
        infosets.setdefault(key, {action.label for action in state.legal_actions})
        for action in state.legal_actions: visit(state.apply(action))

    for root in roots: visit(root)
    if len(states) > MAX_EXACT_TREE_NODES:
        raise RuntimeError(f"Phase 4F exact tree guardrail exceeded: {len(states)} > {MAX_EXACT_TREE_NODES}")
    actions = Counter(len(value) for value in infosets.values())
    return {
        "convention": turn_subgame_convention(), "root_private_chance_outcomes": len(roots),
        "legal_turn_outcomes_per_reached_node": sorted({len(node.remaining_turn_cards()) for node in chance_nodes}),
        "full_tree_node_count": len(states), "chance_nodes": len(chance_nodes),
        "terminal_nodes": len(terminals), "information_sets": len(infosets),
        "information_sets_by_street": dict(street_infosets), "max_depth": max_depth,
        "actions_per_information_set": dict(sorted(actions.items())),
        "estimated_state_memory_bytes": len(states) * 256,
        "guardrail_nodes": MAX_EXACT_TREE_NODES, "bounded": True,
    }


def validate_turn_tree(roots: tuple[TurnHoldemState, ...] | None = None) -> list[str]:
    errors: list[str] = []
    for root in roots or turn_chance_states():
        def visit(state: TurnHoldemState) -> None:
            visible = set(FIXED_FLOP) | set(state.player0_cards) | set(state.player1_cards)
            if len(visible) != 7:
                errors.append("private/fixed-flop collision")
            if state.terminal:
                if state.utility(0) != -state.utility(1): errors.append("terminal utility is not zero sum")
                return
            if state.chance:
                outcomes = state.chance_outcomes()
                if sum(probability for _, _, probability in outcomes) != 1.0: errors.append("turn probabilities do not sum to one")
                for card, child, _ in outcomes:
                    if card in visible or child.turn_card != card: errors.append("illegal turn card")
                    visit(child)
                return
            key = state.information_set()
            if any(card in key for card in state.deck): errors.append("information set leaks card")
            if state.turn_card is None and any(card in key for card in state.remaining_turn_cards()): errors.append("flop key leaks future card")
            if not state.legal_actions: errors.append("nonterminal lacks legal actions")
            for action in state.legal_actions:
                try: visit(state.apply(action))
                except ValueError: errors.append("advertised impossible action")
        visit(root)
    return errors
