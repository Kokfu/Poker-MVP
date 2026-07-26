from dataclasses import dataclass, field
@dataclass
class Statistics:
    simulation_id:str; seed:int|None; bot_a:str; bot_b:str; bb:int; hands_played:int=0; bot_a_wins:int=0; bot_b_wins:int=0; ties:int=0; bot_a_net_chips:int=0; bot_b_net_chips:int=0; showdowns:int=0; fold_ended_hands:int=0; illegal_actions:int=0; duration_ms:float=0; action_counts:dict=field(default_factory=dict); street_reached_counts:dict=field(default_factory=dict)
    def record_action(self,player,action): self.action_counts.setdefault(player,{}); self.action_counts[player][action]=self.action_counts[player].get(action,0)+1
    def as_dict(self):
        return {**self.__dict__,"bot_a_bb_per_100":self.bot_a_net_chips/self.bb*100/self.hands_played if self.hands_played else 0,"bot_b_bb_per_100":self.bot_b_net_chips/self.bb*100/self.hands_played if self.hands_played else 0,"average_hand_duration_ms":self.duration_ms/self.hands_played if self.hands_played else 0,"average_decision_time_ms":{}}
