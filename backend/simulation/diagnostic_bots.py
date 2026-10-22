"""Non-registered deterministic public-behavior archetypes for research tests."""
from .actions import Action
from .bots import PokerBot

class OverFolderBot(PokerBot):
    def decide(self, o):
        # Continue preflop to create legitimate postflop fold-to-bet samples.
        if o.amount_to_call and o.street == "preflop" and "call" in o.legal_actions: return Action("call")
        if o.amount_to_call and "fold" in o.legal_actions: return Action("fold")
        return self._passive(o)

class CallingStationBot(PokerBot):
    def decide(self, o):
        if o.amount_to_call and "call" in o.legal_actions: return Action("call")
        return self._passive(o)

class PassiveCheckCallBot(CallingStationBot):
    """Legal check/call archetype for low-aggression public-history tests."""

class OverAggressorBot(PokerBot):
    def decide(self, o):
        # Bet whenever checked to, but call raises to keep the diagnostic
        # horizon long enough for public aggression samples to mature.
        if not o.amount_to_call and "bet" in o.legal_actions: return self._sizing(o, "bet")
        if o.amount_to_call and "call" in o.legal_actions: return Action("call")
        return self._passive(o)
