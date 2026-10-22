"""Pure poker-analysis functions; hand evaluators stay isolated behind adapters.

``TreysAdapter`` is the accepted reference evaluator.  ``Eval7Adapter`` is the
fast production evaluator: it evaluates with eval7 and translates every result
into the identical Treys rank (1 = royal flush, 7462 = worst high card), so all
comparisons, categories, and seeded results are unchanged.
"""
from __future__ import annotations
from collections import Counter
from itertools import combinations, combinations_with_replacement
import os
import random
import time
from typing import Iterable
from treys import Card, Evaluator

RANKS = "23456789TJQKA"
SUITS = "shdc"
FULL_DECK = tuple(f"{r}{s}" for r in RANKS for s in SUITS)
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
DISTINCT_HAND_CLASSES = 7462

class TreysAdapter:
    name = "treys"
    def __init__(self): self.evaluator = Evaluator()
    def score(self, hole: list[str], board: list[str]) -> int:
        return self.evaluator.evaluate([Card.new(c) for c in hole], [Card.new(c) for c in board])
    def category(self, hole: list[str], board: list[str]) -> str:
        return self.evaluator.class_to_string(self.evaluator.get_rank_class(self.score(hole, board)))

def hand_class_representatives() -> tuple[tuple[str, ...], ...]:
    """One five-card hand for each of the 7,462 distinct poker hand classes."""
    hands: list[tuple[str, ...]] = []
    for ranks in combinations_with_replacement(RANKS, 5):
        counts = Counter(ranks)
        if max(counts.values()) > 4:
            continue
        # Every rank group starts on a different suit and repeated ranks use
        # successive suits, so there are no duplicate cards and no flush.
        seen: Counter[str] = Counter()
        groups = {rank: index for index, rank in enumerate(sorted(counts))}
        cards = []
        for rank in ranks:
            cards.append(rank + SUITS[(groups[rank] + seen[rank]) % 4]); seen[rank] += 1
        hands.append(tuple(cards))
    for ranks in combinations(RANKS, 5):
        hands.append(tuple(rank + SUITS[0] for rank in ranks))
    return tuple(hands)

class Eval7Adapter:
    """eval7 speed with Treys-identical ranks and category strings."""
    name = "eval7"
    def __init__(self, reference: TreysAdapter | None = None):
        import eval7
        self.reference = reference or TreysAdapter()
        self._evaluate = eval7.evaluate
        self._cards = {card: eval7.Card(card) for card in FULL_DECK}
        self._rank_for: dict[int, int] = {}
        for hand in hand_class_representatives():
            value = self._evaluate([self._cards[card] for card in hand])
            rank = self.reference.score(list(hand[:2]), list(hand[2:]))
            if self._rank_for.setdefault(value, rank) != rank:
                raise RuntimeError("eval7 and Treys disagree on hand-class equivalence")
        if len(self._rank_for) != DISTINCT_HAND_CLASSES or len(set(self._rank_for.values())) != DISTINCT_HAND_CLASSES:
            raise RuntimeError("eval7/Treys rank translation is not a bijection")
    def score(self, hole: list[str], board: list[str]) -> int:
        cards = hole + board
        # Invalid counts and duplicate cards (callers may probe impossible
        # combos) keep the reference's exact errors and values.
        if not 5 <= len(cards) <= 7 or len(set(cards)) != len(cards):
            return self.reference.score(hole, board)
        lookup = self._cards
        return self._rank_for[self._evaluate([lookup[c] for c in cards])]
    def category(self, hole: list[str], board: list[str]) -> str:
        evaluator = self.reference.evaluator
        return evaluator.class_to_string(evaluator.get_rank_class(self.score(hole, board)))

def _default_evaluator() -> TreysAdapter | Eval7Adapter:
    # POKER_EVALUATOR=treys forces the reference implementation for debugging.
    return TreysAdapter() if os.environ.get("POKER_EVALUATOR", "").lower() == "treys" else Eval7Adapter()

EVALUATOR = _default_evaluator()
STRAIGHTS = [set(range(s, s + 5)) for s in range(2, 11)] + [{14, 2, 3, 4, 5}]

def street_for(board: list[str]) -> str: return {0: "Preflop", 3: "Flop", 4: "Turn", 5: "River"}[len(board)]
def _suit(s: str) -> str: return {"s":"♠", "h":"♥", "d":"♦", "c":"♣"}[s]
def _rank(v: int) -> str: return next(r for r, value in RANK_VALUE.items() if value == v)

