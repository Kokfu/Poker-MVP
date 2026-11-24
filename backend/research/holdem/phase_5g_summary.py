"""Summarize frozen Phase 5G panels and apply their numerical gates."""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import mean

from research.holdem.phase_5e import write
from research.holdem.phase_5f_summary import group, paired_interval
from research.holdem.phase_5g import ARMS, BUDGETS, source_manifest


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def size(price, pot):
    if 8 * price <= 3 * pot:
        return "small"
    if 4 * price <= 3 * pot:
        return "half-pot band"
    if 8 * price <= 9 * pot:
        return "pot band"
    return "overbet"


def wilson(count, total):
    if not total:
        return None
    z = 1.959963984540054
    p = count / total
    center = (p + z*z / (2*total)) / (1 + z*z/total)
    spread = z * sqrt(p*(1-p)/total + z*z/(4*total*total)) / (1 + z*z/total)
    return [max(0., center - spread), min(1., center + spread)]


def coverage(rows, arm):
    counts = Counter(row["coverage"][arm]["coverage"] for row in rows)
    return {key: counts[key] for key in ("supported", "sparse", "unsupported")}


def proper(rows, arm):
    folds = [row for row in rows if row["context"]["closing"]]
    return {
        **{key: mean(r["scores"][arm][key] for r in rows)
           for key in ("brier", "log_loss", "expected_brier", "expected_log_loss")},
        "closing_fold_mae": mean(abs(r["probabilities"][arm]["fold"] - r["probabilities"]["E"]["fold"])
                                 for r in folds) if folds else None,
        "mean_predicted_fold": mean(r["probabilities"][arm].get("fold", 0.) for r in rows),
        "true_fold": mean(r["probabilities"]["E"].get("fold", 0.) for r in rows),
    }


def results(cases, arm):
    entries = [case["arms"][arm] for case in cases]
    rank_pairs = sum(case["rank_pairs"] for case in cases)
    return {
        "mae": mean(row["mae"] for row in entries),
        "rank_pairs": rank_pairs,
        "rank_ok": sum(row["rank_ok"] for row in entries),
        "false_advantages": sum(row["false_advantages"] for row in entries),
        "mean_regret": mean(row["regret"] for row in entries),
        "worst_regret": max(row["regret"] for row in entries),
        "profitable_calls": sum(row["selected_type"] == "profitable_call" for row in entries),
        "profitable_bluffs": sum(row["selected_type"] == "profitable_bluff" for row in entries),
        "harmful_shoves": sum(row["harmful_shove"] for row in entries),
        "harmful_vs_A": sum(row["regret"] > case["arms"]["A"]["regret"] + 1e-12
                            for row, case in zip(entries, cases, strict=True)),
        "worst_added_regret": max(row["regret"] - case["arms"]["A"]["regret"]
                                  for row, case in zip(entries, cases, strict=True)),
    }


