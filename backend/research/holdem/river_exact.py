"""Small exact Phase 4G control; only action selection is restricted."""
from __future__ import annotations
from dataclasses import dataclass
from .river_subgame import RiverHoldemState
from .cfr import HoldemSubgameCFRTrainer
@dataclass(frozen=True)
class ReducedRiverState:
    base: RiverHoldemState; reverse_chance: bool=False
    terminal=property(lambda s:s.base.terminal); chance=property(lambda s:s.base.chance); acting_player=property(lambda s:s.base.acting_player); street=property(lambda s:s.base.street)
    chance_stage=property(lambda s:s.base.chance_stage)
    player0_cards=property(lambda s:s.base.player0_cards); player1_cards=property(lambda s:s.base.player1_cards)
    # The reduced game changes only available actions.  These read-only
    # delegates deliberately let the shared exhaustive diagnostics inspect the
    # authoritative physical-card and contribution state without duplicating
    # any poker transition rule.
    flop_history=property(lambda s:s.base.flop_history); turn_history=property(lambda s:s.base.turn_history); river_history=property(lambda s:s.base.river_history)
    turn_card=property(lambda s:s.base.turn_card); river_card=property(lambda s:s.base.river_card); deck=property(lambda s:s.base.deck)
    def information_set(self):return self.base.information_set()
    def utility_p0(self):return self.base.utility_p0()
    def utility(self,player):return self.base.utility(player)
    def remaining_turn_cards(self):return self.base.remaining_turn_cards()
    def remaining_river_cards(self):return self.base.remaining_river_cards()
    def chance_outcomes(self):
        rows=self.base.chance_outcomes(); rows=tuple(reversed(rows)) if self.reverse_chance else rows
        return tuple((label,ReducedRiverState(child,self.reverse_chance),prob) for label,child,prob in rows)
    @property
    def legal_actions(self):
        if self.terminal or self.chance:return ()
        history=self.base._current_history(); allowed={"check","bet"} if not history or history[-1].action_type=="check" else {"fold","call"}; out=[]; used=set()
        for action in self.base.legal_actions:
            if action.action_type in allowed and action.action_type not in used:out.append(action);used.add(action.action_type)
        return tuple(out)
    def apply(self,a):
        if a not in self.legal_actions:raise ValueError("illegal reduced action")
        return ReducedRiverState(self.base.apply(a),self.reverse_chance)
def reduced_river_roots(reverse_chance=False):
    # Two turns, then one conditional river each: smallest genuine sequential control.
    base=RiverHoldemState(("Ah","Ad"),("Kh","Kc"),deck=("Ah","Ad","Kh","Kc","Qs","Js","Ts"))
    return (ReducedRiverState(base,reverse_chance),)
def reduced_river_report(iterations=10):
    trainer=HoldemSubgameCFRTrainer("vanilla",roots=reduced_river_roots()).train(iterations)
    value=trainer.profile_ev()
    # Pure information-set BR enumeration is intentionally not attempted:
    # even this smallest real sequential-chance control has enough distinct
    # visible river states to make it intractable.  Its exact EV/tree checks
    # remain controls, never a Phase 4G exploitability claim.
    return {"scope":"reduced exact three-street validation only; not larger Phase 4G exploitability; constrained BR metrics intentionally omitted as intractable","private_deals":1,"information_sets":len(trainer.infosets),"metrics":{"player0_ev":value,"player1_ev":-value}}
