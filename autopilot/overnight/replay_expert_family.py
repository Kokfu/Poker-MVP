"""Reconstruct public decision cohorts from recorded development schedules."""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
JOBS = ROOT / "autopilot" / "overnight" / "jobs"
sys.path.insert(0, str(ROOT / "backend"))

from simulation import duplicate_evaluation as evaluation
from simulation.agent_profiles import restore_profiles
from simulation.evaluation import bootstrap_interval
from solver.bot import AdaptiveSolverBot


def load_schedule(opponent, independent_ledger=None):
    if independent_ledger is not None:
        with independent_ledger.open(encoding="utf-8") as source:
            header = json.loads(next(source))
            sessions = [json.loads(line) for line in source]
        if (header["format_version"], header["agent"], header["opponent"]) != (1, "solver_adaptive", opponent):
            raise ValueError("the independent ledger does not record this matchup")
        if len(sessions) != header["configuration"]["pairs"]:
            raise ValueError("the independent ledger must contain the full schedule")
        for index, session in enumerate(sessions, start=1):
            if session.pop("session") != index:
                raise ValueError("the independent ledger has out-of-order sessions")
        return header["configuration"], sessions, None, header["agent"], opponent, False

    if opponent == "adaptive":
        path = ROOT / "benchmark-results" / "phase-5" / "session-tournament-dev.json"
        archive = json.loads(path.read_text(encoding="utf-8"))
        match = next(row for row in archive["rows"] if {row["strategy"], row["opponent"]} == {"solver_adaptive", opponent})
        orientation = 1 if match["strategy"] == "solver_adaptive" else -1
        return archive["configuration"], None, orientation * match["bb_per_100"], match["strategy"], match["opponent"], False

    path = JOBS / "profiles" / f"{opponent}.profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    run = profile["runs"][f"nov27-{opponent}"]
    if any(run["initial_profile_hands"].values()):
        raise ValueError("the archived run did not begin with fresh profiles")
    return run["header"]["configuration"], run["sessions"], None, "solver_adaptive", opponent, True


def categorize(history, solver_seat):
    aggressions = Counter()
    limped = False
    seen = set()
    for event in history.events:
        if event.event_type != "action_taken":
            continue
        street = event.street
        if event.actor == solver_seat:
            if street == "preflop" and not aggressions[street]:
                spot = "limped" if limped else "unopened"
            elif event.amount_to_call_before:
                spot = "facing_raise" if street == "preflop" or aggressions[street] > 1 else "facing_bet"
            else:
                spot = "check_available"
            if (street, spot) not in seen:
                seen.add((street, spot))
                yield street, spot, event
        if street == "preflop" and event.applied_action == "call" and not aggressions[street]:
            limped = True
        if event.applied_action in {"bet", "raise"} or event.all_in_classification in {"short_raise", "full_raise"}:
            aggressions[street] += 1


def replay(opponent, limit, independent_ledger=None):
    config_values, archived_sessions, archived_rate, strategy, rival, carry_learning = load_schedule(
        opponent, independent_ledger,
    )
    if config_values["seed_set"] != "development":
        raise ValueError("only development schedules can be replayed")
    config = evaluation.DuplicateConfig(**{**config_values, "workers": 1})
    seeds = config.seeds()[:limit]
    profiles = restore_profiles(None) if carry_learning else None
    results = defaultdict(lambda: {"hands": 0, "net_chips": 0, "actions": Counter()})

    def add(table, street="", position="", spot="", action=None, net=0):
        row = results[table, street, position, spot]
        row["hands"] += 1
        row["net_chips"] += net
        if action:
            row["actions"][action] += 1

    class ObservedEngine(evaluation.HandEngine):
        def play(self):
            result = super().play()
            solver = next(seat for seat, bot in self.bots.items() if type(bot) is AdaptiveSolverBot)
            history = result["history"]
            position = "BTN" if history.button_player == solver else "BB"
            net = result["stacks"][solver] - config.starting_stack
            final_street = next((event.street for event in reversed(history.events) if event.event_type == "action_taken"), "preflop")
            add("terminal_street", street=final_street, position=position, net=net)
            add("terminal_outcome", street=final_street, position=position, spot=history.ending_type, net=net)
            add("position", position=position, net=net)
            for street, case, event in categorize(history, solver):
                action = event.applied_action or "unknown"
                add("decision", street=street, position=position, spot=case, action=action, net=net)
                if street != "preflop" and event.amount_to_call_before:
                    price = event.amount_to_call_before / (event.pot_before + event.amount_to_call_before)
                    add("call_price", street=street, position=position,
                        spot=f"{case} {'above 25%' if price > .25 else 'up to 25%'}", action=action, net=net)
            return result

    pairs = []
    with patch.object(evaluation, "HandEngine", ObservedEngine):
        for index, seed in enumerate(seeds):
            diagnostics = {}
            pair = evaluation.play_duplicate_pair(
                config, strategy, rival, seed, learning=profiles, diagnostics=diagnostics,
            )
            observed = {**asdict(pair), **diagnostics}
            if archived_sessions is not None and observed != archived_sessions[index]:
                raise ValueError(f"{opponent} session {index + 1} differs from the archived run")
            pairs.append(observed)
            print(f"{opponent} session {index + 1}/{len(seeds)} complete", flush=True)

    hands = sum(2 * pair["hands_per_seat"] for pair in pairs)
    orientation = 1 if strategy == "solver_adaptive" else -1
    net = orientation * sum(pair["net_seat_a"] + pair["net_seat_b"] for pair in pairs)
    rates = [
        orientation * 100 * (pair["net_seat_a"] + pair["net_seat_b"]) /
        (2 * pair["hands_per_seat"] * config.big_blind)
        for pair in pairs
    ]
    for table in ("terminal_street", "terminal_outcome", "position"):
        partition = [total for key, total in results.items() if key[0] == table]
        assert sum(item["hands"] for item in partition) == hands
        assert sum(item["net_chips"] for item in partition) == net
    return {
        "opponent": opponent, "hands": hands, "sessions": len(pairs),
        "bb_per_100": 100 * net / (hands * config.big_blind),
        "session_interval": bootstrap_interval(
            rates, resamples=config.bootstrap_resamples, statistics_seed=config.statistics_seed,
            confidence_level=config.confidence_level,
        ),
        "archived_aggregate_bb_per_100": archived_rate,
        "verified_archived_sessions": len(pairs) if archived_sessions is not None else 0,
        "carried_profile": carry_learning,
        "deal_mismatches": sum(not pair["deal_verified"] for pair in pairs),
        "illegal_actions": sum(pair["illegal_actions"] for pair in pairs),
        "fallback_actions": sum(pair["fallback_actions"] for pair in pairs),
        "solver_fallback_actions": sum(pair["solver_fallback_actions"] for pair in pairs),
        "cohorts": rows(results, config.big_blind),
    }


def rows(results, big_blind):
    return [
        {"table": table, "street": street, "position": position, "spot": spot, **total,
         "bb_per_100": 100 * total["net_chips"] / (total["hands"] * big_blind)}
        for (table, street, position, spot), total in sorted(results.items())
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("opponent", choices=("expert", "adaptive", "range_expert"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--independent-ledger", type=Path, help="replay an independent development JSONL")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("the optional session limit must be positive")
    if args.output.exists():
        parser.error("the output file already exists")
    report = replay(args.opponent, args.limit, args.independent_ledger)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
