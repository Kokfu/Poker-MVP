"""RangeAwareExpertBot: ExpertRuleBot plus a public range-equity layer."""
from __future__ import annotations

from hashlib import sha256

from .actions import Action
from .bots import PokerBot
from .decision_state import DecisionObservation
from .expert_bot import ExpertDecisionExplanation, ExpertRuleBot
from .game_state import Observation
from .range_strategy import RangeAwareDecisionExplanation, RangeStrategyAdjustmentEngine


class RangeAwareExpertBot(PokerBot):
    """Keeps ExpertRuleBot independently intact and applies bounded adjustments."""
    range_equity_iterations = 500
    uses_range_equity = True

    def __init__(self, seed: int | None = None, equity_iterations: int = 1000, range_equity_iterations: int | None = None):
        super().__init__(seed, equity_iterations)
        self.baseline = ExpertRuleBot(seed, equity_iterations)
        self.adjustment_engine = RangeStrategyAdjustmentEngine()
        # Evaluation/test callers already use ``equity_iterations`` to set a
        # bounded simulation budget.  Preserve the 500 production default but
        # honour a deliberately smaller supplied budget without new API shape.
        self.range_equity_iterations = min(500, equity_iterations) if range_equity_iterations is None else range_equity_iterations
        self.range_equity_seed_base = 0 if seed is None else seed
        self.last_baseline_explanation: ExpertDecisionExplanation | None = None
        self.last_explanation: RangeAwareDecisionExplanation | None = None
        self.decision_count = self.range_calculations = self.exact_equity_calculations = self.monte_carlo_equity_calculations = self.adjustment_count = 0
        self.range_skipped = self.baseline_fallbacks = 0
        self.adjustment_categories: dict[str, int] = {}
        self.decision_trace: list[dict] = []

    def decide(self, observation: Observation) -> Action:
        return self.baseline.decide(observation)

    def range_equity_seed(self, state) -> int:
        """Stable SHA-256 seed; it never consumes the bot or deck RNG."""
        value = "|".join(str(item) for item in (self.range_equity_seed_base, state.match_id or "", state.hand_id, state.hand_number, state.acting_player, state.street, state.current_street_actions.__len__()))
        return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big")

    def decide_decision(self, observation: DecisionObservation) -> Action:
        self.decision_count += 1
        baseline = self.baseline.decide_decision(observation)
        self.last_baseline_explanation = self.baseline.last_explanation
        if observation.range_equity is not None:
            self.range_calculations += 1
            self.exact_equity_calculations += int(observation.range_equity.method == "exact")
            self.monte_carlo_equity_calculations += int(observation.range_equity.method == "monte_carlo")
        else:
            self.range_skipped += 1
        action, explanation = self.adjustment_engine.apply(observation, baseline)
        self.last_explanation = explanation
        self.adjustment_count += int(explanation.adjustment_applied)
        self.baseline_fallbacks += int(explanation.concentration_gate == "unavailable")
        if explanation.adjustment_category:
            self.adjustment_categories[explanation.adjustment_category] = self.adjustment_categories.get(explanation.adjustment_category, 0) + 1
        self.decision_trace.append({
            "hand_number": observation.decision_state.hand_number, "street": observation.decision_state.street,
            "hero_cards": observation.decision_state.hole_cards, "board": observation.decision_state.board_cards,
            "pot": observation.decision_state.pot, "amount_to_call": observation.decision_state.amount_to_call,
            "baseline_action": baseline.type, "baseline_target": baseline.amount, "final_action": action.type, "final_target": action.amount,
            "range_equity": explanation.range_equity, "required_equity": explanation.required_equity,
            "equity_margin": explanation.equity_margin, "active_combos": explanation.active_combos,
            "effective_combo_count": explanation.effective_combo_count, "normalized_entropy": explanation.normalized_entropy,
            "method": explanation.method, "iterations": explanation.iterations, "category": explanation.adjustment_category,
            "gate": explanation.concentration_gate, "rationale": explanation.rationale,
        })
        return action
