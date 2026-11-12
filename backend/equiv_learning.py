"""Deterministic learning-session fingerprint (equivalence evidence).

Plays a learning session of ``solver_adaptive`` against the fake Slumbot
referee from ``test_simulation_slumbot`` and records, for every sampled
decision, the full-precision probability vector and the action, plus every
hand result.  Run on two code versions and compare the JSON::

    python equiv_learning.py out.json [hands]

``test_solver_gated.py`` compares the default code path with the golden file
``test_data/equiv_learning_main_fa3b538.json`` produced from ``main`` (fa3b538).
"""
from __future__ import annotations

import json
import sys

from simulation.slumbot import SlumbotClient, run_slumbot_session
from solver.bot import AdaptiveSolverBot

HANDS = 12


def make_recorder(base=AdaptiveSolverBot, **kwargs):
    class Recording(base):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw, **kwargs)
            self.raw: list[list[float]] = []

        def _sample(self, ds, probabilities):
            self.raw.append([float(p) for p in probabilities])
            return super()._sample(ds, probabilities)
    return Recording


def fingerprint(hands: int = HANDS, bot_class=AdaptiveSolverBot, **kwargs) -> dict:
    from test_simulation_slumbot import FakeSlumbot
    recorder = make_recorder(bot_class, **kwargs)
    bots = []

    def factory(index):
        bot = recorder(seed=0, equity_iterations=50)
        bots.append(bot)
        return bot

    results, summary = run_slumbot_session(factory, hands, SlumbotClient(FakeSlumbot(seed=5), token="tok"), learn=True)
    bot = bots[0]
    return {"hands": hands, "winnings": [r.winnings for r in results],
            "probabilities": bot.raw,
            "actions": [[t["hand_number"], t["street"], t["action"], t["target"]] for t in bot.decision_trace],
            "decisions": bot.decision_count, "fallbacks": bot.fallback_count,
            "locked_nodes": [(t.get("source"), t.get("probabilities")) for t in bot.decision_trace]}


if __name__ == "__main__":
    out = sys.argv[1]
    data = fingerprint(int(sys.argv[2]) if len(sys.argv) > 2 else HANDS)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    print(out, data["decisions"], "decisions", len(data["probabilities"]), "sampled")
