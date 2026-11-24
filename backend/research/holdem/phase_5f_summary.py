"""Summarize the frozen Phase 5F panels without pooling away missing evidence."""
from argparse import ArgumentParser
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import mean

import numpy as np

from research.holdem.phase_5e import write
from research.holdem.phase_5f import ARMS, manifest


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def group(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    return groups


def paired_interval(cells, value):
    strata = group(cells, lambda cell: (cell["family"], cell["rare_count"]))
    values = [[value(cell) for cell in subset] for subset in strata.values()]
    rng = Random(894100)
    samples = [mean(v for members in values for v in rng.choices(members, k=len(members)))
               for _ in range(2000)]
    return {"delta": mean(v for members in values for v in members),
            "ci95": np.quantile(samples, [.025, .975]).tolist()}


def reply_stats(rows):
    return {"n": len(rows), "v2": sum(row["coverage"] == "supported" for row in rows),
            "observed": {key: mean(row["response"] == key for row in rows)
                         for key in ("fold", "call", "raise", "shove")},
            "arms": {arm: {
                **{score: mean(row["scores"][arm][score] for row in rows)
                   for score in ("brier", "log_loss", "expected_brier", "expected_log_loss")},
                "rate": {key: mean(row["probabilities"][arm].get(key, 0.) for row in rows)
                         for key in ("fold", "call", "raise", "shove")},
                "mae": {key: mean(abs(row["probabilities"][arm].get(key, 0.)
                                      - row["probabilities"]["D"].get(key, 0.)) for row in rows)
                        for key in ("fold", "call", "raise", "shove")},
                "realized_accuracy": mean(max(row["probabilities"][arm], key=lambda key:
                                           (row["probabilities"][arm][key], key)) == row["response"]
                                          for row in rows),
            } for arm in ARMS}}


def instances(cases):
    for case in cases:
        for label, value in case["arms"]["D"]["values"].items():
            detail = case["reply_details"].get(label)
            yield case, label, value, detail


def ev_stats(cases):
    actions = list(instances(cases))
    types = ("profitable_call", "unprofitable_call", "profitable_bluff", "unprofitable_bluff")
    return {"n": len(cases), "rank_pairs": sum(case["rank_pairs"] for case in cases),
            "opportunities": {kind: sum(case["opportunities"].get(kind, 0) for case in cases)
                              for kind in types},
            "bad_shoves": sum(case["bad_shove"] for case in cases),
            "arms": {arm: {
                "mae": mean(case["arms"][arm]["mae"] for case in cases),
                "signed": mean(case["arms"][arm]["signed"] for case in cases),
                "action_mae": mean(abs(case["arms"][arm]["values"][label] - truth)
                                   for case, label, truth, _ in actions),
                "regret": mean(case["arms"][arm]["regret"] for case in cases),
                "worst_regret": max(case["arms"][arm]["regret"] for case in cases),
                "rank_ok": sum(case["arms"][arm]["rank_ok"] for case in cases),
                "false_advantages": sum(case["arms"][arm]["false_advantages"] for case in cases),
                "detected": sum(case["arms"][arm]["unprofitable_shove_detected"] for case in cases),
                "chosen": {kind: sum(case["arms"][arm]["selected_type"] == kind for case in cases)
                           for kind in types},
                "profitable_bluff_decisions": sum(case["opportunities"].get("profitable_bluff", 0) > 0
                                                  for case in cases),
            } for arm in ARMS}}


def action_stats(actions):
    return {"n": len(actions), "arms": {arm: {
        "mae": mean(abs(case["arms"][arm]["values"][label] - truth) for case, label, truth, _ in actions),
        "signed": mean(case["arms"][arm]["values"][label] - truth for case, label, truth, _ in actions),
    } for arm in ARMS}}


def matched_archive(cells, previous):
    old = {(cell["family"], cell["cluster"]): cell["ev"] for cell in previous if cell["ev"]}
    for cell in cells:
        archived = old.pop((cell["family"], cell["cluster"]))
        assert len(archived) == len(cell["ev"])
        for original, recovered in zip(archived, cell["ev"], strict=True):
            assert original["closing"] == recovered["closing"]
            for arm, old_arm in (("A", "A"), ("B", "B"), ("D", "C")):
                before, after = original["arms"][old_arm], recovered["arms"][arm]
                assert before["choice"] == after["choice"]
                assert tuple(before["values"]) == tuple(after["values"])
                assert np.allclose(list(before["values"].values()), list(after["values"].values()),
                                   rtol=0, atol=1e-12)
    assert not old


def panels(cells):
    cases = [{**case, "family": cell["family"], "cluster": cell["cluster"]}
             for cell in cells for case in cell["ev"]]
    replies = [{**reply, "family": cell["family"], "cluster": cell["cluster"]}
               for cell in cells for reply in cell["reply"]]
    actions = list(instances(cases))
    wagers = [row for row in actions if row[3] is not None]
    fallback_exact = all(row["probabilities"]["C"] == row["probabilities"]["A"]
                         for row in replies if row["coverage"] != "supported")
    fallback_exact &= all(case["arms"]["C"]["values"][label] == case["arms"]["A"]["values"][label]
                          for case, label, _, detail in wagers if detail["source"] == "incumbent")
    switches = [case for case in cases if case["arms"]["C"]["choice"] != case["arms"]["A"]["choice"]]

    def harm(case):
        return case["arms"]["C"]["regret"] - case["arms"]["A"]["regret"]

    harmful = sorted((case for case in switches if harm(case) > 1e-12), key=harm, reverse=True)
    bad_fallbacks = sorted(
        ({"label": label, "case": case, "increased_error": abs(case["arms"]["B"]["values"][label] - truth)
          - abs(case["arms"]["A"]["values"][label] - truth)} for case, label, truth, detail in wagers
         if detail["coverage"] == "unsupported"),
        key=lambda item: item["increased_error"], reverse=True)
    summary = {"fallback_exact": fallback_exact, "reply": reply_stats(replies),
               "reply_by_coverage": {key: reply_stats(rows) for key, rows in
                                     group(replies, lambda row: row["coverage"]).items()},
               "reply_by_wager": {key: reply_stats(rows) for key, rows in
                                  group(replies, lambda row: str(row["price"])).items()},
               "reply_by_group": {key: reply_stats(rows) for key, rows in
                                  group(replies, lambda row: row["group"]).items()},
               "closing_reply": reply_stats([row for row in replies if row["context"]["closing"]]),
               "ev": ev_stats(cases),
               "ev_by_family": {key: ev_stats(rows) for key, rows in group(cases, lambda row: row["family"]).items()},
               "ev_by_root": {key: ev_stats(rows) for key, rows in group(cases, lambda row:
                              "closing_call" if row["closing"] else "checked_to").items()},
               "action_by_coverage": {key: action_stats(rows) for key, rows in
                   group(actions, lambda row: row[3]["coverage"] if row[3] else "no_future_reply").items()},
               "wager_by_menu": {key: action_stats(rows) for key, rows in
                                  group(wagers, lambda row: row[3]["group"]).items()},
               "switches": len(switches), "harmful": len(harmful),
               "most_harmful": [{"harm_bb": harm(case), "case": case} for case in harmful[:10]],
               "worst_added_harm": harm(harmful[0]) if harmful else 0.,
               "historical_worst_fallbacks": bad_fallbacks[:10]}
    for arm in ("B", "C"):
        for metric in ("mae", "regret"):
            summary[f"{arm}-{metric}"] = paired_interval(cells, lambda cell: mean(
                case["arms"][arm][metric] - case["arms"]["A"][metric] for case in cell["ev"]))
        for metric in ("brier", "log_loss"):
            summary[f"{arm}-{metric}"] = paired_interval(cells, lambda cell: mean(
                row["scores"][arm][metric] - row["scores"]["A"][metric] for row in cell["reply"]))
    return summary


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory
    assert manifest() == load(out / "frozen.json")
    first = (out / "holdout-13.json").read_bytes()
    parity = first == (out / "holdout-31.json").read_bytes()
    if not parity:
        raise RuntimeError("canonical holdouts differ")
    archive = load(out / "archive.json")
    matched_archive(archive, load(out.parent / "phase-5e-2026-11-19" / "holdout-13.json"))
    historical, fresh = panels(archive), panels(json.loads(first))
    run_times = [load(out / f"holdout-{seed}-timing.json") for seed in (13, 31)]
    observer = {mode: load(out / f"observer-{mode}" / "summary.json")
                for mode in ("isolated", "concurrent")}
    ev = fresh["C-mae"]
    gates = {
        "mae_materiality_and_interval": ev["delta"] <= -.10 and ev["ci95"][1] < 0,
        "regret_non_deterioration": fresh["C-regret"]["delta"] <= .05,
        "harm": fresh["worst_added_harm"] < 8.,
        "fallback_exact": fresh["fallback_exact"] and historical["fallback_exact"],
        "coverage": all(fresh["action_by_coverage"][key]["n"] >= 32 and
                        fresh["reply_by_coverage"][key]["n"] >= 32
                        for key in ("supported", "unsupported", "sparse")),
        "observer": all(check for run in observer.values() for check in run["checks"].values()),
        "offline_budgets": all(run["exact"]["max"] < 15 and run["peak_mib"] < 768 for run in run_times),
        "hash_parity": parity,
    }
    write(out / "summary.json", {"hash": sha256(first).hexdigest(), "archive_parity": True,
                                 "fresh": fresh, "historical": historical, "gates": gates,
                                 "study_timing": run_times, "observer": observer})


if __name__ == "__main__":
    main()
