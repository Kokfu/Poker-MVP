"""Phase 4G adapter; uses the accepted generic external-sampling core."""
from __future__ import annotations
from time import perf_counter
from ..mccfr import ExternalSamplingMCCFRTrainer
from .cfr import HoldemSubgameCFRTrainer
from .river_subgame import RIVER_RESEARCH_DECK, RiverHoldemState, river_chance_states
from .diagnostics_4g import reachable_infoset_universe

class RiverChanceExternalSamplingMCCFRTrainer(ExternalSamplingMCCFRTrainer):
    def __init__(self, seed=0, roots: tuple[RiverHoldemState,...] | None=None, full_tree_node_count=None):
        supplied = roots or river_chance_states()
        super().__init__(supplied, seed, action_label=lambda a:a.label, chance_label=lambda s:"/".join((*s.player0_cards,*s.player1_cards)), full_tree_node_count=full_tree_node_count)
        self.infoset_streets: dict[str,str] = {}
    def _node(self,state):
        node=super()._node(state); prior=self.infoset_streets.setdefault(node.key,state.street)
        if prior != state.street: raise AssertionError("information set aliases distinct streets")
        return node
    def _distribution(self,state):
        node=self.infosets.get(state.information_set())
        return node.average() if node else {a:1/len(state.legal_actions) for a in state.legal_actions}
    def profile_ev(self, roots=None):
        def walk(state):
            if state.terminal:return state.utility_p0()
            if state.chance:return sum(p*walk(child) for _,child,p in state.chance_outcomes())
            return sum(self._distribution(state)[a]*walk(state.apply(a)) for a in state.legal_actions)
        selected=tuple(roots) if roots is not None else self.roots
        return sum(walk(root) for root in selected)/len(selected)
    def reachable_infosets(self): return dict(reachable_infoset_universe())
    def all_information_set_keys(self): return tuple(self.reachable_infosets())
    def chance_coverage(self):
        turn={card:self.future_chance_stage_sample_counts[f"turn:{card}"] for card in RIVER_RESEARCH_DECK}
        river={card:self.future_chance_stage_sample_counts[f"river:{card}"] for card in RIVER_RESEARCH_DECK}
        # Both cards are public by the river node; retain the actual selected
        # turn rather than inferring a pair from branching traversal order.
        pairs={}
        for row in self.last_trajectories:
            for item in row["opponent_samples"]:
                if item.get("chance_street") == "river":
                    pair=(item["chance_parent_public_card"],item["future_chance"])
                    pairs[pair]=pairs.get(pair,0)+1
        return {"turn":{"eligible_cards":list(RIVER_RESEARCH_DECK),"per_card_sample_counts":turn,"unseen_turns":[c for c,n in turn.items() if not n]},"river":{"conditional_eligible_cards":"deck excluding flop, private cards, selected turn","per_card_sample_counts":river,"unseen_reachable_river_cards":[c for c,n in river.items() if not n],"observed_turn_river_pairs":pairs}}

def river_training_report(checkpoints=(100,1000,10000),seed=7,full_tree_node_count=None):
    trainer=RiverChanceExternalSamplingMCCFRTrainer(seed,full_tree_node_count=full_tree_node_count); rows=[]; prior=0; previous=None
    for checkpoint in checkpoints:
        started=perf_counter(); trainer.train(checkpoint-prior); elapsed=perf_counter()-started; policy=trainer.average_strategy(); universe=trainer.reachable_infosets(); diag=trainer.diagnostics(universe)
        visited=set(trainer.infoset_visit_counts); zero=set(diag["zero_visit_information_sets"])
        by_street={street:{"reachable":sum(s==street for s in universe.values()),"visited":sum(universe.get(k)==street for k in visited),"zero_visit":sum(universe.get(k)==street for k in zero)} for street in ("flop","turn","river")}
        rows.append({"logical_iterations":checkpoint,"traversals":diag["traversals"],"runtime_seconds":elapsed,"iterations_per_second":(checkpoint-prior)/elapsed if elapsed else float("inf"),"visited_nodes":diag["visited_nodes"],"nodes_per_iteration":diag["visited_nodes_per_iteration"],"information_sets_touched":diag["information_sets_touched"],"reachable_information_sets":len(universe),"visited_information_sets":len(visited),"zero_visit_sets":sorted(zero),"zero_visit_information_sets":len(zero),"coverage_percent":100*len(visited)/len(universe),"information_sets_by_street":by_street,"profile_ev_player0_representative_private_root":trainer.profile_ev((trainer.roots[0],)),"average_strategy_stability_l1":None if previous is None else _l1(previous,policy),"finite":diag["finite"],"chance_coverage":trainer.chance_coverage()}); previous,prior=policy,checkpoint
    return {"phase_4g_research_schema_version":"1.0","profile_ev_scope":"exact conditional public-chance EV for one representative private root; not full Phase 4G EV","seed":seed,"checkpoints":rows}
def _l1(a,b): return sum(abs(a.get(k,{}).get(x,0)-b.get(k,{}).get(x,0)) for k in set(a)|set(b) for x in set(a.get(k,{}))|set(b.get(k,{})))
