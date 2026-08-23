"""Research-only, player-visible heads-up Hold'em abstractions.

This package deliberately consumes immutable ``DecisionState`` snapshots.  It
does not train a solver, register a bot, or participate in ``HandEngine`` rule
evaluation.
"""

from .abstraction import (
    AbstractAction,
    HoldemAbstraction,
    card_bucket,
    concrete_state_key,
)
from .diagnostics import abstraction_diagnostics

__all__ = [
    "AbstractAction",
    "HoldemAbstraction",
    "abstraction_diagnostics",
    "card_bucket",
    "concrete_state_key",
]
