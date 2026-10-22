"""One-street betting trees that follow the engine's legal-target rules.

Players are indexed 0/1 inside a tree.  Every bet/raise is a street *total*
("target"), exactly like the engine.  A street closes on a check or call once
the other player has acted this street (so a preflop limp still lets the big
blind act).  When a street closes the tree ends in a ``leaf``: an exact
showdown on the river, otherwise an all-remaining-runouts equity leaf.  Leaves
and folds carry each player's total hand contribution so utilities are exact
chip amounts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import ceil
from typing import Literal


@dataclass(frozen=True)
class SizeMenu:
    """Bet sizes by aggression depth on a street.

    Postflop entries are pot fractions: target = highest + f * (pot + to_call).
    Preflop entries (``multiplier=True``) are multiples of the highest bet.
    Depths beyond the menu allow only all-in.  All-in is always available.
    """
    by_depth: tuple[tuple[float, ...], ...]
    multiplier: bool = False
    allow_all_in: bool = True
    all_in_merge: float = 0.85  # sizes at/above this share of all-in become all-in


POSTFLOP_MENU = SizeMenu(by_depth=((0.5, 1.0), (1.0,)))
PREFLOP_MENU = SizeMenu(by_depth=((2.5,), (3.0,), (2.3,)), multiplier=True)


@dataclass(frozen=True)
class StreetState:
    street: Literal["preflop", "flop", "turn", "river"]
    to_act: int
    commit: tuple[int, int]  # this street
    stack: tuple[int, int]  # behind
    base: tuple[int, int]  # contributed on earlier streets (incl. blinds preflop are in commit)
    last_full_raise: int
    acted: tuple[bool, bool] = (False, False)
    depth: int = 0  # bets/raises already made on this street

    @property
    def highest(self) -> int:
        return max(self.commit)

    @property
    def pot(self) -> int:
        return sum(self.base) + sum(self.commit)

    def contribution(self, player: int) -> int:
        return self.base[player] + self.commit[player]


@dataclass
class Node:
    index: int
    kind: Literal["decision", "fold", "leaf"]
    player: int = -1  # decision: actor; fold: the player who folded
    labels: list[str] = field(default_factory=list)
    actions: list[tuple[str, int | None]] = field(default_factory=list)  # (type, street target)
    children: list[int] = field(default_factory=list)
    contribution: tuple[int, int] = (0, 0)
    state: StreetState | None = None


class StreetTree:
    def __init__(self, root: StreetState, menu: SizeMenu, max_nodes: int = 5_000):
        self.menu, self.max_nodes = menu, max_nodes
        self.nodes: list[Node] = []
        self.root = self._build(root)

    def _node(self, **values) -> Node:
        if len(self.nodes) >= self.max_nodes:
            raise ValueError("betting tree exceeds node limit")
        node = Node(index=len(self.nodes), **values)
        self.nodes.append(node)
        return node

    def _terminal(self, state: StreetState, kind: str, player: int = -1) -> int:
        return self._node(kind=kind, player=player, contribution=(state.contribution(0), state.contribution(1)), state=state).index

    def _build(self, state: StreetState) -> int:
        node = self._node(kind="decision", player=state.to_act, state=state)
        for label, kind, target in legal_abstract_actions(state, self.menu):
            node.labels.append(label)
            node.actions.append((kind, target))
            node.children.append(self._after(state, kind, target))
        if not node.actions:
            raise ValueError("decision node without actions")
        return node.index

    def _after(self, state: StreetState, kind: str, target: int | None) -> int:
        p, o = state.to_act, 1 - state.to_act
        if kind == "fold":
            return self._terminal(state, "fold", p)
        commit, stack = list(state.commit), list(state.stack)
        acted = list(state.acted)
        acted[p] = True
        if kind in ("check", "call"):
            amount = min(state.highest - commit[p], stack[p]) if kind == "call" else 0
            commit[p] += amount
            stack[p] -= amount
            after = replace(state, commit=tuple(commit), stack=tuple(stack), acted=tuple(acted), to_act=o)
            if acted[o] or 0 in stack:
                # Street closes (or nobody can act again): trim unmatched excess.
                matched = min(commit)
                refund = [commit[i] - matched for i in (0, 1)]
                after = replace(after, commit=(matched, matched), stack=(stack[0] + refund[0], stack[1] + refund[1]))
                return self._terminal(after, "leaf")
            return self._build(after)
        assert target is not None
        raise_size = target - state.highest
        full = raise_size >= state.last_full_raise
        stack[p] -= target - commit[p]
        commit[p] = target
        after = replace(
            state, commit=tuple(commit), stack=tuple(stack), acted=tuple(acted), to_act=o,
            last_full_raise=raise_size if full else state.last_full_raise, depth=state.depth + 1,
        )
        return self._build(after)


def legal_abstract_actions(state: StreetState, menu: SizeMenu) -> list[tuple[str, str, int | None]]:
    """(label, engine type, street target) choices at ``state``."""
    p, o = state.to_act, 1 - state.to_act
    to_call = state.highest - state.commit[p]
    actions: list[tuple[str, str, int | None]] = []
    if to_call > 0:
        actions.append(("fold", "fold", None))
        actions.append(("call", "call", None))
    else:
        actions.append(("check", "check", None))
    # Nobody to bet into, or the opponent is already all-in.
    if state.stack[p] <= to_call or state.stack[o] == 0:
        return actions
    all_in = min(state.commit[p] + state.stack[p], state.commit[o] + state.stack[o])
    minimum = state.highest + state.last_full_raise
    kind = "raise" if state.highest > 0 else "bet"
    targets: list[int] = []
    sizes = menu.by_depth[state.depth] if state.depth < len(menu.by_depth) else ()
    for size in sizes:
        target = ceil(size * state.highest) if menu.multiplier else state.highest + ceil(size * (state.pot + to_call))
        target = max(target, minimum)
        if target >= menu.all_in_merge * all_in or target >= all_in:
            continue
        if target not in targets:
            targets.append(target)
    for target in targets:
        label = f"{kind}_{target}"
        actions.append((label, kind, target))
    if menu.allow_all_in and all_in > state.highest:
        actions.append(("all_in", "all_in", all_in))
    return actions
