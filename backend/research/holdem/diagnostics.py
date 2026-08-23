"""Deterministic coverage and compression diagnostics for Hold'em abstraction."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from simulation.decision_state import DecisionObservation, DecisionState

from .abstraction import CARD_BUCKETS, HoldemAbstraction, _geometry, card_bucket, concrete_state_key


def _state(item: DecisionState | DecisionObservation) -> DecisionState:
    return item.decision_state if isinstance(item, DecisionObservation) else item


def abstraction_diagnostics(items: Iterable[DecisionState | DecisionObservation]) -> dict:
    """Audit a deterministic supplied hand set without sampling or RNG use."""
    states = tuple(_state(item) for item in items)
    concrete = {concrete_state_key(state) for state in states}
    abstract = {HoldemAbstraction.information_set(state) for state in states}
    occupancy = Counter(card_bucket(state) for state in states)
    geometry_occupancy: dict[str, dict[str, int]] = {
        field: {} for field in (
            "pot_bb", "spr", "call_pressure", "hero_commitment",
            "opponent_commitment", "raises_this_street", "raising_reopened",
        )
    }
    for state in states:
        for field, value in _geometry(state).items():
            counts = geometry_occupancy[field]
            label = str(value).lower() if isinstance(value, bool) else str(value)
            counts[label] = counts.get(label, 0) + 1
    mapping_errors: list[str] = []
    represented = 0
    possible = 0
    concretization_attempts = 0
    for state in states:
        mapped = HoldemAbstraction.abstract_actions(state)
        mapped_types = {action.action_type for action in mapped}
        possible += len(state.legal_actions)
        represented += sum(action in mapped_types for action in state.legal_actions)
        for action in mapped:
            concretization_attempts += 1
            try:
                HoldemAbstraction.concretize(state, action)
            except ValueError as exc:
                mapping_errors.append(str(exc))
    total = len(states)
    overloaded = sorted(
        bucket for bucket, count in occupancy.items()
        if total >= 10 and count / total > .70
    )
    return {
        "sampled_states": total,
        "concrete_states": len(concrete),
        "abstract_states": len(abstract),
        "compression_ratio": (len(concrete) / len(abstract)) if abstract else 0.0,
        "bucket_occupancy": dict(sorted(occupancy.items())),
        "geometry_occupancy": {
            field: dict(sorted(counts.items()))
            for field, counts in geometry_occupancy.items()
        },
        "empty_card_buckets": [bucket for bucket in CARD_BUCKETS if not occupancy[bucket]],
        "overloaded_card_buckets": overloaded,
        "action_abstraction": {
            "legal_action_slots": possible,
            "represented_slots": represented,
            "coverage": represented / possible if possible else 1.0,
            "mapping_errors": mapping_errors,
            "mapping_error_count": len(mapping_errors),
            "concretization_attempts": concretization_attempts,
        },
    }
