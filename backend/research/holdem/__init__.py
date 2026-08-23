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
from .cfr import HoldemSubgameCFRTrainer
from .diagnostics_4d import training_report, tree_diagnostics, validate_tree
from .subgame import HoldemSubgameState, chance_states, subgame_convention

__all__ = [
    "AbstractAction",
    "HoldemAbstraction",
    "abstraction_diagnostics",
    "card_bucket",
    "concrete_state_key",
    "HoldemSubgameCFRTrainer",
    "HoldemSubgameState",
    "chance_states",
    "subgame_convention",
    "training_report",
    "tree_diagnostics",
    "validate_tree",
]
