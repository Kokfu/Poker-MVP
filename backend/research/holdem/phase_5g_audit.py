"""Read-only public history audit and independent per-prefix memory measurement."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from statistics import mean
import tracemalloc

from research.holdem import phase_5e as prior
from research.holdem.opponent_profile_v2 import extract
from research.holdem.phase_5g import DEVELOPMENT, train
from research.holdem.phase_5g_summary import load, size, wilson
from research.holdem.profile_v2_hybrid import EvidenceProfile, wager_key
from simulation.history_service import hand_history_from_dict


def category(row):
    return size(row.collectible, row.matched_pot)


def counts(rows):
    responses = Counter(row.response for _, row in rows if row.response is not None)
    n = sum(responses.values())
    return {"hands_with_opportunity": len({source for source, _ in rows}), "opportunities": len(rows),
            "responses": dict(responses), "observed": n, "missing": len(rows) - n,
            "effective_sample_size_unit_weight": n, "empirical_fold_wilson95": wilson(responses["fold"], n)}


def slices(raw):
    profile = EvidenceProfile("read-only-audit")
    total = 0
    unknown = 0
    duplicates = 0
    wagers = []
    short_calls = []
    decisions = []
    seen = set()
    for source, history, seat in raw:
        total += 1
        accepted = profile.update(source, history, seat)
        if not accepted:
            duplicates += 1
            continue
        rows, missed = extract(history, seat)
        unknown += missed
        for row in rows:
            key = (source, row.event_index)
            assert key not in seen
            seen.add(key)
            decisions.append((source, row))
            if wager_key(row.situation, row.collectible, row.matched_pot) is not None:
                wagers.append((source, row))
                event = history.events[row.event_index]
                if row.response == "call" and event.applied_action == "all_in" and row.offered > row.collectible:
                    short_calls.append((source, row))
    by_dimension = {}
    for name, levels, split in (
        ("street", ("preflop", "flop", "turn", "river"), lambda r: r.situation.street),
        ("wager_size", ("small", "half-pot band", "pot band", "overbet"), category),
        ("closing", ("open", "closing"),
         lambda r: "closing" if r.situation.closing else "open"),
        ("closing_shove", ("other", "closing shove"),
         lambda r: "closing shove" if r.situation.closing and r.situation.previous == "all_in" else "other"),
        ("effective_depth", ("0-10", ">10-30", ">30-100", ">100"),
         lambda r: ("0-10", ">10-30", ">30-100", ">100")[r.situation.depth_bucket]),
        ("spr", ("0-1", ">1-3", ">3-8", ">8"),
         lambda r: ("0-1", ">1-3", ">3-8", ">8")[r.situation.spr_bucket]),
        ("position", ("button", "big_blind"), lambda r: r.situation.position),
        ("previous", ("start", "check", "call", "bet", "raise", "all_in"), lambda r: r.situation.previous),
    ):
        by_dimension[name] = {level: counts([(source, row) for source, row in wagers if split(row) == level])
                              for level in levels}
    by_dimension["all_public_decisions_by_street"] = {
        street: counts([(source, row) for source, row in decisions if row.situation.street == street])
        for street in ("preflop", "flop", "turn", "river")}
    by_dimension["short_all_in_call"] = counts(short_calls)
    exact = defaultdict(list)
    for item in wagers:
        row = item[1]
        exact[wager_key(row.situation, row.collectible, row.matched_pot)].append(item)
    exact_results = []
    for _, rows in sorted(exact.items()):
        row = rows[0][1]
        evidence = profile.evidence(row.situation, row.collectible, row.matched_pot)
        exact_results.append({"context": row.situation.__dict__, "price": row.collectible, "pot": row.matched_pot,
                              "stack": row.effective_stack, "bb": row.big_blind,
                              "exact_evidence": evidence._asdict(), **counts(rows),
                              "forecast_source": "V2" if evidence.coverage == "supported" else "incumbent",
                              "historical_action_mae": None})
    return {"hands_logged": total, "accepted": profile.v2.hands_observed, "duplicate_ids": duplicates,
            "unknown_legal_turns": unknown, "all_public_decisions": counts(decisions),
            "live_wagers": counts(wagers), "slices": by_dimension, "exact": exact_results}


def local_histories(path):
    if not path.is_file():
        return {"available": False}
    by_opponent = defaultdict(list)
    records = Counter()
    rejected = Counter()
    seen = set()
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for source, opponent, spot in connection.execute("SELECT id, opponent, spot FROM hands ORDER BY id"):
            records[opponent] += 1
            try:
                contents = json.loads(spot)
                # SQLite guarantees unique row IDs. An identical spot under a different ID
                # is flagged as a possible copy, since it cannot establish hand identity.
                key = (opponent, json.dumps(contents, sort_keys=True))
                if key in seen:
                    rejected["identical_payload_candidate"] += 1
                    continue
                seen.add(key)
                status, payload, _ = prior.coach._replay(prior.coach.spot_from_dict(contents))
                if status != "hand_complete":
                    rejected["incomplete"] += 1
                    continue
                history = payload["result"]["history"]
                assert prior.ProfileV2("validation").update(str(source), history, "b")
            except (ValueError, KeyError, TypeError):
                rejected["invalid"] += 1
                continue
            by_opponent[opponent].append((str(source), history, "b"))
    opponents = []
    for opponent in records:
        report = slices(by_opponent[opponent])
        report["hands_logged"] = records[opponent]
        opponents.append(report)
    return {"available": True, "hands_logged": sum(records.values()), "opponents": opponents,
            "rejected_or_excluded": dict(rejected), "style": "unclassified"}


def archived_audit(archive):
    contexts = defaultdict(list)
    for cell in archive:
        for row in cell["reply"]:
            key = (cell["family"], cell["cluster"], row["member"], row["price"], row["pot"],
                   json.dumps(row["context"], sort_keys=True))
            contexts[key].append(row)
    values = defaultdict(list)
    for cell in archive:
        for case in cell["ev"]:
            for action, row in case["reply_details"].items():
                key = (cell["family"], cell["cluster"], case["member"], row["price"], row["pot"],
                       json.dumps(row["context"], sort_keys=True))
                values[key].append({arm: abs(case["arms"][arm]["values"][action] -
                                             case["arms"]["D"]["values"][action])
                                    for arm in ("A", "B", "C")})
    results = []
    for (family, cluster, member, price, pot, context), rows in sorted(contexts.items()):
        row = rows[0]
        n = row["replies"]
        scored = values[family, cluster, member, price, pot, context]
        results.append({"family": family, "member": member, "cluster": cluster, "price": price, "pot": pot,
                        "context": json.loads(context), "hands_logged": 300, "opportunities": row["opportunities"],
                        "observed": n, "effective_sample_size_unit_weight": n, "coverage": row["coverage"],
                        "forecast_source": "V2" if row["coverage"] == "supported" else "incumbent",
                        "hybrid_fold_forecast": row["probabilities"]["C"]["fold"],
                        "empirical_fold_ci_available": False,
                        "conditional_fold_error": abs(row["probabilities"]["C"]["fold"] -
                                                      row["probabilities"]["D"]["fold"]),
                        "historical_action_samples": len(scored),
                        "historical_action_mae": {arm: mean(r[arm] for r in scored)
                                                  for arm in ("A", "B", "C")} if scored else None})
    return results


def memory():
    original, additional, *_ = DEVELOPMENT
    report = {}
    tracemalloc.start()
    try:
        for n, _, _, _, _ in train(2, 0, 0, original + 200, additional + 200, 1500):
            retained, peak = tracemalloc.get_traced_memory()
            report[str(n)] = {"retained_bytes": retained, "peak_bytes": peak}
    finally:
        tracemalloc.stop()
    return report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("audit", "memory"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.stage == "memory":
        prior.write(args.output / "profile-memory.json", memory())
        return
    previous = args.output.parent / "phase-5f-2026-11-20"
    histories = [hand_history_from_dict(row) for row in load(previous / "api-histories-0.json")]
    fixture = {}
    for label, raw in (("single", histories[:1]), ("persistent match", histories[1:])):
        fixture[label] = {style: slices((f"{label}:{i}", history, seat) for i, history in enumerate(raw))
                          for style, seat in (("solver", "a"), ("tight", "b"))}
    prior.write(args.output / "coverage-audit.json", {
        "local": local_histories(prior.ROOT / "backend/data/coach.sqlite"),
        "public_fixtures": fixture, "phase_5f_contexts": archived_audit(load(previous / "holdout-13.json")),
    })


if __name__ == "__main__":
    main()
