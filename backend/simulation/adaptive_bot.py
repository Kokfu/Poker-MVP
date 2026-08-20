"""Adaptive strategy: immutable ExpertRuleBot control plus exploit layer."""
from __future__ import annotations

from .actions import Action
from .bots import PokerBot
from .decision_state import DecisionObservation
from .expert_bot import ExpertRuleBot, ExpertDecisionExplanation
from .exploit_strategy import ExploitAdjustmentEngine, ExploitDecisionExplanation
from .game_state import Observation


class ExpertAdaptiveBot(PokerBot):
    """Uses only the observation's completed-history opponent snapshot."""
    def __init__(self, seed: int | None = None, equity_iterations: int = 1000):
        super().__init__(seed, equity_iterations)
        self.baseline = ExpertRuleBot(seed, equity_iterations)
        self.engine = ExploitAdjustmentEngine()
        self.last_baseline_explanation: ExpertDecisionExplanation | None = None
        self.last_explanation: ExploitDecisionExplanation | None = None
        # In-memory research diagnostics; never serialized by APIs/histories.
        self.decision_trace: list[dict] = []
        self.decision_count = self.exploit_activations = self.negative_target_incidents = self.out_of_bounds_target_incidents = 0

    def decide(self, observation: Observation) -> Action:
        return self.baseline.decide(observation)

    def decide_decision(self, observation: DecisionObservation) -> Action:
        self.decision_count += 1
        baseline = self.baseline.decide_decision(observation)
        self.last_baseline_explanation = self.baseline.last_explanation
        action, explanation = self.engine.apply(observation, baseline, self.last_baseline_explanation)
        self.last_explanation = explanation
        profile = observation.opponent_profile
        estimate = None
        if profile and explanation.statistic:
            source = getattr(profile, "street_statistics", {}).get(observation.decision_state.street, {}) if explanation.statistic in {"fold_to_bet", "call_vs_bet"} else getattr(profile, "statistics", {})
            estimate = source.get(explanation.statistic) if isinstance(source, dict) else None
        self.decision_trace.append({
            "hand_number": observation.decision_state.hand_number,
            "street": observation.decision_state.street, "pot": observation.decision_state.pot,
            "amount_to_call": observation.decision_state.amount_to_call,
            "hand_strength_category": getattr(self.last_baseline_explanation, "hand_strength_category", None),
            "profile_hands_observed": getattr(profile, "hands_observed", 0) if profile else 0,
            "baseline_action": baseline.type, "final_action": action.type,
            "exploit_applied": explanation.exploit_applied,
            "category": explanation.category, "statistic": explanation.statistic,
            "opportunities": explanation.opportunities, "confidence": explanation.confidence,
            "occurrences": getattr(estimate, "occurrences", None), "raw_frequency": getattr(estimate, "raw_frequency", None),
            "smoothed_frequency": explanation.smoothed_frequency, "final_target": action.amount,
            "signal_strength": explanation.signal_strength, "adjustment_level": explanation.adjustment_level,
            "rejection_reason": None if explanation.exploit_applied else explanation.primary_rationale,
        })
        self.exploit_activations += int(explanation.exploit_applied)
        if action.amount is not None:
            s = observation.decision_state
            self.negative_target_incidents += int(action.amount < 0)
            self.out_of_bounds_target_incidents += int(action.amount > s.maximum_legal_target or (s.minimum_legal_target is not None and action.amount < s.minimum_legal_target))
        return action
