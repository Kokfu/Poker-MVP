"""Public-history opponent tendency summaries for heads-up matches.

This module intentionally consumes only completed ``HandHistory`` action events.
It is deterministic, contains no card/deck access, and is not a strategy engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Literal

from .history import HandHistory, HandHistoryEvent

Confidence = Literal["very_low", "low", "medium", "high"]
PlayerType = Literal["unknown", "tight_passive", "tight_aggressive", "loose_passive", "loose_aggressive", "balanced_or_unclear"]
STREETS = ("flop", "turn", "river")
ALPHA = 1
BETA = 1
CONFIDENCE_THRESHOLDS = ((5, "very_low"), (20, "low"), (50, "medium"), (float("inf"), "high"))


def confidence_for(opportunities: int) -> Confidence:
    for limit, label in CONFIDENCE_THRESHOLDS:
        if opportunities < limit:
            return label  # type: ignore[return-value]
    return "high"


@dataclass
class OpponentStats:
    opportunities: int = 0
    occurrences: int = 0

    def observe(self, occurred: bool) -> None:
        self.opportunities += 1
        self.occurrences += int(occurred)

    def snapshot(self) -> "StatEstimate":
        raw = self.occurrences / self.opportunities if self.opportunities else 0.0
        return StatEstimate(self.opportunities, self.occurrences, raw, (self.occurrences + ALPHA) / (self.opportunities + ALPHA + BETA), confidence_for(self.opportunities))


@dataclass(frozen=True)
class StatEstimate:
    opportunities: int
    occurrences: int
    raw_frequency: float
    smoothed_frequency: float
    confidence: Confidence


@dataclass
class SizingProfile:
    opportunities: int = 0
    samples: int = 0
    small: int = 0
    medium: int = 0
    large: int = 0
    overbet: int = 0
    _total_fraction: float = 0.0

    def observe(self, fraction: float | None) -> None:
        self.opportunities += 1
        if fraction is None or not isfinite(fraction) or fraction < 0:
            return
        self.samples += 1
        self._total_fraction += fraction
        if fraction <= .40: self.small += 1
        elif fraction <= .75: self.medium += 1
        elif fraction <= 1.25: self.large += 1
        else: self.overbet += 1

    def as_dict(self) -> dict[str, Any]:
        return {"opportunities": self.opportunities, "samples": self.samples, "buckets": {"small": self.small, "medium": self.medium, "large": self.large, "overbet": self.overbet}, "mean_fraction": self._total_fraction / self.samples if self.samples else 0.0}


@dataclass(frozen=True)
class OpponentProfileSnapshot:
    hands_observed: int
    decisions_observed: int
    statistics: dict[str, StatEstimate]
    street_statistics: dict[str, dict[str, StatEstimate]]
    sizing: dict[str, Any]
    classification: PlayerType

    def as_dict(self) -> dict[str, Any]:
        return _safe(asdict(self))


@dataclass
class OpponentModel:
    """Accumulates one player's public completed-hand behavior.

    Heads-up denominators: VPIP is a voluntary preflop call/bet/raise/all-in
    opportunity (blinds excluded); PFR is a preflop decision where raising is
    legal; limp is an unopened preflop decision; 3-bet is a response to exactly
    one prior voluntary preflop raise. Fold-to-* means facing a public wager.
    """
    player: str
    hands_observed: int = 0
    decisions_observed: int = 0
    stats: dict[str, OpponentStats] = field(default_factory=dict)
    street_stats: dict[str, dict[str, OpponentStats]] = field(default_factory=dict)
    sizing: SizingProfile = field(default_factory=SizingProfile)
    street_sizing: dict[str, SizingProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("fold", "check", "call", "bet", "raise", "all_in", "aggressive", "passive", "vpip", "preflop_raise", "limp", "three_bet", "fold_to_raise", "fold_to_three_bet"):
            self.stats.setdefault(name, OpponentStats())
        for street in STREETS:
            self.street_stats.setdefault(street, {name: OpponentStats() for name in ("bet", "fold_to_bet", "call_vs_bet", "raise_vs_bet", "check", "check_raise")})
            self.street_sizing.setdefault(street, SizingProfile())

    def update(self, history: HandHistory) -> None:
        """Consume a completed public history once; no hidden fields are read."""
        events = [event for event in history.events if event.event_type == "action_taken" and event.actor in {"a", "b"} and event.applied_action not in {None, "illegal_action"}]
        self.hands_observed += 1
        preflop_actions: list[HandHistoryEvent] = []
        street_actions: dict[str, list[HandHistoryEvent]] = {street: [] for street in STREETS}
        for event in events:
            if event.actor != self.player:
                if event.street == "preflop": preflop_actions.append(event)
                elif event.street in street_actions: street_actions[event.street].append(event)
                continue
            action = event.applied_action or ""
            self.decisions_observed += 1
            for name in ("fold", "check", "call", "bet", "raise", "all_in"):
                self.stats[name].observe(action == name)
            self.stats["aggressive"].observe(action in {"bet", "raise", "all_in"})
            self.stats["passive"].observe(action in {"check", "call", "fold"})
            if event.street == "preflop":
                prior = preflop_actions
                prior_raises = [item for item in prior if item.applied_action in {"bet", "raise", "all_in"} and (item.current_highest_bet_after or 0) > (item.current_highest_bet_before or 0)]
                voluntary = action in {"call", "bet", "raise", "all_in"}
                self.stats["vpip"].observe(voluntary)
                can_raise = bool(event.legal_actions and any(item in event.legal_actions for item in ("bet", "raise", "all_in")))
                if can_raise: self.stats["preflop_raise"].observe(action in {"bet", "raise", "all_in"} and (event.current_highest_bet_after or 0) > (event.current_highest_bet_before or 0))
                unopened = not prior_raises and (event.amount_to_call_before or 0) <= history.big_blind_amount - (event.street_commitment_a_before if self.player == "a" else event.street_commitment_b_before)
                if unopened: self.stats["limp"].observe(action == "call")
                if len(prior_raises) == 1: self.stats["three_bet"].observe(action in {"raise", "all_in"} and (event.current_highest_bet_after or 0) > (event.current_highest_bet_before or 0))
                if prior_raises and action == "fold":
                    self.stats["fold_to_raise"].observe(True)
                    if len(prior_raises) >= 2: self.stats["fold_to_three_bet"].observe(True)
                elif prior_raises:
                    self.stats["fold_to_raise"].observe(False)
                    if len(prior_raises) >= 2: self.stats["fold_to_three_bet"].observe(False)
                preflop_actions.append(event)
            elif event.street in STREETS:
                street = event.street; bucket = self.street_stats[street]; prior = street_actions[street]
                facing = (event.amount_to_call_before or 0) > 0
                if facing:
                    bucket["fold_to_bet"].observe(action == "fold")
                    bucket["call_vs_bet"].observe(action == "call")
                    bucket["raise_vs_bet"].observe(action in {"raise", "all_in"} and (event.current_highest_bet_after or 0) > (event.current_highest_bet_before or 0))
                else:
                    bucket["check"].observe(action == "check")
                    bucket["bet"].observe(action in {"bet", "all_in"} and (event.current_highest_bet_before or 0) == 0)
                checked_then_faced_bet = any(item.actor == self.player and item.applied_action == "check" for item in prior) and facing
                if checked_then_faced_bet: bucket["check_raise"].observe(action in {"raise", "all_in"} and (event.current_highest_bet_after or 0) > (event.current_highest_bet_before or 0))
                street_actions[street].append(event)
            if action in {"bet", "raise", "all_in"} and (event.current_highest_bet_after or 0) > (event.current_highest_bet_before or 0):
                increment = (event.target_total or event.current_highest_bet_after or 0) - (event.current_highest_bet_before or 0)
                fraction = increment / event.pot_before if event.pot_before > 0 else None
                self.sizing.observe(fraction)
                if event.street in STREETS: self.street_sizing[event.street].observe(fraction)

    def snapshot(self) -> OpponentProfileSnapshot:
        stats = {name: value.snapshot() for name, value in self.stats.items()}
        streets = {street: {name: value.snapshot() for name, value in values.items()} for street, values in self.street_stats.items()}
        return OpponentProfileSnapshot(self.hands_observed, self.decisions_observed, stats, streets, {"overall": self.sizing.as_dict(), "by_street": {street: profile.as_dict() for street, profile in self.street_sizing.items()}}, self._classification(stats))

    def _classification(self, stats: dict[str, StatEstimate]) -> PlayerType:
        vpip, aggression = stats["vpip"], stats["aggressive"]
        if self.hands_observed < 20 or vpip.opportunities < 20: return "unknown"
        loose = vpip.smoothed_frequency >= .50
        aggressive = aggression.smoothed_frequency >= .35
        if loose and aggressive: return "loose_aggressive"
        if loose and not aggressive: return "loose_passive"
        if not loose and aggressive: return "tight_aggressive"
        if not loose and not aggressive: return "tight_passive"
        return "balanced_or_unclear"


def _safe(value: Any) -> Any:
    if isinstance(value, float): return value if isfinite(value) else 0.0
    if isinstance(value, dict): return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(item) for item in value]
    return value
