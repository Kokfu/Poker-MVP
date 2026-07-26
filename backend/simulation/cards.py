import random
from poker_analyzer import FULL_DECK

class Deck:
    def __init__(self, seed: int | None = None):
        self.cards = list(FULL_DECK)
        random.Random(seed).shuffle(self.cards)
    def deal(self, count: int = 1) -> list[str]:
        if count > len(self.cards): raise ValueError("Not enough cards in deck")
        result, self.cards = self.cards[:count], self.cards[count:]
        return result
