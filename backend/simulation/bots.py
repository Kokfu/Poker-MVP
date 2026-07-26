import random
from abc import ABC, abstractmethod
from .actions import Action
from .game_state import Observation
from poker_analyzer import EVALUATOR, calculate_equity, RANK_VALUE

class PokerBot(ABC):
    def __init__(self, seed: int | None = None, equity_iterations: int = 1000): self.rng=random.Random(seed); self.equity_iterations=equity_iterations
    @abstractmethod
    def decide(self, observation: Observation) -> Action: ...
    def _sizing(self, o: Observation, action: str) -> Action:
        minimum=o.minimum_target_to
        if minimum is None: return self._passive(o)
        desired=o.current_bet + o.amount_to_call + max(o.pot // 2, 1)
        target=max(minimum,min(desired,o.maximum_target_to))
        return Action(action, target)
    def _passive(self,o):
        if "check" in o.legal_actions: return Action("check")
        if "call" in o.legal_actions: return Action("call")
        if "all_in" in o.legal_actions: return Action("all_in")
        return Action("fold")

class RandomBot(PokerBot):
    def decide(self,o):
        concrete=[self._sizing(o,x) if x in ("bet","raise") else Action(x) for x in o.legal_actions]
        return self.rng.choice(concrete)

class TightBot(PokerBot):
    def decide(self,o):
        ranks=sorted((RANK_VALUE[c[0]] for c in o.hole_cards),reverse=True); strong=ranks[0]>=12 and (ranks[1]>=10 or ranks[0]==ranks[1])
        if o.street=="preflop":
            if o.amount_to_call and not strong: return Action("fold")
            if strong and ("raise" in o.legal_actions or "bet" in o.legal_actions): return self._sizing(o,"raise" if "raise" in o.legal_actions else "bet")
            return self._passive(o)
        made=EVALUATOR.category(o.hole_cards,o.community_cards)
        if o.amount_to_call and made in ("High Card","Pair") and o.amount_to_call > max(1,o.pot//3): return Action("fold")
        if made not in ("High Card","Pair") and ("raise" in o.legal_actions or "bet" in o.legal_actions): return self._sizing(o,"raise" if "raise" in o.legal_actions else "bet")
        return self._passive(o)

class AggressiveBot(PokerBot):
    def decide(self,o):
        aggressive="raise" if "raise" in o.legal_actions else "bet" if "bet" in o.legal_actions else None
        if aggressive and self.rng.random()<.65: return self._sizing(o,aggressive)
        if o.amount_to_call and self.rng.random()<.18: return Action("fold")
        return self._passive(o)

class EquityBot(PokerBot):
    def decide(self,o):
        if o.street=="preflop":
            ranks=sorted((RANK_VALUE[c[0]] for c in o.hole_cards),reverse=True); equity=.55 if ranks[0]>=12 or ranks[0]==ranks[1] else .40
        else: equity=calculate_equity(o.hole_cards,o.community_cards,self.equity_iterations,seed=self.rng.randrange(2**31))["equity"]
        required=0 if not o.amount_to_call else o.amount_to_call/(o.pot+o.amount_to_call)
        aggressive="raise" if "raise" in o.legal_actions else "bet" if "bet" in o.legal_actions else None
        if aggressive and equity>=max(.58,required+.12): return self._sizing(o,aggressive)
        if o.amount_to_call and equity<required-.03: return Action("fold")
        return self._passive(o)

BOT_TYPES={"random":RandomBot,"tight":TightBot,"aggressive":AggressiveBot,"equity":EquityBot}