def starting_hand_label(cards: list[str]) -> str:
    a, b = sorted(cards, key=lambda c: RANK_VALUE[c[0]], reverse=True)
    if a[0] == b[0]: quality = "premium pocket pair" if a[0] in "AKQJ" else "pocket pair"
    elif a[1] == b[1] and a[0] in "AKQJ" and b[0] in "AKQJT": quality = "suited Broadway starting hand"
    elif a[1] != b[1] and {a[0], b[0]} == {"7", "2"}: quality = "offsuit weak starting hand"
    else: quality = "suited starting hand" if a[1] == b[1] else "offsuit starting hand"
    return f"{a[0]}{_suit(a[1])} {b[0]}{_suit(b[1])} — {quality}"

def detect_draws(hero: list[str], board: list[str]) -> list[dict]:
    if len(board) not in (3, 4): return []
    cards, draws = hero + board, []
    for suit in SUITS:
        if sum(c[1] == suit for c in cards) == 4 and any(c[1] == suit for c in hero):
            draws.append({"type":"flush_draw", "outs_ranks":[], "personal_to_hero":True}); break
    ranks = {RANK_VALUE[c[0]] for c in cards}; hero_ranks = {RANK_VALUE[c[0]] for c in hero}
    # A completion is personal only if its straight includes a hero-hole rank.
    already = any(seq <= ranks and seq & hero_ranks for seq in STRAIGHTS)
    completes = {candidate for candidate in range(2, 15) if not already and any(seq <= (ranks | {candidate}) and seq & hero_ranks for seq in STRAIGHTS)}
    if len(completes) == 2: draws.append({"type":"open_ended_straight_draw", "outs_ranks":[_rank(x) for x in sorted(completes)], "personal_to_hero":True})
    elif len(completes) == 1: draws.append({"type":"gutshot_straight_draw", "outs_ranks":[_rank(next(iter(completes)))], "personal_to_hero":True})
    return draws

def pot_odds(pot: float, call: float) -> tuple[float, float]:
    final = pot + call
    return final, 0.0 if call == 0 else call / final

def recommendation(equity: float, required: float, call: float) -> str:
    if call == 0: return "Check"
    if equity < required - .02: return "Fold"
    if equity < required + .10: return "Call"
    return "Consider raising"

def calculate_equity(hero: list[str], board: list[str], iterations: int, seed: int | None = None) -> dict:
    unseen = [c for c in FULL_DECK if c not in hero + board]
    if len(board) == 5:
        deals: Iterable[tuple[str, ...]] = combinations(unseen, 2); method = "exact_enumeration"
    else:
        rng = random.Random(seed)
        # Stream samples instead of retaining up to 100,000 deals in memory.
        deals = (tuple(rng.sample(unseen, 2 + 5 - len(board))) for _ in range(iterations)); method = "monte_carlo"
    wins = ties = losses = total = 0
    for deal in deals:
        opponent, final_board = list(deal[:2]), board if len(board) == 5 else board + list(deal[2:])
        hs, os = EVALUATOR.score(hero, final_board), EVALUATOR.score(opponent, final_board); total += 1
        if hs < os: wins += 1
        elif hs == os: ties += 1
        else: losses += 1
    return {"win_rate":wins/total, "tie_rate":ties/total, "loss_rate":losses/total, "equity":(wins+ties/2)/total, "calculation_method":method, "hands_checked":total}

def analyze(hero: list[str], board: list[str], pot: float, call: float, iterations: int) -> dict:
    started = time.perf_counter(); result = calculate_equity(hero, board, iterations)
    final, required = pot_odds(pot, call); street = street_for(board); made = None if not board else EVALUATOR.category(hero, board)
    result.update({"street":street, "hand_label":starting_hand_label(hero) if not board else made, "made_hand":made, "draws":detect_draws(hero, board), "required_equity":required, "final_pot_if_call":final, "iterations":iterations if street != "River" else result["hands_checked"], "recommendation":recommendation(result["equity"], required, call), "elapsed_ms":round((time.perf_counter()-started)*1000), "disclaimer":"This recommendation is a basic educational heuristic and does not account for rake, opponent ranges, tournament ICM, player tendencies, or future-street strategy."})
    result["explanation"] = "A free action is available, so checking is the educational baseline." if call == 0 else ("Your estimated equity is above the required equity based on the pot odds." if result["equity"] >= required else "Your estimated equity is below the required equity based on the pot odds.")
    return result
