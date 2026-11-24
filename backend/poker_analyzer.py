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
    ranks = {RANK_VALUE[c[0]] for c in cards}
    if any(straight <= ranks for straight in STRAIGHTS):
        return draws

    board_ranks = {RANK_VALUE[c[0]] for c in board}
    completions: dict[int, list[set[int]]] = {}
    for straight in STRAIGHTS:
        missing = straight - ranks
        if len(missing) != 1:
            continue
        out = next(iter(missing))
        held_ranks = straight - missing
        if not held_ranks <= board_ranks:
            completions.setdefault(out, []).append(held_ranks)

    outs = sorted(completions)
    if not outs:
        return draws
    if len(outs) == 1:
        draw_type = "gutshot_straight_draw"
    else:
        shared_run = any(run in completions[outs[1]] for run in completions[outs[0]])
        draw_type = "open_ended_straight_draw" if shared_run else "double_gutshot_straight_draw"
    draws.append({"type": draw_type, "outs_ranks": [_rank(out) for out in outs], "personal_to_hero": True})
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

MIN_OPPONENTS, MAX_OPPONENTS = 1, 8

def multiway_equity(hero: list[str], board: list[str], opponents: int, iterations: int = 20_000,
                    seed: int | None = None) -> dict[str, float]:
    """Hero's share of the pot against ``opponents`` random hands (ties split evenly)."""
    if not MIN_OPPONENTS <= opponents <= MAX_OPPONENTS:
        raise ValueError(f"opponents must be {MIN_OPPONENTS}-{MAX_OPPONENTS}")
    unseen = [card for card in FULL_DECK if card not in set(hero) | set(board)]
    rng = random.Random(seed)
    missing = 5 - len(board)
    draw = 2 * opponents + missing
    wins = ties = 0
    share = 0.0
    for _ in range(iterations):
        deal = rng.sample(unseen, draw)
        final_board = board + deal[:missing]
        hero_score = EVALUATOR.score(hero, final_board)
        others = [EVALUATOR.score(deal[missing + 2 * i: missing + 2 * i + 2], final_board) for i in range(opponents)]
        best_other = min(others)  # lower score = stronger hand
        if hero_score < best_other:
            wins += 1
            share += 1.0
        elif hero_score == best_other:
            ties += 1
            share += 1.0 / (others.count(hero_score) + 1)
    return {"equity": share / iterations, "win_rate": wins / iterations, "tie_rate": ties / iterations,
            "loss_rate": (iterations - wins - ties) / iterations}


def analyze(hero: list[str], board: list[str], pot: float, call: float, iterations: int, opponents: int = 1) -> dict:
    started = time.perf_counter()
    if opponents == 1:  # the accepted heads-up path, unchanged
        result = calculate_equity(hero, board, iterations)
    else:
        result = multiway_equity(hero, board, opponents, iterations)
        result.update({"calculation_method": "monte_carlo", "hands_checked": iterations})
    final, required = pot_odds(pot, call); street = street_for(board); made = None if not board else EVALUATOR.category(hero, board)
    result.update({"street":street, "hand_label":starting_hand_label(hero) if not board else made, "made_hand":made, "draws":detect_draws(hero, board), "required_equity":required, "final_pot_if_call":final, "opponents":opponents, "iterations":result["hands_checked"] if opponents == 1 and street == "River" else iterations, "recommendation":recommendation(result["equity"], required, call), "elapsed_ms":round((time.perf_counter()-started)*1000), "disclaimer":"This recommendation is a basic educational heuristic and does not account for rake, opponent ranges, tournament ICM, player tendencies, or future-street strategy." + ("" if opponents == 1 else f" Equity is measured against {opponents} random hands; players who stay in a pot usually hold better than random, so real equity is often lower.")})
    result["explanation"] = "A free action is available, so checking is the educational baseline." if call == 0 else ("Your estimated equity is above the required equity based on the pot odds." if result["equity"] >= required else "Your estimated equity is below the required equity based on the pot odds.")
    return result
