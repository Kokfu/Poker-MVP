"""Offline matched-profile river and duplicate gameplay experiments."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from math import fsum, isclose
import json
import os
from pathlib import Path
import random
from statistics import mean
from time import perf_counter

import numpy as np
from treys import Evaluator

from coach.service import Spot, SpotAction, _replay
from poker_analyzer import RANK_VALUE, TreysAdapter
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action
from simulation.bots import BOT_TYPES, AggressiveBot, PokerBot
from simulation.cards import Deck
from simulation.engine import HandEngine
from simulation.evaluation import _derived_seed, _percentile_interval, _validate_history_and_conservation
from simulation.opponent_model import OpponentModel, OpponentProfileSnapshot
from solver.bot import AdaptiveSolverBot, SolverBot
from solver.combos import COMBOS, card_mask, combo_index
from solver.showdown import ShowdownModel


BIG_BLIND = 100
STACK = 1500
SIZES = (3, 30, 100)
PRIOR = 10
HARM_TOLERANCE = 1e-6
RANKER = TreysAdapter()
RANK_CLASSES = Evaluator()
CASES = (
    ("set", "9h 9d", "Kc 9s 3d 5h Js", 500),
    ("middle_pair", "6d 5d", "Qs 6s 2c 7h Ad", 500),
    ("ace_high", "As 4s", "Jh 8d 3c 2h 9c", 0),
    ("top_pair", "Kd Td", "Kh 7d 4s Qc 3h", 0),
)


def strength(rank):
    return 9 - max(7, RANK_CLASSES.get_rank_class(rank))


@dataclass(frozen=True)
class Style:
    tight: bool
    aggressive: bool

    def participate(self, cards):
        high, low = sorted((RANK_VALUE[card[0]] for card in cards), reverse=True)
        if self.tight:
            return .85 if high == low or (high == 14 and low >= 10) else .09
        return .88

    @property
    def raise_probability(self):
        return .65 if self.aggressive else 0

    def open_probability(self, rank):
        rates = (.40, .65, .95) if self.aggressive else (.02, .08, .35)
        return rates[strength(rank)]

    def call_probability(self, cards, rank, cost, pot):
        small, large = (
            ((.28, .74, .99), (.12, .53, .95)) if self.aggressive
            else ((.12, .78, .99), (.03, .45, .94))
        )
        return (small if 2 * cost <= pot else large)[strength(rank)]

    def path_likelihood(self, cards, board, river_rank, bet):
        flop, turn = (RANKER.score(list(cards), list(board[:n])) for n in (3, 4))
        river = self.open_probability(river_rank)
        return (self.participate(cards) * (1 - self.raise_probability)
                * (1 - self.open_probability(flop)) * (1 - self.open_probability(turn))
                * (river if bet else 1 - river))


STYLES = {
    "tight_passive": Style(True, False),
    "loose_passive": Style(False, False),
    "tight_aggressive": Style(True, True),
    "loose_aggressive": Style(False, True),
}
OPPONENTS = (*STYLES, "equity", "expert", "solver")
MISMATCH = dict(zip(STYLES, reversed(STYLES), strict=True))


class SyntheticOpponent(PokerBot):
    def __init__(self, style, seed):
        super().__init__(seed)
        self.style = style

    def decide(self, o):
        if o.street == "preflop":
            if o.amount_to_call and self.rng.random() >= self.style.participate(o.hole_cards):
                return Action("fold")
            if "raise" in o.legal_actions and self.rng.random() < self.style.raise_probability:
                return self._sizing(o, "raise")
            return self._passive(o)
        rank = RANKER.score(o.hole_cards, o.community_cards)
        if o.amount_to_call:
            cost = min(o.amount_to_call, o.hero_stack)
            effective_pot = o.pot - (o.amount_to_call - cost)
            if self.rng.random() >= self.style.call_probability(o.hole_cards, rank, cost, effective_pot):
                return Action("fold")
        elif "bet" in o.legal_actions and self.rng.random() < self.style.open_probability(rank):
            return Action("bet", max(o.minimum_target_to, min(500, o.maximum_target_to)))
        return self._passive(o)


def make_opponent(name, seed):
    if name in STYLES:
        return SyntheticOpponent(STYLES[name], seed)
    return BOT_TYPES[name](seed=seed, equity_iterations=1000)


class PolicyProbe:
    """Read full precision from the same chooser used by Coach and Match."""

    probabilities = None
    estimate = None
    record_estimate = False

    def _sample(self, ds, probabilities):
        if (not np.isfinite(probabilities).all() or (probabilities < 0).any()
                or not isclose(fsum(probabilities), 1, rel_tol=0, abs_tol=1e-6)):
            raise AssertionError("invalid raw solver probabilities")
        self.probabilities = probabilities.copy()
        self.decision_state = ds
        return super()._sample(ds, probabilities)

    def _range_report(self, board, hero_combo, villain):
        if self.record_estimate:
            mask = card_mask(tuple(COMBOS[hero_combo]) + board)
            weights = np.where(mask, 0.0, villain)
            self.estimate = weights / weights.sum() if weights.sum() else None
        return super()._range_report(board, hero_combo, villain)


class OffProbe(PolicyProbe, SolverBot):
    pass


class OnProbe(PolicyProbe, AdaptiveSolverBot):
    pass


@dataclass(frozen=True)
class FrozenProfile:
    snapshot: OpponentProfileSnapshot
    showdown: ShowdownModel

    def attach(self, advisor):
        advisor.showdown_model = deepcopy(self.showdown)


def check_finished(engine, result):
    net = {seat: result["stacks"][seat] - STACK for seat in ("a", "b")}
    _validate_history_and_conservation(result["history"], net["a"], net["b"])
    fallbacks = [bot.last_explanation for bot in engine.bots.values()
                 if getattr(bot, "fallback_count", 0)]
    if result["illegal_actions"] or result["illegal_diagnostics"] or fallbacks:
        raise RuntimeError(f"failed integrity check in {engine.state.hand_id}: "
                           f"{result['illegal_diagnostics']}, {fallbacks}")
    return net


def train(name, stream, sizes):
    base = 41_000_000 + 100_000 * OPPONENTS.index(name) + 1000 * stream
    model, showdown = OpponentModel("b"), ShowdownModel()
    profiles = {}
    for i in range(max(sizes)):
        seed = base + i
        hero = AggressiveBot(_derived_seed(seed, "training-hero"))
        villain = make_opponent(name, _derived_seed(seed, "training-villain"))
        engine = HandEngine(hero, villain, stack=STACK, seed=seed, hand_id=f"train-{seed}",
                            button=("a", "b")[i % 2])
        result = engine.play()
        check_finished(engine, result)
        model.update(result["history"])
        showdown.observe(result["history"], "b")
        if i + 1 in sizes:
            profiles[i + 1] = FrozenProfile(model.snapshot(), deepcopy(showdown))
    return profiles


def label(action):
    return action.type if action.amount is None else f"{action.type}_{action.amount}"


def to_action(key):
    kind, _, target = key.partition("_")
    return Action(kind, int(target)) if target.isdecimal() else Action(key)


def river_spot(hero, board, bet):
    actions = [SpotAction("hero", "raise", 250), SpotAction("villain", "call")]
    actions += [SpotAction("villain", "check"), SpotAction("hero", "check")] * 2
    actions.append(SpotAction("villain", "bet", bet) if bet else SpotAction("villain", "check"))
    return Spot(hero.split(), board.split(), hero_stack=STACK, villain_stack=STACK, actions=actions)


def river_policy(spot, profile=None, seed=917):
    bot = OffProbe(seed) if profile is None else OnProbe(seed)
    if profile:
        profile.attach(bot)
    bot.explain_ev = bot.record_estimate = True
    status, payload, _ = _replay(spot, bot, None if profile is None else profile.snapshot)
    info = payload["explanation"]
    if status != "hero_to_act" or info["source"] != "postflop_solve" or bot.estimate is None:
        raise RuntimeError(f"unexpected river decision: {status}, {info}")
    actions = []
    mix = Counter()
    total = fsum(bot.probabilities)
    for raw, mass in zip(info["labels"], bot.probabilities, strict=True):
        action = to_action(raw)
        concrete = bot._concrete_postflop(bot.decision_state, (action.type, action.amount))
        actions.append(label(concrete))
        mix[actions[-1]] += float(mass) / total
    return {"mix": dict(mix), "source": info["source"], "advice": payload["advice"],
            "modeled_ev_bb": {key: val / BIG_BLIND for key, val in zip(actions, info["action_ev"], strict=True)},
            "locks": info["exploit"]["locked_nodes"]}, bot.estimate


def river_reference(spot, bet, style):
    hero, board = tuple(spot.hero_cards), tuple(spot.board)
    exact = ExactRiverEV(hero, board, lambda cards, rank: style.path_likelihood(cards, board, rank, bet))
    state = RiverState(500 + bet, 0, bet, 1250, 1250 - bet, bet or 100, checked_to=not bet)
    return exact, state


def weighted_ev(mix, values):
    return fsum(mass * values[key] for key, mass in mix.items())


def score_river(style, spot, bet, policies, n):
    true, state = river_reference(spot, bet, style)
    keys = sorted({key for policy, _ in policies.values() for key in policy["mix"]})

    def values_at(evaluator):
        return {key: evaluator.action_ev(state, to_action(key), style.call_probability) / BIG_BLIND
                for key in keys}

    true_evs = values_at(true)
    best_true = max(true_evs, key=true_evs.get)
    off_mix, on_mix = (policies[arm][0]["mix"] for arm in ("off", "matched"))
    alpha = n / (n + PRIOR)
    candidate = {key: (1 - alpha) * off_mix.get(key, 0) + alpha * on_mix.get(key, 0) for key in keys}
    off_ev = weighted_ev(off_mix, true_evs)
    scored = {}
    for arm, (policy, estimate) in policies.items():
        inferred = ExactRiverEV(tuple(spot.hero_cards), tuple(spot.board),
                                lambda combo, _: float(estimate[combo_index(combo)]))
        inferred_evs = values_at(inferred)
        best_inferred = max(inferred_evs, key=inferred_evs.get)
        scored[arm] = {
            **policy,
            "range_tv": fsum(abs(a.weight - b.weight) for a, b in zip(true.holdings, inferred.holdings, strict=True)) / 2,
            "equity_error": abs(true.equity - inferred.equity),
            "best_with_true_response": best_inferred,
            "ev_with_true_response": inferred_evs,
            "posterior_regret_bb": true_evs[best_true] - true_evs[best_inferred],
            "policy_gap_bb": true_evs[best_inferred] - weighted_ev(policy["mix"], true_evs),
        }
    scored["candidate"] = {"mix": candidate}
    for row in scored.values():
        row["ev_bb"] = weighted_ev(row["mix"], true_evs)
        row["delta_bb"] = row["ev_bb"] - off_ev
        row["action_tv"] = fsum(abs(row["mix"].get(k, 0) - off_mix.get(k, 0)) for k in keys) / 2
    return {"arms": scored, "true_evs_bb": true_evs, "true_equity": true.equity, "best_true": best_true}


def exact_summary(rows):
    summary = {}
    for arm in rows[0]["arms"]:
        decisions = [row["arms"][arm] for row in rows]
        harm = [-row["delta_bb"] for row in decisions if row["delta_bb"] < -HARM_TOLERANCE]
        counts = Counter()
        for row in decisions:
            for key, mass in row["mix"].items():
                counts[to_action(key).type] += mass / len(rows)
        summary[arm] = {
            "ev_bb": mean(row["ev_bb"] for row in decisions),
            "delta_bb": mean(row["delta_bb"] for row in decisions),
            "action_tv": mean(row["action_tv"] for row in decisions),
            "harm_count": len(harm), "harm_sum_bb": fsum(harm),
            "harm_mean_bb": mean(harm) if harm else 0,
            "action_frequencies": dict(counts),
            **{key: mean(row[key] for row in decisions) for key in ("range_tv", "equity_error")
               if key in decisions[0]},
        }
    return summary


def run_exact():
    profiles = {(name, stream): train(name, stream, SIZES) for name in STYLES for stream in (0, 1)}
    rows = []
    for case, hero, board, bet in CASES:
        spot = river_spot(hero, board, bet)
        off = river_policy(spot)
        computed = {(name, stream, size): river_policy(spot, profile)
                    for (name, stream), prefixes in profiles.items() for size, profile in prefixes.items()}
        for name, style in STYLES.items():
            for stream in (0, 1):
                for size in SIZES:
                    arms = {"off": off, "matched": computed[name, stream, size],
                            "mismatched": computed[MISMATCH[name], stream, size]}
                    rows.append({"opponent": name, "stream": stream, "size": size, "case": case,
                                 **score_river(style, spot, bet, arms, size)})
        print(f"Exact river completed {case}", flush=True)
    return {
        "rows": rows, "overall": exact_summary(rows),
        **{f"by_{field}": {str(value): exact_summary([row for row in rows if row[field] == value])
                           for value in values} for field, values in
           (("opponent", STYLES), ("stream", (0, 1)), ("size", SIZES))},
        "profiles": {name: {stream: {size: prof.snapshot.as_dict() for size, prof in profiles[name, stream].items()}
                            for stream in (0, 1)} for name in STYLES},
    }


def play_arm(name, profile, seed, seat, enabled):
    started = perf_counter()
    hero_seed = _derived_seed(seed, "evaluation-hero")
    bot = OnProbe(hero_seed) if enabled else OffProbe(hero_seed)
    if enabled:
        profile.attach(bot)
    opponent = make_opponent(name, _derived_seed(seed, "evaluation-opponent"))
    pair = (bot, opponent) if seat == "a" else (opponent, bot)
    deal = Deck(seed).deal(9)
    engine = HandEngine(*pair, stack=STACK, seed=seed, hand_id=f"eval-{seed}", button="a",
                        opponent_profile_provider=lambda player: profile.snapshot if player == seat else None)
    result = engine.play()
    net = check_finished(engine, result)[seat]
    board = result["state"].community_cards
    if engine.holes != {"a": deal[:2], "b": deal[2:4]} or board != deal[4:4 + len(board)]:
        raise RuntimeError(f"duplicate deck mismatch at seed {seed}")
    return {
        "net": net, "decisions": bot.decision_count, "solves": bot.solve_count,
        "sources": dict(Counter(row["source"] for row in bot.decision_trace)),
        "illegal_actions": result["illegal_actions"],
        "solver_fallbacks": bot.fallback_count + getattr(opponent, "fallback_count", 0),
        "showdown": result["showdown"],
        "seconds": perf_counter() - started,
        "actions": [[e.actor, e.street, e.applied_action, e.target_total] for e in result["history"].events
                    if e.event_type == "action_taken"],
    }


def play_block(name, stream, start, deals=2):
    started = perf_counter()
    profile = train(name, stream, (30,))[30]
    setup_seconds = perf_counter() - started
    started = perf_counter()
    hands = [
        {"seed": seed, "seat": seat, "off": play_arm(name, profile, seed, seat, False),
         "matched": play_arm(name, profile, seed, seat, True)}
        for seed in range(start, start + deals) for seat in ("a", "b")
    ]
    return {"opponent": name, "stream": stream, "profile": profile.snapshot.as_dict(),
            "hands": hands, "setup_seconds": setup_seconds, "play_seconds": perf_counter() - started}


def summarize_gameplay(blocks):
    rng = random.Random(44_091)
    groups = {name: [b for b in blocks if b["opponent"] == name] for name in OPPONENTS}
    groups = {name: group for name, group in groups.items() if group}

    def delta(block):
        return mean(100 / BIG_BLIND * (hand["matched"]["net"] - hand["off"]["net"])
                    for hand in block["hands"])

    def summarize(strata):
        hands = [hand for group in strata for block in group for hand in block["hands"]]
        rates = [[delta(block) for block in group] for group in strata]
        interval = None
        if all(len(rate) >= 2 for rate in rates):
            samples = [mean(mean(rng.choices(rate, k=len(rate))) for rate in rates) for _ in range(10_000)]
            interval = _percentile_interval(samples, .95)
        result = {"blocks": sum(map(len, strata)), "hands_per_arm": len(hands),
                  "delta_bb100": mean(mean(rate) for rate in rates), "paired_95": interval}
        for arm in ("off", "matched"):
            plays = [hand[arm] for hand in hands]
            match_nets = [sum(hand[arm]["net"] for hand in block["hands"])
                          for group in strata for block in group]
            result[arm] = {
                "bb100": mean(mean(100 / BIG_BLIND * hand[arm]["net"]
                                   for block in group for hand in block["hands"]) for group in strata),
                "wins": sum(hand["net"] > 0 for hand in plays),
                "losses": sum(hand["net"] < 0 for hand in plays),
                "ties": sum(hand["net"] == 0 for hand in plays),
                "block_wins": sum(net > 0 for net in match_nets),
                "block_losses": sum(net < 0 for net in match_nets),
                "block_ties": sum(net == 0 for net in match_nets),
                **{key: sum(hand[key] for hand in plays) for key in
                   ("decisions", "solves", "illegal_actions", "solver_fallbacks", "seconds")},
            }
        return result

    return {"overall": summarize(list(groups.values())),
            "by_opponent": {name: summarize([group]) for name, group in groups.items()}}


def run_gameplay(workload):
    blocks = []
    for i, name in enumerate(OPPONENTS if workload == "pilot" else STYLES):
        for stream in ((2,) if workload == "pilot" else range(3, 9)):
            start = 42_000_000 + 1000 * i if workload == "pilot" else 43_000_000 + 100_000 * i + 1000 * stream
            block = play_block(name, stream, start)
            blocks.append(block)
            print(f"{workload} {name} stream {stream}: {block['play_seconds']:.2f}s", flush=True)
    return {"blocks": blocks, **summarize_gameplay(blocks)}


def peak_resident_bytes():
    if os.name != "nt":
        import resource
        import sys
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == "darwin" else value * 1024
    import ctypes as ct
    from ctypes import wintypes

    class ProcessMemoryCounters(ct.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ct.c_size_t) for name in ("peak_working_set", "working_set", "peak_paged_pool",
                                            "paged_pool", "peak_nonpaged_pool", "nonpaged_pool",
                                            "pagefile", "peak_pagefile")]

    process_handle = ct.WinDLL("kernel32").GetCurrentProcess
    process_handle.restype = wintypes.HANDLE
    get_memory = ct.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ct.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    counters = ProcessMemoryCounters()
    counters.cb = ct.sizeof(counters)
    if not get_memory(process_handle(), ct.byref(counters), counters.cb):
        raise ct.WinError(ct.get_last_error())
    return counters.peak_working_set


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workload", choices=("exact", "pilot", "larger"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    started = perf_counter()
    result = run_exact() if args.workload == "exact" else run_gameplay(args.workload)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump({"workload": args.workload, "seconds": perf_counter() - started,
                   "peak_resident_bytes": peak_resident_bytes(), **result}, file,
                  indent=2, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    main()
