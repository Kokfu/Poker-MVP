"""How strongly an opponent's actions follow hand strength, learned at showdown.

Node locks (``solver.exploit``) fit an opponent's observed action frequencies
while preserving the solver's hand ordering, i.e. they assume stronger hands
bet and call more often.  That is right for sensible players and badly wrong
for a maniac who bets random hands.  This model estimates the difference from
public evidence only: completed-hand histories where both hole-card pairs
were legitimately revealed at showdown.

For each street where the opponent bet/raised or called, it records the
percentile of their revealed hand among all hands possible on that street's
board (1 = strongest).  If their continuing hands were strength-ordered the
mean percentile would be near ``1 - f / 2`` (f = how often they take such
actions); if they were random it would be near 0.5.  ``correlation`` maps the
observed mean onto [0, 1] and shrinks toward 1 (the solver's default
assumption) until enough showdowns have been seen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .combos import COMBO_CLASS, COMBO_COUNT, card_mask, combo_index
from .equity import rank_vector

AGGRESSIVE = {"bet", "raise", "all_in"}
PRIOR_STRENGTH = 8.0  # pseudo-observations at correlation 1


@lru_cache(maxsize=1)
def _preflop_percentiles() -> np.ndarray:
    from .preflop import load_class_equity
    class_d, class_w = load_class_equity()
    from .combos import CLASS_COMBO_COUNT
    weights = CLASS_COMBO_COUNT * class_w
    strength = (class_d * weights).sum(axis=1) / weights.sum(axis=1)  # vs a random hand
    per_combo = strength[COMBO_CLASS]
    order = per_combo.argsort().argsort()
    return (order + 0.5) / COMBO_COUNT


def hand_percentile(cards, board) -> float:
    """Percentile of ``cards`` among all combos possible given ``board``."""
    if not board:
        return float(_preflop_percentiles()[combo_index(cards)])
    live = np.where(~card_mask(tuple(board)))[0]
    ranks = rank_vector(list(board), live)
    mine = ranks[int(np.searchsorted(live, combo_index(cards)))]
    below, equal = (ranks < mine).sum(), (ranks == mine).sum()
    return float((below + 0.5 * equal) / len(ranks))


@dataclass
class ShowdownModel:
    percentiles: dict[str, list[float]] = field(default_factory=lambda: {"aggressive": [], "call": []})
    opportunities: dict[str, int] = field(default_factory=lambda: {"aggressive": 0, "call": 0, "decisions": 0})
    hands: int = 0

    def observe(self, history, opponent: str) -> None:
        """Consume one completed hand; only showdown reveals are read."""
        self.hands += 1
        actions = [e for e in history.events if e.event_type == "action_taken" and e.actor == opponent and e.applied_action]
        for event in actions:
            self.opportunities["decisions"] += 1
            if event.applied_action in AGGRESSIVE:
                self.opportunities["aggressive"] += 1
            elif event.applied_action == "call":
                self.opportunities["call"] += 1
        shown = next((e.revealed_hole_cards for e in history.events if e.event_type == "showdown" and e.revealed_hole_cards), None)
        if not shown or opponent not in shown:
            return
        cards = tuple(shown[opponent])
        seen: set[tuple[str, str]] = set()
        for event in actions:
            group = "aggressive" if event.applied_action in AGGRESSIVE else "call" if event.applied_action == "call" else None
            if group is None or (event.street, group) in seen:
                continue
            seen.add((event.street, group))
            self.percentiles[group].append(hand_percentile(cards, tuple(event.board)))

    def correlation(self, group: str) -> float:
        values = self.percentiles[group]
        if not values:
            return 1.0
        decisions = max(self.opportunities["decisions"], 1)
        frequency = min(max(self.opportunities[group] / decisions, 0.02), 0.98)
        ordered_mean = 1.0 - frequency / 2.0
        observed = (float(np.mean(values)) - 0.5) / max(ordered_mean - 0.5, 0.05)
        observed = min(max(observed, 0.0), 1.0)
        n = len(values)
        return (n * observed + PRIOR_STRENGTH * 1.0) / (n + PRIOR_STRENGTH)

    def summary(self) -> dict:
        return {"showdowns_used": {g: len(v) for g, v in self.percentiles.items()},
                "strength_correlation": {g: round(self.correlation(g), 3) for g in self.percentiles}}
