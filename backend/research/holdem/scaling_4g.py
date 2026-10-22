"""Like-for-like operational comparison of the accepted 4F and 4G games."""
from __future__ import annotations

from time import perf_counter

from .diagnostics_4f import turn_tree_diagnostics
from .diagnostics_4g import river_tree_diagnostics, reachable_infoset_universe
from .turn_mccfr import TurnChanceExternalSamplingMCCFRTrainer
from .river_mccfr import RiverChanceExternalSamplingMCCFRTrainer
from .cfr import HoldemSubgameCFRTrainer


def phase_4f_vs_4g_scaling_report(iterations: int = 1_000, seed: int = 7) -> dict[str, object]:
    """Run both unchanged adapters with one logical iteration = two traversals."""
    if iterations < 1: raise ValueError("iterations must be positive")
    f_tree, g_tree = turn_tree_diagnostics(), river_tree_diagnostics()
    f = TurnChanceExternalSamplingMCCFRTrainer(seed); g = RiverChanceExternalSamplingMCCFRTrainer(seed)
    rows = {}
    f_exact = HoldemSubgameCFRTrainer(roots=f.roots)
    f_universe = {node.key: state.street for state, node in f_exact._state_nodes.items()}
    for name, trainer, tree, universe in (
        ("phase_4f", f, f_tree, f_universe),
        ("phase_4g", g, g_tree, dict(reachable_infoset_universe())),
    ):
        started = perf_counter(); trainer.train(iterations); runtime = perf_counter()-started
        diagnostics = trainer.diagnostics(universe)
        visited=set(trainer.infoset_visit_counts); zero=set(diagnostics["zero_visit_information_sets"])
        rows[name] = {"tree_nodes":tree["full_tree_node_count"],"chance_nodes":tree["chance_nodes"],"terminal_nodes":tree["terminal_nodes"],"reachable_information_sets":len(universe),"reachable_information_sets_by_street":{street:sum(value==street for value in universe.values()) for street in set(universe.values())},"logical_iterations":iterations,"traversals":diagnostics["traversals"],"visited_nodes":diagnostics["visited_nodes"],"nodes_per_logical_iteration":diagnostics["visited_nodes_per_iteration"],"runtime_seconds":runtime,"iterations_per_second":iterations/runtime,"traversals_per_second":diagnostics["traversals"]/runtime,"visited_information_sets":len(visited),"zero_visit_information_sets":len(zero),"strategy_table_entries":sum(len(node.actions) for node in trainer.infosets.values()),"strategy_regret_memory_bytes":diagnostics["estimated_infoset_memory_bytes"],"chance_coverage":trainer.turn_sampling_diagnostics() if name == "phase_4f" else trainer.chance_coverage(),"finite":diagnostics["finite"]}
    return {"scope":"operational scaling only; no strategy-strength or exploitability comparison","accounting":"one logical iteration equals one P0 traversal plus one P1 traversal","seed":seed,"phase_4f":rows["phase_4f"],"phase_4g":rows["phase_4g"]}
