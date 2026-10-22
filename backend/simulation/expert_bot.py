"""Deterministic, explainable heads-up rule-based poker strategy.

This is deliberately a compact heuristic baseline, not a solver.  It consumes
only ``DecisionObservation`` and treats engine-provided legal actions/targets
as authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from poker_analyzer import RANK_VALUE

from .actions import Action
from .bots import PokerBot
from .decision_state import DecisionObservation
from .game_state import Observation


@dataclass(frozen=True)
class ExpertDecisionExplanation:
    chosen_action: str
    target_total: int | None
    strategy_category: str
    hand_strength_category: str
    equity_used: float | None
    required_equity: float
    pot_odds: float
    spr: float
    opponent_adjustment: str | None
    sizing_rationale: str | None
    primary_reasons: tuple[str, ...]
    warnings: tuple[str, ...]


class ExpertRuleBot(PokerBot):
    """A deterministic, conservative rule-based heads-up strategy.

    Sizing buckets are 33%, 60%, and 85% of the pot.  Low SPR is <= 3,
    medium is <= 7, and deep is > 7.  The values are target-total clamped.
    """
    LOW_SPR = 3.0
    MEDIUM_SPR = 7.0

    def __init__(self, seed: int | None = None, equity_iterations: int = 1000):
        super().__init__(seed, equity_iterations)
        self.last_explanation: ExpertDecisionExplanation | None = None
        self.decision_count = 0
        self.negative_target_incidents = 0
        self.out_of_bounds_target_incidents = 0

    def decide(self, observation: Observation) -> Action:
        # Compatibility only; production engine uses decide_decision.
        return self._legacy_passive(observation)

    @staticmethod
    def _legacy_passive(o: Observation) -> Action:
        if "check" in o.legal_actions:
            return Action("check")
        if "call" in o.legal_actions:
            return Action("call")
        if "all_in" in o.legal_actions:
            return Action("all_in")
        return Action("fold")

    def decide_decision(self, observation: DecisionObservation) -> Action:
        self.decision_count += 1
        s, f = observation.decision_state, observation.poker_features
        strength = self._preflop_strength(s.hole_cards) if f.is_preflop else self._postflop_strength(f, s)
        adjustment, warnings = self._opponent_adjustment(observation)
        equity = observation.equity.estimated_equity if observation.equity and isfinite(observation.equity.estimated_equity) else None
        reasons = [strength]
        if equity is not None:
            reasons.append("equity estimate available")
        if adjustment:
            reasons.append(adjustment)

        if f.is_preflop:
            preferred, category, size = self._preflop(s, strength)
        else:
            preferred, category, size = self._postflop(s, f, strength, equity, adjustment)
        action = self._legalize(s, preferred, size)
        sizing = None if action.amount is None else ("all-in" if action.type == "all_in" else f"{size or 0:.0%} pot target")
        self.last_explanation = ExpertDecisionExplanation(
            action.type, action.amount, category, strength, equity, f.required_equity,
            f.pot_odds, f.stack_to_pot_ratio, adjustment, sizing, tuple(reasons), tuple(warnings),
        )
        return action

    def _preflop_strength(self, cards: tuple[str, ...]) -> str:
        ranks = sorted((RANK_VALUE[c[0]] for c in cards), reverse=True)
        hi, lo = ranks
        pair, suited = hi == lo, cards[0][1] == cards[1][1]
        connected = hi - lo <= 2
        if pair and hi >= 11 or (hi >= 13 and lo >= 12) or (hi == 14 and lo >= 11): return "premium"
        if pair and hi >= 8 or (hi >= 12 and lo >= 10) or (hi == 14 and lo >= 9 and suited): return "strong"
        if pair or (hi >= 11 and lo >= 8) or (suited and hi >= 10 and connected): return "medium_playable"
        if suited and connected or (hi >= 10 and lo >= 7 and connected): return "speculative"
        return "weak"

    def _preflop(self, s, strength: str) -> tuple[str, str, float | None]:
        raises = sum(a.action in {"bet", "raise", "all_in"} for a in s.hand_actions)
        facing = s.amount_to_call > 0
        short = s.effective_stack_bb <= 20
        opening = raises == 0 and not facing
        if short and strength in {"premium", "strong"} and "all_in" in s.legal_actions:
            return "all_in", "preflop_commit", None
        if opening:
            if strength in {"premium", "strong", "medium_playable"} or (s.position == "in_position" and strength == "speculative"):
                return "raise", "preflop_open", 0.60
            return "check", "preflop_fold_or_check", None
        if facing:
            # First raise: defend broadly in position; 3-bet pots require strength.
            threshold = {"premium", "strong"} if raises >= 2 else ({"premium", "strong", "medium_playable"} if s.position == "in_position" else {"premium", "strong"})
            if strength == "premium": return "raise", "preflop_value_reraise", 0.85
            if strength in threshold: return "call", "preflop_defend", None
            if short and strength == "medium_playable" and s.amount_to_call <= s.pot // 3: return "all_in", "preflop_short_commit", None
            return "fold", "preflop_fold", None
        # A limp is a free opportunity to isolate wider than an unopened raise.
        if strength in {"premium", "strong", "medium_playable", "speculative"}:
            return "raise", "preflop_isolate_limp", 0.75
        return "check", "preflop_check", None

    def _postflop_strength(self, f, s) -> str:
        if f.has_straight_flush or f.has_quads or f.has_full_house or f.has_flush or f.has_straight or f.has_trips or f.has_two_pair: return "strong_made"
        hero_ranks = sorted((RANK_VALUE[c[0]] for c in s.hole_cards), reverse=True)
        board_high = RANK_VALUE[f.board_high_card_rank] if f.board_high_card_rank else 0
        if f.has_pair and (hero_ranks[0] >= board_high or hero_ranks[0] >= 13): return "strong_pair"
        if f.pair_plus_draw: return "pair_plus_draw"
        if f.flush_draw or f.open_ended_straight_draw: return "strong_draw"
        if f.gutshot or f.has_pair: return "medium_showdown"
        return "air"

    def _postflop(self, s, f, strength: str, equity: float | None, adjustment: str | None) -> tuple[str, str, float | None]:
        facing = s.amount_to_call > 0
        wet = f.connected_board or f.two_tone_board or f.monotone_board
        value = strength in {"strong_made", "strong_pair"}
        draw = strength in {"strong_draw", "pair_plus_draw"}
        required = f.required_equity
        if equity is not None and facing and equity < required - 0.04:
            return "fold", "equity_fold", None
        if facing:
            big_bet = f.bet_faced_fraction_of_pot >= .75
            if strength == "strong_made": return "raise", "value_raise", .85 if wet else .60
            if strength == "strong_pair" and f.stack_to_pot_ratio <= self.LOW_SPR: return "raise", "low_spr_commit", .75
            if draw and (not big_bet or f.pair_plus_draw or (equity is not None and equity >= required)):
                return "raise" if s.position == "in_position" and not big_bet else "call", "draw_continue", .60
            if strength == "medium_showdown" and not big_bet and (equity is None or equity >= required - .03): return "call", "showdown_value", None
            if strength == "strong_pair" and not (f.stack_to_pot_ratio > self.MEDIUM_SPR and big_bet): return "call", "pair_bluffcatch", None
            return "fold", "postflop_fold", None
        if value: return "bet", "value_bet", .85 if wet and strength == "strong_made" else .60
        if draw and (s.position == "in_position" or s.hero_has_initiative): return "bet", "semi_bluff", .60
        # Deterministic selective bluff: initiative, position, dry board and no calling-station adjustment.
        pressure_spot = s.hero_has_initiative or adjustment == "selective_pressure_vs_tight_passive"
        if strength == "air" and s.position == "in_position" and pressure_spot and not wet and adjustment != "reduce_bluffs_vs_loose_passive":
            return "bet", "selective_bluff", .33
        return "check", "check_back", None

    def _opponent_adjustment(self, o: DecisionObservation) -> tuple[str | None, list[str]]:
        profile = o.opponent_profile
        if profile is None: return None, []
        stats = getattr(profile, "statistics", {})
        confidence = getattr(stats.get("vpip"), "confidence", "very_low") if isinstance(stats, dict) else "very_low"
        if confidence in {"very_low", "low"}: return None, ["opponent sample confidence is low"]
        # Numeric public estimates are the strategy input; the descriptive
        # classification remains available for reporting but is not decisive.
        def rate(name: str, default: float = .0) -> float:
            estimate = stats.get(name) if isinstance(stats, dict) else None
            value = getattr(estimate, "smoothed_frequency", default)
            return value if isinstance(value, (int, float)) and isfinite(value) else default
        loose, aggressive = rate("vpip") >= .50, rate("aggressive") >= .35
        if loose and not aggressive: return "reduce_bluffs_vs_loose_passive", []
        if loose and aggressive: return "widen_bluffcatch_vs_loose_aggressive", []
        if not loose and not aggressive: return "selective_pressure_vs_tight_passive", []
        if not loose and aggressive: return "avoid_marginal_aggression_vs_tight_aggressive", []
        return None, []

    def _legalize(self, s, preferred: str, fraction: float | None) -> Action:
        legal = set(s.legal_actions)
        if preferred in {"bet", "raise"} and preferred in legal and s.minimum_legal_target is not None:
            increment = max(1, round(s.pot * (fraction or .60)))
            target = s.current_highest_bet + increment
            target = max(s.minimum_legal_target, min(target, s.maximum_legal_target))
            if s.minimum_legal_target <= target <= s.maximum_legal_target: return self._record_target(s, Action(preferred, target))
        if preferred in legal: return self._record_target(s, Action(preferred))
        if preferred in {"raise", "bet"} and "all_in" in legal: return self._record_target(s, Action("all_in"))
        for fallback in ("check", "call", "fold", "all_in"):
            if fallback in legal: return self._record_target(s, Action(fallback))
        return self._record_target(s, Action("fold"))

    def _record_target(self, s, action: Action) -> Action:
        if action.amount is not None:
            self.negative_target_incidents += int(action.amount < 0)
            self.out_of_bounds_target_incidents += int(action.amount > s.maximum_legal_target)
        return action
