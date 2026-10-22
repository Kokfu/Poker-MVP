"""Review of the user's own logged hands: stats, results, and heuristic leak flags.

Hands are replayed through the same engine and ``OpponentModel`` that build
opponent profiles, with the model pointed at the user's seat, so VPIP, PFR and
the other statistics are defined exactly as they are for opponents.
"""
from __future__ import annotations

from typing import Any

from simulation.opponent_model import OpponentModel, confidence_for

from .service import HERO, _hand_complete_payload, _replay, spot_from_dict
from .store import HandStore

MIN_SAMPLE = 20  # opportunities before a leak is flagged
POSTFLOP_STREETS = ("flop", "turn", "river")


def _stat(opportunities: int, occurrences: int) -> dict[str, Any]:
    return {"frequency": round(occurrences / opportunities, 3) if opportunities else None,
            "opportunities": opportunities, "occurrences": occurrences, "confidence": confidence_for(opportunities)}


def review(store: HandStore, opponent: str | None = None) -> dict[str, Any]:
    model = OpponentModel(HERO)
    net_bb = 0.0
    known = showdowns = showdown_known = showdown_wins = skipped = 0
    by_opponent: dict[str, dict[str, Any]] = {}
    for stored in store.all_hands(opponent):
        spot = spot_from_dict(stored["spot"])
        try:
            status, payload, _ = _replay(spot)
        except ValueError:
            skipped += 1  # a stored hand that no longer replays is reported, not hidden
            continue
        if status != "hand_complete":
            skipped += 1
            continue
        model.update(payload["result"]["history"])
        summary = _hand_complete_payload(spot, payload)["summary"]
        row = by_opponent.setdefault(stored["opponent"], {"opponent": stored["opponent"], "hands": 0, "net_bb": 0.0, "known_hands": 0})
        row["hands"] += 1
        showdowns += int(bool(summary["showdown"]))
        net = summary.get("hero_net")
        if net is not None:
            known += 1
            net_bb += net / spot.big_blind
            row["known_hands"] += 1
            row["net_bb"] += net / spot.big_blind
            if summary["showdown"]:
                showdown_known += 1
                showdown_wins += int(net > 0)
    snapshot = model.snapshot()
    stats, streets = snapshot.statistics, snapshot.street_statistics

    def across(name: str) -> tuple[int, int]:
        return sum(streets[s][name].opportunities for s in POSTFLOP_STREETS), sum(streets[s][name].occurrences for s in POSTFLOP_STREETS)

    measures = {
        "vpip": _stat(stats["vpip"].opportunities, stats["vpip"].occurrences),
        "pfr": _stat(stats["preflop_raise"].opportunities, stats["preflop_raise"].occurrences),
        "three_bet": _stat(stats["three_bet"].opportunities, stats["three_bet"].occurrences),
        "fold_to_preflop_raise": _stat(stats["fold_to_raise"].opportunities, stats["fold_to_raise"].occurrences),
        "postflop_bet": _stat(*across("bet")),
        "fold_to_bet": _stat(*across("fold_to_bet")),
        "showdown_win": _stat(showdown_known, showdown_wins),
    }
    results = {
        "hands": snapshot.hands_observed, "hands_with_known_result": known, "net_bb": round(net_bb, 2),
        "bb_per_100": round(net_bb / known * 100, 1) if known else None, "showdowns": showdowns,
        "showdowns_with_known_result": showdown_known, "skipped_hands": skipped,
        "note": "Results count only hands whose outcome is known: folds, and showdowns where you entered the opponent's cards.",
    }
    return {"opponent": opponent, "results": results, "stats": measures, "leaks": leaks(measures),
            "by_opponent": [{**row, "net_bb": round(row["net_bb"], 2)} for row in sorted(by_opponent.values(), key=lambda r: r["opponent"])]}


def _flag(measures: dict[str, Any], name: str, test, issue: str, advice: str) -> dict[str, Any] | None:
    stat = measures[name]
    if stat["opportunities"] < MIN_SAMPLE or stat["frequency"] is None or not test(stat["frequency"]):
        return None
    return {"stat": name, "issue": issue, "advice": advice, "frequency": stat["frequency"],
            "opportunities": stat["opportunities"], "confidence": stat["confidence"]}


def leaks(measures: dict[str, Any]) -> list[dict[str, Any]]:
    """Heuristic flags, shown only with at least 20 opportunities.  They are study prompts, not verdicts."""
    found = [
        _flag(measures, "fold_to_bet", lambda f: f > 0.60, "Folding to postflop bets very often",
              "Opponents can bluff you profitably; defend more often with hands that have showdown value or draws."),
        _flag(measures, "fold_to_bet", lambda f: f < 0.25, "Rarely folding to postflop bets",
              "You may be paying off value bets; fold the weakest bluff-catchers against big bets."),
        _flag(measures, "vpip", lambda f: f < 0.50, "Very tight preflop for heads-up",
              "Heads-up, the button should play most hands and the big blind should defend widely."),
        _flag(measures, "fold_to_preflop_raise", lambda f: f > 0.60, "Folding to preflop raises very often",
              "Defend the big blind more; folding this much lets every raise show an automatic profit."),
        _flag(measures, "postflop_bet", lambda f: f < 0.20, "Rarely betting postflop when checked to",
              "Bet more for value and as a bluff; passive play gives up pots and lets opponents see cards cheaply."),
        _flag(measures, "showdown_win", lambda f: f < 0.45, "Losing more than half of showdowns",
              "You may be calling with hands that are too weak; compare your calls against the Coach's equity and EV."),
    ]
    vpip, pfr = measures["vpip"], measures["pfr"]
    if vpip["opportunities"] >= MIN_SAMPLE and vpip["frequency"] and pfr["frequency"] is not None and pfr["frequency"] / vpip["frequency"] < 0.4:
        found.append({"stat": "pfr", "issue": "Calling or limping far more than raising preflop",
                      "advice": "Raise more of the hands you play; open-limping and flat-calling give up initiative.",
                      "frequency": pfr["frequency"], "opportunities": pfr["opportunities"], "confidence": pfr["confidence"]})
    return [item for item in found if item]
