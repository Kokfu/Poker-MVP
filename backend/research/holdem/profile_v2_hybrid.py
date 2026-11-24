"""Research-only selection between public V2 evidence and an incumbent forecast."""
from collections import Counter
from fractions import Fraction
from typing import Literal, NamedTuple

from research.holdem.opponent_profile_v2 import ProfileV2, Situation, extract, forecast

MIN_REPLIES = 20
Coverage = Literal["supported", "sparse", "unsupported"]


class Evidence(NamedTuple):
    coverage: Coverage
    opportunities: int
    replies: int


def wager_key(context: Situation, collectible: int, matched_pot: int):
    if collectible <= 0 or matched_pot <= 0:
        return None
    return context, Fraction(collectible, matched_pot)


class EvidenceProfile:
    """Replay the same completed public histories into V2 and its coverage index."""

    def __init__(self, opponent_id: str):
        self.v2 = ProfileV2(opponent_id)
        self._opportunities = Counter()
        self._replies = Counter()

    def update(self, source_hand_id, history, seat):
        if not self.v2.update(source_hand_id, history, seat):
            return False
        observations, _ = extract(history, seat)
        for row in observations:
            key = wager_key(row.situation, row.collectible, row.matched_pot)
            if key is not None:
                self._opportunities[key] += 1
                if row.response is not None:
                    self._replies[key] += 1
        return True

    def evidence(self, context, collectible, matched_pot):
        key = wager_key(context, collectible, matched_pot)
        replies = self._replies[key]
        coverage = ("supported" if replies >= MIN_REPLIES else
                    "sparse" if replies else "unsupported")
        return Evidence(coverage, self._opportunities[key], replies)


def hybrid_forecast(profile, context, collectible, matched_pot, incumbent):
    """Return the selected law and evidence, preserving the fallback object itself.

    The incumbent is a zero-argument callable supplying its normal legal forecast.
    The public situation already contains the exact legal response-class mask.
    """
    evidence = (profile.evidence(context, collectible, matched_pot)
                if profile is not None else Evidence("unsupported", 0, 0))
    if evidence.coverage == "supported":
        return forecast(profile.v2, context, True), evidence
    return incumbent(), evidence