def summarize(cells, timings, peak):
    members = [{**member, "family": cell["family"], "cluster": cell["cluster"]}
               for cell in cells for member in cell["members"]]
    cases = [{**case, "family": m["family"], "cluster": m["cluster"], "member": m["member"], "deal": i}
             for m in members for i, case in enumerate(m["cases"])]
    replies = [{**row, "family": m["family"], "member": m["member"]} for m in members
               for case, scripted in zip(m["cases"], m["scripted"], strict=True)
               for row in (*case["wagers"].values(), *scripted)]
    actions = [(case, label, case["wagers"].get(label))
               for case in cases for label in case["arms"]["E"]["values"]]
    curves = {}
    for n in BUDGETS:
        label = str(n)
        arm = f"H{n}"
        training = [m["training"][label] for m in members]
        curves[label] = {
            "total_hands": n * len(members),
            **{key: sum(row[key] for row in training)
               for key in ("all_wager_opportunities", "all_wager_responses",
                           "unique_query_opportunities", "unique_query_responses", "unknown_turns")},
            "coverage": coverage(replies, arm), **proper(replies, arm), **results(cases, arm),
            "training_seconds": timings[f"training_{n}"],
            "profile_memory": peak[label], "panel_seconds": timings[f"panel_{n}"],
        }

    def aggregate(rows):
        return {"n": len(rows), "C_coverage": coverage(rows, "H300"), "D_coverage": coverage(rows, "H1500"),
                "arms": {arm: proper(rows, arm) for arm in ARMS}}

    def action_slice(rows):
        return {"n": len(rows), "mae": {arm: mean(
            abs(case["arms"][arm]["values"][label] - case["arms"]["E"]["values"][label])
            for case, label, _ in rows) for arm in ARMS}}

    def swing(case):
        return case["arms"]["D"]["regret"] - case["arms"]["A"]["regret"]

    harmful = sorted((case for case in cases if swing(case) > 1e-12), key=swing, reverse=True)
    aggregate_ev = {arm: results(cases, arm) for arm in ARMS}
    paired = {}
    for arm in ARMS[1:]:
        for baseline in (("A", "C") if arm == "D" else ("A",)):
            estimates = paired_interval(cells, lambda cell: mean(
                case["arms"][baseline]["mae"] - case["arms"][arm]["mae"]
                for member in cell["members"] for case in member["cases"]))
            paired[f"{arm}_over_{baseline}"] = estimates

    fallback_exact = all(row["probabilities"][arm] == row["probabilities"]["A"]
                         for row in replies for arm in (f"H{n}" for n in BUDGETS)
                         if row["coverage"][arm]["coverage"] != "supported")
    fallback_exact &= all(case["arms"][arm]["values"][label] == case["arms"]["A"]["values"][label]
                          for case, label, row in actions if row for arm in (f"H{n}" for n in BUDGETS)
                          if row["coverage"][arm]["coverage"] != "supported")
    old_new_coverage = {}
    for arm in ("H300", "H1500"):
        old_new_coverage[arm] = {key: action_slice(rows) for key, rows in group(
            actions, lambda item: item[2]["coverage"][arm]["coverage"] if item[2] else "no_future_reply").items()}
    old_cover = old_new_coverage["H300"]
    return {
        "clusters": len(cells), "decisions": len(cases), "replies": len(replies), "actions": len(actions),
        "curve": curves, "ev": aggregate_ev, "paired": paired, "overall_reply": aggregate(replies),
        "by_price": {str(price): aggregate(rows) for price, rows in group(replies, lambda row: row["price"]).items()},
        "by_category": {key: aggregate(rows) for key, rows in group(
            replies, lambda r: "closing shove" if r["context"]["closing"] else size(r["price"], r["pot"])).items()},
        "by_panel": {key: aggregate(rows) for key, rows in group(replies, lambda r: r["group"]).items()},
        "by_opponent": {f"{family}/{member}": {
            "ev": {arm: results(rows, arm) for arm in ARMS},
            "replies": aggregate([r for r in replies if (r["family"], r["member"]) == (family, member)]),
        } for (family, member), rows in group(cases, lambda r: (r["family"], r["member"])).items()},
        "action_by_coverage": old_new_coverage,
        "action_by_price": {str(price): action_slice(rows) for price, rows in group(
            [item for item in actions if item[2]], lambda item: item[2]["price"]).items()},
        "action_by_transition": {key: action_slice(rows) for key, rows in group(
            [item for item in actions if item[2]], lambda item:
            item[2]["coverage"]["H300"]["coverage"] + "_to_" + item[2]["coverage"]["H1500"]["coverage"]).items()},
        "profitable_call_opportunities": sum("profitable_call" in r["action_types"].values() for r in cases),
        "profitable_bluff_decisions": sum("profitable_bluff" in r["action_types"].values() for r in cases),
        "harmful_shove_opportunities": sum(r["bad_shove"] for r in cases),
        "harmful_cases": [{"added_regret": swing(case), **case} for case in harmful[:10]],
        "gates": {
            "D_vs_A_gain": paired["D_over_A"]["delta"] >= .10 and paired["D_over_A"]["ci95"][0] > 0,
            "D_vs_C_gain": paired["D_over_C"]["ci95"][0] > 0,
            "mean_regret": aggregate_ev["D"]["mean_regret"] - aggregate_ev["A"]["mean_regret"] <= .05,
            "worst_added_regret": aggregate_ev["D"]["worst_added_regret"] < 8.,
            "closed_calls_preserved": aggregate_ev["D"]["profitable_calls"] == aggregate_ev["E"]["profitable_calls"],
            "full_menu_supported": old_new_coverage["H1500"].get("supported", {}).get("n", 0) ==
                                   sum(bool(w) for _, _, w in actions),
            "historical_coverage_slices": all(old_cover.get(k, {}).get("n", 0) >= 32 and
                                             coverage(replies, "H300")[k] >= 32
                                             for k in ("supported", "sparse", "unsupported")),
            "exact_fallback": fallback_exact,
            "offline_runtime": timings["exact"]["max"] < 15 and timings["peak_mib"] < 768,
        },
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output
    assert load(out / "frozen.json") == source_manifest()
    primary = (out / "holdout-13.json").read_bytes()
    alternate = (out / "holdout-31.json").read_bytes()
    result = summarize(json.loads(primary), load(out / "holdout-13-timing.json"),
                       load(out / "profile-memory.json"))
    result["hash_seed_reproducibility"] = {"equal": primary == alternate,
                                         "sha256": sha256(primary).hexdigest()}
    write(out / "summary.json", result)
    if primary != alternate:
        raise ValueError("hash-seed parity failed")


if __name__ == "__main__":
    main()
