"""Exact heads-up river payoffs for closing checks, calls and fold/call replies.

Independent of solver trees, reach, hand ranking and value traversal. Scope:
one Hero decision, with Villain responding to a wager by folding or calling.
"""
from dataclasses import dataclass
from itertools import combinations
from math import fsum, isfinite
from typing import Callable

from poker_analyzer import FULL_DECK, TreysAdapter
from simulation.actions import Action


Combo = tuple[str, str]
RangeWeight = Callable[[Combo, int], float]
# Villain cards, Treys rank, effective cost to call, pot before Villain calls.
CallProbability = Callable[[Combo, int, int, int], float]


@dataclass(frozen=True)
class RiverState:
    pot: int
    hero_commit: int
    villain_commit: int
    hero_stack: int
    villain_stack: int
    last_full_raise: int
    checked_to: bool = False
    raising_reopened: bool = True
    hero_gets_odd_chip: bool = False  # local engine gives the odd chip to seat b

    def __post_init__(self):
        amounts = (self.pot, self.hero_commit, self.villain_commit, self.hero_stack,
                   self.villain_stack, self.last_full_raise)
        if any(type(value) is not int or value < 0 for value in amounts):
            raise ValueError("river amounts must be nonnegative integers")
        if (self.hero_commit > self.villain_commit or self.pot < self.hero_commit + self.villain_commit
                or not self.hero_stack or not self.last_full_raise
                or (not self.villain_stack and self.hero_commit == self.villain_commit)
                or (self.checked_to and (self.hero_commit or self.villain_commit))):
            raise ValueError("invalid heads-up river decision")

    def branch(self, action: Action) -> tuple[int, int, bool]:
        """Return Hero and Villain's final proposed totals and whether Villain responds."""
        price = self.villain_commit - self.hero_commit
        ceiling = self.hero_commit + self.hero_stack
        if action.type in ("fold", "check", "call", "all_in") and action.amount is not None:
            raise ValueError("only a bet or raise carries an explicit target")
        if action.type == "fold" and price:
            return self.hero_commit, self.villain_commit, False
        if action.type == "check" and not price:
            if not self.checked_to:
                raise ValueError("check requires a specified continuation unless it closes the river")
            return self.hero_commit, self.villain_commit, False
        if action.type == "call" and 0 < price < self.hero_stack:
            return self.villain_commit, self.villain_commit, False
        if action.type == "all_in" and ceiling <= self.villain_commit:
            return ceiling, self.villain_commit, False
        if self.raising_reopened and self.villain_stack:
            expected = "raise" if price else "bet"
            minimum = self.villain_commit + self.last_full_raise
            target = action.amount
            if action.type == expected and type(target) is int and minimum <= target <= ceiling:
                return target, min(target, self.villain_commit + self.villain_stack), True
            if action.type == "all_in" and ceiling > self.villain_commit:
                return ceiling, min(ceiling, self.villain_commit + self.villain_stack), True
        raise ValueError(f"illegal or unsupported river action: {action}")


@dataclass(frozen=True)
class Holding:
    combo: Combo
    rank: int
    weight: float
    result: int  # 1 Hero wins, 0 ties, -1 loses


class ExactRiverEV:
    def __init__(self, hero: Combo, board: tuple[str, ...], range_weight: RangeWeight):
        blocked = set(hero) | set(board)
        if len(hero) != 2 or len(board) != 5 or len(blocked) != 7 or not blocked.issubset(FULL_DECK):
            raise ValueError("expected seven distinct, valid cards")
        evaluator = TreysAdapter()
        public = list(board)
        hero_rank = evaluator.score(list(hero), public)
        holdings = []
        for combo in combinations((card for card in FULL_DECK if card not in blocked), 2):
            rank = evaluator.score(list(combo), public)
            weight = range_weight(combo, rank)
            if not isfinite(weight) or weight < 0:
                raise ValueError("range weights must be finite and nonnegative")
            result = (hero_rank < rank) - (hero_rank > rank)
            holdings.append(Holding(combo, rank, weight, result))
        scale = max(hand.weight for hand in holdings)
        if not scale:
            raise ValueError("range has no compatible positive mass")
        total = fsum(hand.weight / scale for hand in holdings)
        self.holdings = tuple(
            Holding(hand.combo, hand.rank, (hand.weight / scale) / total, hand.result)
            for hand in holdings
        )

    @property
    def equity(self) -> float:
        return fsum(hand.weight * (hand.result + 1) / 2 for hand in self.holdings)

    def action_ev(self, state: RiverState, action: Action, call_probability: CallProbability | None = None) -> float:
        hero_target, villain_target, reply = state.branch(action)
        if action.type == "fold":
            return 0.0
        matched = min(hero_target, villain_target)
        hero_paid = matched - state.hero_commit
        pot = state.pot - state.hero_commit - state.villain_commit + 2 * matched
        tie = (pot + state.hero_gets_odd_chip) // 2
        payoffs = {-1: -hero_paid, 0: tie - hero_paid, 1: pot - hero_paid}
        if not reply:
            return fsum(hand.weight * payoffs[hand.result] for hand in self.holdings)
        if call_probability is None:
            raise ValueError("aggression requires an explicit Villain response")
        call_cost = matched - state.villain_commit
        pot_before_call = pot - call_cost

        def expected(hand: Holding) -> float:
            call = call_probability(hand.combo, hand.rank, call_cost, pot_before_call)
            if not isfinite(call) or not 0 <= call <= 1:
                raise ValueError("call probability must lie in [0, 1]")
            return hand.weight * ((1 - call) * state.pot + call * payoffs[hand.result])

        return fsum(expected(hand) for hand in self.holdings)
