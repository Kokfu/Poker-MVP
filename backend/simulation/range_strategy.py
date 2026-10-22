"""Bounded range-equity adjustments layered over the immutable Expert baseline.

Ranges describe current-hand hypotheses from public actions; opponent profiles
remain long-run behavioural evidence and are not used here to avoid double
counting.  This module never receives hidden cards, deck state, or future
events.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from .actions import Action
from .decision_state import DecisionObservation

AdjustmentLevel = Literal["none", "small", "moderate", "strong"]

# Centralized conservative research thresholds.  A range is heuristic, so a
# clear price error is required before a baseline fold/call is changed.
CALL_MARGIN = 0.12
FOLD_MARGIN = -0.12
# Sequential public-action updates are intentionally floored and consequently
# remain broad; 1% concentration is enough to admit (not force) a separately
# large equity-margin adjustment.  Near-uniform ranges still retain baseline.
MIN_CONCENTRATION = 0.01
VALUE_EQUITY = 0.70


@dataclass(frozen=True)
class RangeAwareDecisionExplanation:
    baseline_action: str; baseline_target: int | None
    final_action: str; final_target: int | None
    adjustment_applied: bool; adjustment_category: str | None
    adjustment_level: AdjustmentLevel
    range_equity: float | None; required_equity: float; equity_margin: float | None
    method: str | None; iterations: int | None
    active_combos: int | None; effective_combo_count: float | None
    normalized_entropy: float | None; concentration: float | None
    top_range_category_shares: dict[str, float]
    concentration_gate: str; rationale: str; safeguards: tuple[str, ...]


class RangeStrategyAdjustmentEngine:
    """Allows only fold<->call and modest check/bet value transitions.

    It deliberately does not invent all-in bluffs or raise a baseline fold.
    River exact estimates arrive from the decision boundary; flop/turn use one
    deterministic Monte Carlo result prepared once for that decision.
    """
    def apply(self, observation: DecisionObservation, baseline: Action) -> tuple[Action, RangeAwareDecisionExplanation]:
        f, s, summary, equity = observation.poker_features, observation.decision_state, observation.opponent_range_summary, observation.range_equity
        required = f.required_equity
        if summary is None:
            return baseline, self._explain(baseline, baseline, None, required, summary, "unavailable", "range snapshot unavailable; Expert baseline retained", ("no-range fallback",))
        if equity is None or not isinstance(getattr(equity, "hero_equity", None), (int, float)) or not isfinite(equity.hero_equity):
            return baseline, self._explain(baseline, baseline, None, required, summary, "unavailable", "range equity unavailable; Expert baseline retained", ("no-equity fallback",))
        hero_equity = float(equity.hero_equity)
        margin = hero_equity - required
        concentration = max(0.0, min(1.0, 1.0 - float(getattr(summary, "normalized_entropy", 1.0))))
        # Small concentration is intentionally insufficient for action flips.
        if concentration < MIN_CONCENTRATION:
            return baseline, self._explain(baseline, baseline, equity, required, summary, "blocked", "broad uncertain range retained baseline", ("concentration below conservative gate",))

        level: AdjustmentLevel = "strong" if concentration >= .35 and abs(margin) >= .20 else "moderate" if abs(margin) >= .16 else "small"
        action, category, rationale, safeguards = baseline, None, "range evidence did not fit an allowed transition", ("bounded transition policy retained baseline",)
        # Facing bets: price is the highest-value, least speculative use.
        call_action = "call" if "call" in s.legal_actions else "all_in" if "all_in" in s.legal_actions else None
        if baseline.type == "fold" and call_action and margin >= CALL_MARGIN:
            action, category = Action(call_action), "equity_call"
            rationale, safeguards = "range equity clearly exceeds the required price", ("only fold-to-call/all-in-call; no raise created",)
        elif baseline.type == "call" and "fold" in s.legal_actions and margin <= FOLD_MARGIN:
            action, category = Action("fold"), "equity_fold"
            rationale, safeguards = "range equity is materially below the required price", ("only call-to-fold; tiny margins do not change baseline",)
        # Value additions require strong actual equity and a meaningfully weak
        # component in the current inferred range.  No profile signal is added.
        elif not s.amount_to_call and baseline.type == "check" and "bet" in s.legal_actions and hero_equity >= VALUE_EQUITY and getattr(summary, "weak_air_fraction", 0.0) >= .20 and s.minimum_legal_target is not None:
            target = max(s.minimum_legal_target, min(s.maximum_legal_target, s.current_highest_bet + max(1, round(s.pot * .33))))
            action, category, rationale = Action("bet", target), "value_expand", "strong equity versus a weak-heavy range supports a bounded value bet"
            safeguards = ("check-to-small-bet only; target clamped to legal interval",)
        elif baseline.type == "bet" and "check" in s.legal_actions and hero_equity <= .52 and getattr(summary, "strong_made_fraction", 0.0) >= .45:
            action, category, rationale = Action("check"), "value_reduce", "strong-heavy range suppresses marginal baseline value betting"
            safeguards = ("bet-to-check only; no bluff substitution",)
        return action, self._explain(baseline, action, equity, required, summary, "passed", rationale, safeguards, category, level if action != baseline else "none")

    @staticmethod
    def _explain(base, final, equity, required, summary, gate, rationale, safeguards, category=None, level: AdjustmentLevel="none"):
        value = getattr(equity, "hero_equity", None) if equity else None
        shares = {name: float(getattr(summary, name, 0.0)) for name in ("strong_made_fraction", "pair_fraction", "draw_fraction", "weak_air_fraction")} if summary else {}
        entropy = getattr(summary, "normalized_entropy", None) if summary else None
        return RangeAwareDecisionExplanation(base.type, base.amount, final.type, final.amount, base != final, category, level, value, required, value - required if value is not None else None, getattr(equity, "method", None) if equity else None, getattr(equity, "iterations", None) if equity else None, getattr(summary, "active_combos", None) if summary else None, getattr(summary, "effective_combo_count", getattr(equity, "effective_combo_count", None)) if summary else None, entropy, 1 - entropy if entropy is not None else None, shares, gate, rationale, tuple(safeguards))
