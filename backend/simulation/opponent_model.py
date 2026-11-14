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


SIZE_BUCKETS = ("<=0.5", "0.5-1.0", ">1.0")


def size_bucket(ratio: float) -> str:
    """Bucket of a bet/raise: (raise amount) / (pot after the opponent's bet is matched).

    Edges as pre-registered for proposal B (autopilot/prereg-step-13.md): <=0.5, 0.5-1.0, >1.0."""
    if ratio <= 0.5:
        return SIZE_BUCKETS[0]
    return SIZE_BUCKETS[1] if ratio <= 1.0 else SIZE_BUCKETS[2]


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


@dataclass
class SizedStats:
    """How the modelled player responded to OUR bets/raises of one size bucket (proposal B)."""
    opportunities: int = 0
    folds: int = 0
    calls: int = 0
    raises: int = 0

    def observe(self, response: str) -> None:
        self.opportunities += 1
        self.folds += response == "fold"
        self.calls += response == "call"
        self.raises += response == "raise"


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
    # Proposal B (bet-size-conditioned reads): bucket -> SizedStats copy.  Read only by bots with
    # ``sized_reads``; never serialised (kept out of ``as_dict``) and ignored by equality.
    sized_statistics: dict[str, SizedStats] | None = field(default=None, compare=False)

    def as_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values.pop("sized_statistics", None)
        return _safe(values)


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
    sized_stats: dict[str, SizedStats] = field(default_factory=dict)  # postflop, pooled over streets (proposal B)

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
        self._observe_sized_responses(events)
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

    def _observe_sized_responses(self, events: list[HandHistoryEvent]) -> None:
        """Proposal B: the modelled player's fold/call/raise against each postflop bet or raise of the
        other player, bucketed by raise amount / pot after matching the modelled player's own bet."""
        mine = "a" if self.player == "a" else "b"
        for index, event in enumerate(events):
            if event.actor == self.player or event.street not in STREETS:
                continue
            if event.applied_action not in {"bet", "raise", "all_in"} or (event.current_highest_bet_after or 0) <= (event.current_highest_bet_before or 0):
                continue
            own = event.street_commitment_a_before if mine == "a" else event.street_commitment_b_before
            other = event.street_commitment_b_before if mine == "a" else event.street_commitment_a_before
            carried = event.pot_before - own - other
            ratio = ((event.current_highest_bet_after or 0) - own) / max(carried + 2 * own, 1)
            reply = next((item for item in events[index + 1:] if item.actor == self.player and item.street == event.street), None)
            if reply is None:
                continue
            raised = reply.applied_action in {"bet", "raise", "all_in"} and (reply.current_highest_bet_after or 0) > (reply.current_highest_bet_before or 0)
            response = "raise" if raised else "fold" if reply.applied_action == "fold" else "call"
            self.sized_stats.setdefault(size_bucket(ratio), SizedStats()).observe(response)

    def snapshot(self) -> OpponentProfileSnapshot:
        stats = {name: value.snapshot() for name, value in self.stats.items()}
        streets = {street: {name: value.snapshot() for name, value in values.items()} for street, values in self.street_stats.items()}
        return OpponentProfileSnapshot(self.hands_observed, self.decisions_observed, stats, streets, {"overall": self.sizing.as_dict(), "by_street": {street: profile.as_dict() for street, profile in self.street_sizing.items()}}, self._classification(stats), {bucket: SizedStats(v.opportunities, v.folds, v.calls, v.raises) for bucket, v in self.sized_stats.items()})

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
