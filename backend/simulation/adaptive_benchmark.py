"""Deterministic persistent-match diagnostics for the adaptive research bot."""
from __future__ import annotations

from .adaptive_bot import ExpertAdaptiveBot
from .bots import AggressiveBot, EquityBot, RandomBot, TightBot
from .expert_bot import ExpertRuleBot
from .match import MatchConfig, run_match
from .diagnostic_bots import CallingStationBot, OverAggressorBot, OverFolderBot, PassiveCheckCallBot

OPPONENTS = {"random": RandomBot, "tight": TightBot, "aggressive": AggressiveBot, "equity": EquityBot, "expert": ExpertRuleBot}
ARCHETYPES = {"overfolder": OverFolderBot, "calling_station": CallingStationBot, "overaggressor": OverAggressorBot, "passive": PassiveCheckCallBot}

def _run(strategy, opponent, first: bool, seed: int, hands: int, starting_stack: int = 10000) -> dict:
    a = strategy(seed=seed, equity_iterations=1) if first else opponent(seed=seed, equity_iterations=1)
    b = opponent(seed=seed + 1, equity_iterations=1) if first else strategy(seed=seed + 1, equity_iterations=1)
    result = run_match(a, b, MatchConfig(starting_stack_a=starting_stack, starting_stack_b=starting_stack, max_hands=hands, seed=seed))
    bot = a if first else b; net = result.bot_a_net_chips if first else result.bot_b_net_chips
    return {"hands": result.hands_played, "net_chips": net, "net_bb": net / 100, "bb_per_100": net / 100 / result.hands_played * 100, "illegal_actions": result.illegal_action_count, "fallbacks": result.fallback_diagnostic_count, "decisions": bot.decision_count, "activations": getattr(bot, "exploit_activations", 0), "negative_targets": getattr(bot, "negative_target_incidents", 0), "out_of_bounds_targets": getattr(bot, "out_of_bounds_target_incidents", 0)}

def run_ab(hands: int = 100, seeds: tuple[int, ...] = (9301, 9302)) -> dict:
    """Equal seeds plus both seats; swaps are not duplicate-deal pairing."""
    output = {}
    for name, opponent in OPPONENTS.items():
        control = [_run(ExpertRuleBot, opponent, side, seed, hands) for seed in seeds for side in (True, False)]
        adaptive = [_run(ExpertAdaptiveBot, opponent, side, seed, hands) for seed in seeds for side in (True, False)]
        total = lambda rows: {key: sum(row[key] for row in rows) for key in rows[0]}
        c, a = total(control), total(adaptive)
        output[name] = {"baseline": c, "adaptive": a, "adaptive_minus_baseline_bb_per_100": a["net_bb"] / a["hands"] * 100 - c["net_bb"] / c["hands"] * 100, "seat_aware_not_duplicate_deals": True}
    return output

def run_legality_stress(hands: int = 100, seeds: range = range(9400, 9410)) -> dict:
    totals = {"hands": 0, "adaptive_decisions": 0, "exploit_activations": 0, "illegal_actions": 0, "fallbacks": 0, "exceptions": 0, "negative_targets": 0, "out_of_bounds_targets": 0}
    for seed in seeds:
        for offset, opponent in enumerate((*OPPONENTS.values(), ExpertAdaptiveBot)):
            try:
                row = _run(ExpertAdaptiveBot, opponent, True, seed + offset, hands)
                totals["hands"] += row["hands"]; totals["adaptive_decisions"] += row["decisions"]; totals["exploit_activations"] += row["activations"]; totals["illegal_actions"] += row["illegal_actions"]; totals["fallbacks"] += row["fallbacks"]; totals["negative_targets"] += row["negative_targets"]; totals["out_of_bounds_targets"] += row["out_of_bounds_targets"]
            except Exception: totals["exceptions"] += 1
    return totals

def run_archetype_diagnostic(hands: int = 200, seeds: tuple[int, ...] = (9501, 9502), starting_stack: int = 100000) -> dict:
    """Real-history activation evidence using non-registered test archetypes."""
    output = {}
    for name, opponent in ARCHETYPES.items():
        rows = []
        for seed in seeds:
            adaptive = ExpertAdaptiveBot(seed=seed, equity_iterations=1)
            other = opponent(seed=seed + 1, equity_iterations=1)
            result = run_match(adaptive, other, MatchConfig(starting_stack_a=starting_stack, starting_stack_b=starting_stack, max_hands=hands, seed=seed))
            rows.append({"hands": result.hands_played, "decisions": adaptive.decision_count, "activations": adaptive.exploit_activations, "illegal_actions": result.illegal_action_count, "fallbacks": result.fallback_diagnostic_count, "negative_targets": adaptive.negative_target_incidents, "out_of_bounds_targets": adaptive.out_of_bounds_target_incidents, "trace": adaptive.decision_trace})
        output[name] = rows
    return output
