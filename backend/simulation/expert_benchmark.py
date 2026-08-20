"""Small deterministic internal benchmark for ExpertRuleBot.

Run ``python -m simulation.expert_benchmark`` from backend.  This reports
independent-hand outcomes; it is diagnostic evidence, not a strength claim.
"""
from .bots import AggressiveBot, EquityBot, RandomBot, TightBot
from .engine import SimulationRunner
from .expert_bot import ExpertRuleBot


def run(hands: int = 1000, seed: int = 7300) -> dict[str, dict]:
    output = {}
    for offset, (name, cls) in enumerate({"random": RandomBot, "tight": TightBot, "aggressive": AggressiveBot, "equity": EquityBot, "expert": ExpertRuleBot}.items()):
        # One iteration keeps the 5,000-hand smoke matrix practical; this is
        # explicitly a regression harness, not an equity-quality benchmark.
        runner = SimulationRunner(ExpertRuleBot(seed=seed), cls(seed=seed + 1, equity_iterations=1), hands=hands, seed=seed + offset, equity_iterations=1)
        result = runner.run()
        output[name] = {key: result[key] for key in ("hands_played", "bot_a_net_chips", "bot_a_bb_per_100", "bot_a_wins", "bot_b_wins", "ties", "illegal_actions")}
        output[name]["bot_a_net_bb"] = result["bot_a_net_chips"] / result["bb"]
        output[name]["fallback_diagnostics"] = len(runner.illegal_diagnostics)
        output[name]["hand_net_sum"] = sum(hand["net_a"] for hand in runner.hand_results)
    return output


def _seat_run(expert_first: bool, opponent, hands: int, seed: int) -> dict:
    first = ExpertRuleBot(seed=seed) if expert_first else opponent(seed=seed)
    second = opponent(seed=seed + 1, equity_iterations=1) if expert_first else ExpertRuleBot(seed=seed + 1)
    runner = SimulationRunner(first, second, hands=hands, seed=seed, equity_iterations=1)
    result = runner.run()
    expert_net = result["bot_a_net_chips"] if expert_first else result["bot_b_net_chips"]
    expert_wins = result["bot_a_wins"] if expert_first else result["bot_b_wins"]
    expert_losses = result["bot_b_wins"] if expert_first else result["bot_a_wins"]
    hand_nets = [hand["net_a"] if expert_first else hand["net_b"] for hand in runner.hand_results]
    wins = [value for value in hand_nets if value > 0]; losses = [value for value in hand_nets if value < 0]
    return {"hands": hands, "expert_seat": "a" if expert_first else "b", "expert_net_chips": expert_net, "expert_net_bb": expert_net / result["bb"], "expert_bb_per_100": expert_net / result["bb"] / hands * 100, "expert_wins": expert_wins, "expert_losses": expert_losses, "ties": result["ties"], "average_win_chips": sum(wins) / len(wins) if wins else 0, "average_loss_chips": sum(losses) / len(losses) if losses else 0, "hand_net_sum": sum(hand_nets), "illegal_actions": result["illegal_actions"], "fallback_diagnostics": len(runner.illegal_diagnostics), "expert_decisions": (first if expert_first else second).decision_count}


def run_mirrored(hands: int = 200, seeds: tuple[int, ...] = (8101, 8102, 8103, 8104)) -> dict[str, dict]:
    """Seat-aware independent comparisons; these are not duplicate deals."""
    output = {}
    for name, cls in {"random": RandomBot, "tight": TightBot, "aggressive": AggressiveBot, "equity": EquityBot, "expert": ExpertRuleBot}.items():
        rows = [_seat_run(orientation, cls, hands, seed) for seed in seeds for orientation in (True, False)]
        output[name] = {"seat_runs": rows, "combined": {"hands": sum(row["hands"] for row in rows), "expert_net_chips": sum(row["expert_net_chips"] for row in rows), "expert_net_bb": sum(row["expert_net_bb"] for row in rows), "illegal_actions": sum(row["illegal_actions"] for row in rows), "fallback_diagnostics": sum(row["fallback_diagnostics"] for row in rows), "accounting_matches": all(row["hand_net_sum"] == row["expert_net_chips"] for row in rows)}}
    return output


def run_legality_stress(hands_per_seed: int = 40, seeds: range = range(9000, 9020)) -> dict[str, int]:
    """Broad deterministic legality diagnostic across 4,000 independent hands."""
    totals = {"hands": 0, "expert_decisions": 0, "illegal_actions": 0, "fallback_diagnostics": 0, "negative_targets": 0, "out_of_bounds_targets": 0, "exceptions": 0}
    for seed in seeds:
        for offset, opponent in enumerate((RandomBot, TightBot, AggressiveBot, EquityBot, ExpertRuleBot)):
            expert = ExpertRuleBot(seed=seed)
            other = opponent(seed=seed + 1, equity_iterations=1)
            try:
                runner = SimulationRunner(expert, other, hands=hands_per_seed, seed=seed + offset, equity_iterations=1)
                result = runner.run()
                totals["hands"] += hands_per_seed; totals["illegal_actions"] += result["illegal_actions"]; totals["fallback_diagnostics"] += len(runner.illegal_diagnostics)
                totals["expert_decisions"] += expert.decision_count
                totals["negative_targets"] += expert.negative_target_incidents; totals["out_of_bounds_targets"] += expert.out_of_bounds_target_incidents
            except Exception:
                totals["exceptions"] += 1
    return totals


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2, sort_keys=True))
