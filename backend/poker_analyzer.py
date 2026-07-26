"""Pure poker-analysis functions; Treys stays isolated behind TreysAdapter."""
from __future__ import annotations
from itertools import combinations
import random
import time
from typing import Iterable
from treys import Card, Evaluator

RANKS = "23456789TJQKA"
SUITS = "shdc"
FULL_DECK = tuple(f"{r}{s}" for r in RANKS for s in SUITS)
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}

class TreysAdapter:
    def __init__(self): self.evaluator = Evaluator()
    def score(self, hole: list[str], board: list[str]) -> int:
        return self.evaluator.evaluate([Card.new(c) for c in hole], [Card.new(c) for c in board])
    def category(self, hole: list[str], board: list[str]) -> str:
        return self.evaluator.class_to_string(self.evaluator.get_rank_class(self.score(hole, board)))

EVALUATOR = TreysAdapter()
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
