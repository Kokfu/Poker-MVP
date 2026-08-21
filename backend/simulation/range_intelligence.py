"""Privacy-safe, deterministic heads-up range and equity infrastructure.

All constructors accept visible cards and public evidence only.  Candidate
combos are hypotheses, never a read of an opponent's unrevealed cards.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import exp, isfinite, log
import random
from typing import Any, Iterable, Mapping

from poker_analyzer import EVALUATOR, FULL_DECK, RANK_VALUE, STRAIGHTS, SUITS


def _card_key(card: str) -> tuple[int, int]:
    if card not in FULL_DECK:
        raise ValueError(f"invalid card: {card}")
    return (RANK_VALUE[card[0]], SUITS.index(card[1]))


@dataclass(frozen=True, order=True)
class HoleCardCombo:
    """One physical two-card combination, canonicalized high rank then suit."""
    cards: tuple[str, str]

    def __init__(self, first: str, second: str):
        if first == second:
            raise ValueError("a hole-card combo requires two distinct cards")
        ordered = tuple(sorted((first, second), key=_card_key, reverse=True))
        object.__setattr__(self, "cards", ordered)

    def as_dict(self) -> dict[str, list[str]]:
        return {"cards": list(self.cards)}


@dataclass(frozen=True)
class PreflopDescriptor:
    pocket_pair: bool; suited: bool; offsuit: bool; high_rank: str; low_rank: str
    rank_gap: int; connected: bool; one_gap: bool; broadway_count: int
    ace_present: bool; king_present: bool; suited_connector: bool; suited_ace: bool
    pocket_pair_rank: str | None; strength: float; category: str

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def describe_preflop(combo: HoleCardCombo) -> PreflopDescriptor:
    a, b = combo.cards; high, low = RANK_VALUE[a[0]], RANK_VALUE[b[0]]
    pair, suited = high == low, a[1] == b[1]
    gap = 0 if pair else high - low - 1
    broadway = sum(rank >= 10 for rank in (high, low))
    score = high + low * .45 + (8 if pair else 0) + (2 if suited else 0) + max(0, 3-gap) + broadway * 1.5
    category = "premium" if (pair and high >= 11) or score >= 24 else "strong" if score >= 20 else "playable" if score >= 16 else "speculative" if score >= 13 else "weak"
    return PreflopDescriptor(pair, suited, not suited, a[0], b[0], gap, not pair and gap == 0,
        not pair and gap == 1, broadway, high == 14 or low == 14, high == 13 or low == 13,
        suited and not pair and gap == 0, suited and (high == 14 or low == 14), a[0] if pair else None, score, category)


def legal_opponent_combos(hero_cards: Iterable[str], board_cards: Iterable[str]) -> tuple[HoleCardCombo, ...]:
    known = tuple(hero_cards) + tuple(board_cards)
    if len(set(known)) != len(known) or any(card not in FULL_DECK for card in known):
        raise ValueError("known cards must be distinct valid cards")
    return tuple(HoleCardCombo(a, b) for a, b in combinations((c for c in FULL_DECK if c not in known), 2))


@dataclass(frozen=True)
class WeightedRange:
    weights: tuple[tuple[HoleCardCombo, float], ...]

    def __post_init__(self) -> None:
        seen = set()
        for combo, weight in self.weights:
            if combo in seen or not isfinite(weight) or weight < 0:
                raise ValueError("range weights must be finite, nonnegative, and unique")
            seen.add(combo)

    @classmethod
    def uniform(cls, combos: Iterable[HoleCardCombo]) -> "WeightedRange":
        return cls(tuple((combo, 1.0) for combo in sorted(set(combos))))

    @property
    def total_combos(self) -> int: return len(self.weights)
    @property
    def active_combos(self) -> int: return sum(weight > 0 for _, weight in self.weights)
    @property
    def total_weight(self) -> float: return sum(weight for _, weight in self.weights)
    def probability(self, combo: HoleCardCombo) -> float:
        total = self.total_weight
        return next((weight / total for item, weight in self.weights if item == combo), 0.0) if total else 0.0
    def normalized(self) -> "WeightedRange":
        total = self.total_weight
        if total <= 0: raise ValueError("cannot normalize an empty-weight range")
        return WeightedRange(tuple((combo, weight / total) for combo, weight in self.weights))
    def as_dict(self, top: int = 10) -> dict[str, Any]:
        normalized = self.normalized()
        ordered = sorted(normalized.weights, key=lambda item: (-item[1], item[0].cards))
        return {"total_combos": self.total_combos, "active_combos": self.active_combos, "total_weight": normalized.total_weight,
                "top_combos_hypotheses_only": [{"cards": list(combo.cards), "probability": weight} for combo, weight in ordered[:top]]}


def heuristic_preflop_range(hero_cards: Iterable[str], board_cards: Iterable[str] = (), action: str | None = None, position: str | None = None) -> WeightedRange:
    """Compact non-solver prior. Public action shifts hand-quality buckets."""
    factors = {"premium": 1.0, "strong": .75, "playable": .48, "speculative": .28, "weak": .12}
    if action in {"raise", "3-bet", "all_in"}: factors.update(premium=2.8, strong=1.8, playable=.75, speculative=.25, weak=.08)
    elif action in {"limp", "call"}: factors.update(premium=.85, strong=1.05, playable=1.15, speculative=1.2, weak=.75)
    if position == "in_position": factors["speculative"] *= 1.1
    return WeightedRange(tuple((combo, factors[describe_preflop(combo).category]) for combo in legal_opponent_combos(hero_cards, board_cards))).normalized()


def combo_board_features(combo: HoleCardCombo, board: Iterable[str]) -> dict[str, Any]:
    board = tuple(board); cards = combo.cards + board
    made = "preflop" if not board else EVALUATOR.category(list(combo.cards), list(board)).lower().replace(" ", "_")
    ranks = {RANK_VALUE[c[0]] for c in cards}; hole = {RANK_VALUE[c[0]] for c in combo.cards}
    flush_draw = len(board) in (3, 4) and any(sum(c[1] == suit for c in cards) == 4 and any(c[1] == suit for c in combo.cards) for suit in SUITS)
    completions = {x for x in range(2, 15) if not any(seq <= ranks and seq & hole for seq in STRAIGHTS) and any(seq <= ranks | {x} and seq & hole for seq in STRAIGHTS)} if len(board) in (3, 4) else set()
    draw = flush_draw or len(completions) in {1, 2}
    return {"made_hand": made, "two_pair_plus": made in {"two_pair", "three_of_a_kind", "straight", "flush", "full_house", "four_of_a_kind", "straight_flush", "royal_flush"}, "flush_draw": flush_draw, "straight_draw": len(completions) in {1, 2}, "strong_draw": draw and (flush_draw or len(completions) == 2), "overcards": bool(board) and any(RANK_VALUE[c[0]] > max(RANK_VALUE[b[0]] for b in board) for c in combo.cards)}


class RangeUpdater:
    """Public-evidence likelihood layer; floors prevent heuristic collapse."""
    MINIMUM_FACTOR = .05
    def update(self, prior: WeightedRange, action: str, board_cards: Iterable[str] = (), pot_fraction: float | None = None, profile: Any | None = None) -> WeightedRange:
        board_cards = tuple(board_cards)
        action = action.lower().replace("_", "-")
        aggressive = action in {"bet", "raise", "3-bet", "all-in"}; passive = action in {"check", "call", "limp"}
        size = "small" if pot_fraction is not None and pot_fraction <= .40 else "medium" if pot_fraction is not None and pot_fraction <= .75 else "large" if pot_fraction is not None and pot_fraction <= 1.25 else "overbet" if pot_fraction is not None else "medium"
        confidence, aggression, calling = _profile_effect(profile, aggressive)
        values = []
        for combo, weight in prior.weights:
            features, desc = combo_board_features(combo, board_cards), describe_preflop(combo)
            factor = 1.0
            if aggressive:
                if not board_cards:
                    factor *= {"premium": 2.4, "strong": 1.65, "playable": 1.0, "speculative": .65, "weak": .35}[desc.category]
                else:
                    factor *= 2.0 if features["two_pair_plus"] else 1.55 if features["strong_draw"] else 1.25 if features["made_hand"] == "pair" else .55
                if size in {"large", "overbet"}: factor *= 1.35 if (features["two_pair_plus"] or features["strong_draw"]) else .82
                factor *= 1 + aggression * (.35 if features["strong_draw"] or features["made_hand"] == "preflop" and desc.category in {"speculative", "weak"} else -.15)
            elif passive:
                factor *= 1.25 if not features["two_pair_plus"] else .82  # traps stay possible
                if action == "call" and calling:
                    factor *= 1.15 if (features["made_hand"] == "pair" or desc.category in {"playable", "speculative"}) else .92
            values.append((combo, max(self.MINIMUM_FACTOR * weight, weight * factor * confidence)))
        return WeightedRange(tuple(values)).normalized()


def _profile_effect(profile: Any, aggressive: bool) -> tuple[float, float, bool]:
    stats = getattr(profile, "statistics", {}) if profile is not None else {}
    estimate = stats.get("aggressive") if isinstance(stats, Mapping) else None
    rate, confidence = getattr(estimate, "smoothed_frequency", .5), getattr(estimate, "confidence", "very_low")
    if not isinstance(rate, (int, float)) or not isfinite(rate) or confidence in {"very_low", "low"}: return 1.0, 0.0, False
    call = stats.get("call") if isinstance(stats, Mapping) else None
    call_rate = getattr(call, "smoothed_frequency", 0.0)
    return 1.0, (rate - .35) if aggressive else 0.0, isinstance(call_rate, (int, float)) and isfinite(call_rate) and call_rate >= .55


@dataclass(frozen=True)
class RangeSummary:
    total_combos: int; active_combos: int; effective_combo_count: float; normalized_entropy: float; premium_fraction: float; strong_made_fraction: float; pair_fraction: float; draw_fraction: float; weak_air_fraction: float; pocket_pair_fraction: float; suited_fraction: float; broadway_fraction: float

    def as_dict(self) -> dict[str, Any]: return self.__dict__.copy()


def summarize_range(weighted: WeightedRange, board_cards: Iterable[str] = ()) -> RangeSummary:
    r = weighted.normalized(); probs = [w for _, w in r.weights if w > 0]; entropy = -sum(p * log(p) for p in probs); max_entropy = log(len(probs)) if len(probs) > 1 else 1.0
    def fraction(predicate): return sum(w for c, w in r.weights if predicate(c))
    return RangeSummary(r.total_combos, r.active_combos, 1 / sum(p*p for p in probs), entropy / max_entropy, fraction(lambda c: describe_preflop(c).category == "premium"), fraction(lambda c: combo_board_features(c, board_cards)["two_pair_plus"]), fraction(lambda c: combo_board_features(c, board_cards)["made_hand"] == "pair"), fraction(lambda c: combo_board_features(c, board_cards)["strong_draw"]), fraction(lambda c: not combo_board_features(c, board_cards)["two_pair_plus"] and not combo_board_features(c, board_cards)["strong_draw"] and combo_board_features(c, board_cards)["made_hand"] not in {"pair", "preflop"}), fraction(lambda c: describe_preflop(c).pocket_pair), fraction(lambda c: describe_preflop(c).suited), fraction(lambda c: describe_preflop(c).broadway_count > 0))


@dataclass(frozen=True)
class RangeEquityEstimate:
    hero_equity: float; tie_probability: float; opponent_equity: float; iterations: int; method: str; range_combo_count: int; effective_combo_count: float
    def as_dict(self) -> dict[str, Any]: return self.__dict__.copy()


class RangeEquityEstimator:
    def estimate(self, hero_cards: Iterable[str], board_cards: Iterable[str], weighted_range: WeightedRange, iterations: int = 2000, seed: int = 0) -> RangeEquityEstimate:
        hero, board, r = tuple(hero_cards), tuple(board_cards), weighted_range.normalized()
        if len(hero) != 2 or set(hero) & set(board): raise ValueError("hero and board must be valid non-colliding cards")
        valid = [(c, w) for c, w in r.weights if not (set(c.cards) & (set(hero) | set(board)))]
        if not valid: raise ValueError("range has no legal candidate combos")
        valid_total = sum(weight for _, weight in valid)
        valid = [(combo, weight / valid_total) for combo, weight in valid]
        effective = 1 / sum(w*w for _, w in valid)
        if len(board) == 5:
            win = tie = 0.0
            for combo, weight in valid:
                hs, os = EVALUATOR.score(list(hero), list(board)), EVALUATOR.score(list(combo.cards), list(board))
                win += weight * (hs < os); tie += weight * (hs == os)
            return RangeEquityEstimate(win + tie/2, tie, 1-win-tie/2, len(valid), "exact", len(valid), effective)
        rng = random.Random(seed); choices, weights = zip(*valid); win = tie = 0
        for _ in range(iterations):
            combo = rng.choices(choices, weights=weights, k=1)[0]
            available = [c for c in FULL_DECK if c not in set(hero + board + combo.cards)]
            final_board = list(board) + rng.sample(available, 5-len(board))
            hs, os = EVALUATOR.score(list(hero), final_board), EVALUATOR.score(list(combo.cards), final_board)
            win += hs < os; tie += hs == os
        tie_p = tie / iterations; equity = (win + tie/2) / iterations
        return RangeEquityEstimate(equity, tie_p, 1-equity, iterations, "monte_carlo", len(valid), effective)


def showdown_calibration(weighted: WeightedRange, actual_public_combo: HoleCardCombo) -> dict[str, float | int]:
    r = weighted.normalized(); probability = r.probability(actual_public_combo)
    ranked = sorted(r.weights, key=lambda item: (-item[1], item[0].cards)); rank = next((i + 1 for i, (c, _) in enumerate(ranked) if c == actual_public_combo), 0)
    return {"actual_combo_probability": probability, "rank": rank, "percentile": 1 - ((rank - 1) / len(ranked)) if rank else 0.0, "log_score": log(max(probability, 1e-300))}


@dataclass
class PublicRangeTracker:
    """Sequential decision-time range state driven only by supplied public events.

    Call ``observe`` immediately after an opponent action, passing the board
    visible at that event. The tracker has no engine/deck/actual-card access.
    """
    hero_cards: tuple[str, str]
    weighted_range: WeightedRange
    updater: RangeUpdater

    @classmethod
    def uniform(cls, hero_cards: Iterable[str], board_cards: Iterable[str] = ()) -> "PublicRangeTracker":
        hero = tuple(hero_cards)
        if len(hero) != 2: raise ValueError("hero needs exactly two cards")
        return cls(hero, WeightedRange.uniform(legal_opponent_combos(hero, board_cards)).normalized(), RangeUpdater())

    def observe(self, action: str, board_cards: Iterable[str] = (), pot_fraction: float | None = None, profile: Any | None = None) -> WeightedRange:
        # The known-card set is checked before update, preventing accidental
        # future-card or candidate collision inputs from silently entering.
        legal = set(legal_opponent_combos(self.hero_cards, board_cards))
        if not set(combo for combo, _ in self.weighted_range.weights) <= legal:
            # Moving streets removes candidates that use newly public cards.
            self.weighted_range = WeightedRange(tuple((combo, weight) for combo, weight in self.weighted_range.weights if combo in legal)).normalized()
        self.weighted_range = self.updater.update(self.weighted_range, action, board_cards, pot_fraction, profile)
        return self.weighted_range
