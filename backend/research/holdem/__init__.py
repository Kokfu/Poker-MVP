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
from .mccfr import HoldemSubgameExternalSamplingMCCFRTrainer, scaling_report
from .diagnostics_4d import training_report, tree_diagnostics, validate_tree
from .subgame import HoldemSubgameState, chance_states, subgame_convention
from .turn_subgame import TurnHoldemState, turn_chance_states, turn_subgame_convention
from .turn_mccfr import TurnChanceExternalSamplingMCCFRTrainer, turn_training_report
from .turn_exact import ReducedTurnState, reduced_turn_roots, reduced_turn_report
from .diagnostics_4f import turn_tree_diagnostics, validate_turn_tree
from .river_subgame import RiverHoldemState, river_chance_states, river_subgame_convention
from .river_mccfr import RiverChanceExternalSamplingMCCFRTrainer, river_training_report
from .river_exact import ReducedRiverState, reduced_river_roots, reduced_river_report
from .diagnostics_4g import river_tree_diagnostics, validate_river_tree
from .scaling_4g import phase_4f_vs_4g_scaling_report

__all__ = [
    "AbstractAction",
    "HoldemAbstraction",
    "abstraction_diagnostics",
    "card_bucket",
    "concrete_state_key",
    "HoldemSubgameCFRTrainer",
    "HoldemSubgameExternalSamplingMCCFRTrainer",
    "scaling_report",
    "HoldemSubgameState",
    "chance_states",
    "subgame_convention",
    "training_report",
    "tree_diagnostics",
    "validate_tree",
    "TurnHoldemState",
    "turn_chance_states",
    "turn_subgame_convention",
    "TurnChanceExternalSamplingMCCFRTrainer",
    "turn_training_report",
    "ReducedTurnState",
    "reduced_turn_roots",
    "reduced_turn_report",
    "turn_tree_diagnostics",
    "validate_turn_tree",
    "RiverHoldemState", "river_chance_states", "river_subgame_convention",
    "RiverChanceExternalSamplingMCCFRTrainer", "river_training_report",
    "ReducedRiverState", "reduced_river_roots", "reduced_river_report",
    "river_tree_diagnostics", "validate_river_tree",
    "phase_4f_vs_4g_scaling_report",
]
