"""Independent terminal transfers for finite heads-up river continuations."""
from dataclasses import dataclass, replace

import numpy as np

from research.holdem.phase_4k import strength


@dataclass(frozen=True)
class Ledger:
    """Past-street pot, street totals, and remaining cash at the decision."""

    past: int
    totals: tuple[int, int]
    cash: tuple[int, int]
    hero: int
    odd_chip: bool

    def advance(self, actor, kind, target):
        if kind in ("check", "fold"):
            return self
        own = self.totals[actor]
        if kind == "call":
            target = min(max(self.totals), own + self.cash[actor])
        assert own < target <= own + self.cash[actor]
        totals, cash = list(self.totals), list(self.cash)
        totals[actor], cash[actor] = target, cash[actor] - (target - own)
        return replace(self, totals=tuple(totals), cash=tuple(cash))

    def terminal(self, outcomes, starting_cash, folder=None):
        """Return the stack change after refund and award, as integer chips."""
        matched = min(self.totals)
        pool = self.past + 2 * matched
        refund = self.totals[self.hero] - matched
        if folder is None:
            award = np.where(outcomes > 0, pool, np.where(outcomes == 0, (pool + self.odd_chip) // 2, 0))
        else:
            award = np.full(len(outcomes), pool if folder != self.hero else 0)
        return self.cash[self.hero] + refund + award - starting_cash


def root_ledger(ds, hero):
    totals = (ds.hero_street_commitment, ds.opponent_street_commitment)
    cash = (ds.hero_stack, ds.opponent_stack)
    return Ledger(ds.pot - sum(totals), totals if hero == 0 else totals[::-1],
                  cash if hero == 0 else cash[::-1], hero, ds.acting_player == "b")


def evaluate_tree(tree, root, ledger, outcomes, replies, hero_tail):
    """Follow the prescribed action menus, settling without tree contributions."""
    starting_cash = ledger.cash[ledger.hero]

    def value(index, state):
        node = tree.nodes[index]
        if node.kind != "decision":
            return state.terminal(outcomes, starting_cash, node.player if node.kind == "fold" else None)
        probabilities = hero_tail[node.index] if node.player == ledger.hero else replies[node.index]
        return sum(p * value(child, state.advance(node.player, *action))
                   for p, child, action in zip(probabilities, node.children, node.actions, strict=True))

    return np.array([value(child, ledger.advance(root.player, *action))
                     for child, action in zip(root.children, root.actions, strict=True)])


def reference_reply(node, holdings, style, allow_raise=True):
    """Fixed Phase 4K call law. Aggressive styles can also shove, by hand tier."""
    state, actor = node.state, node.player
    own, offered = state.commit[actor], state.commit[1 - actor]
    cost = min(offered - own, state.stack[actor])
    pot = sum(state.base) + 2 * own
    call = np.array([style.call_probability(h.combo, h.rank, cost, pot + cost) for h in holdings])
    result = np.zeros((len(node.actions), len(holdings)))
    shove = 0.
    if allow_raise and style.aggressive and "all_in" in node.labels:
        shove = np.array([(.02, .10, .35)[strength(h.rank)] for h in holdings])
        if cost > pot:
            shove *= .5
        result[node.labels.index("all_in")] = shove
    result[node.labels.index("fold")] = (1 - shove) * (1 - call)
    result[node.labels.index("call")] = (1 - shove) * call
    return result


def all_wagers(ledger, outcomes, weights, holdings, style, minimum, maximum):
    """Exhaust every integer root wager with the fixed fold/call reference."""
    if minimum is None or maximum is None or maximum < minimum:
        return {}
    hero, other = ledger.hero, 1 - ledger.hero
    own, their = ledger.totals[hero], ledger.totals[other]
    targets = np.arange(minimum, maximum + 1)
    matched = np.minimum(targets, their + ledger.cash[other])
    cost = matched - their
    before = ledger.past + 2 * their
    pool = ledger.past + 2 * matched
    fold_value = ledger.past + own + their
    pays = matched - own
    small = cost <= before
    values = np.empty(len(targets))
    for mask, call_price, pot in ((small, 1, 2), (~small, 2, 3)):
        probs = weights * [style.call_probability(h.combo, h.rank, call_price, pot) for h in holdings]
        values[mask] = ((probs[outcomes > 0].sum() * pool[mask]) +
                        probs[outcomes == 0].sum() * ((pool[mask] + ledger.odd_chip) // 2)
                        - probs.sum() * pays[mask] + (1 - probs.sum()) * fold_value)
    return dict(zip(targets.tolist(), values.tolist(), strict=True))
