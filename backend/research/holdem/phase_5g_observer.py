"""Assess heavier Coach contention and exercise concurrent offline evidence replay."""
from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from research.holdem import phase_5e as prior, phase_5f_observer as observer, river_shadow
from research.holdem.phase_5g import DEVELOPMENT, train
from research.holdem.phase_5g_summary import load


def independent_profiles():
    original, additional, *_ = DEVELOPMENT

    def aggregate(_):
        result = [(n, sorted(profile._opportunities.items()), sorted(profile._replies.items()),
                   sorted(allocations.items())) for n, profile, _, allocations, _
                  in train(2, 0, 0, original + 200, additional + 200, 500)]
        return result

    baseline = aggregate(0)
    with ThreadPoolExecutor(max_workers=8) as pool:
        copies = list(pool.map(aggregate, range(8)))
    return {"workers": len(copies), "hands_per_worker": 500,
            "all_equal": all(copy == baseline for copy in copies), "ownership": "one profile per worker"}


def shared_trace_directory(output):
    with TemporaryDirectory(dir=output) as folder, patch.dict(river_shadow.os.environ, {river_shadow.TRACE_DIR: folder}):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(river_shadow.write_trace, ({"writer_fixture": i} for i in range(96))))
        directory = Path(folder)
        records = [load(path)["writer_fixture"] for path in directory.glob("*.json")]
        return {"completed": len(records), "expected": 96, "unique": sorted(records) == list(range(96)),
                "pending": len(list(directory.glob("*.pending")))}


def summarize(out):
    directory = out / "observer-concurrent"
    workers = load(directory / "results.json")["workers"]
    rows = []
    exceptions = []
    for path in sorted(directory.glob("*/worker.log")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("{"):
                rows.append(json.loads(line))
            if "River shadow output failed" in line or "Traceback" in line:
                exceptions.append(line)
    enabled = [row for row in rows if row["enabled"]]
    stats = {key: prior.latency(values) for key in
             ("seconds", "shadow_seconds", "cfr", "snapshot", "shadow_exact", "trace_write")
             if (values := [r[key] for r in rows if r.get(key) is not None])}
    result = {"coach_scheduled": len(workers) * 16, "coach_returned": len(rows),
              "shadow_scheduled": len(workers) * 12,
              "shadow_status": dict(Counter(r["shadow_status"] for r in enabled)),
              "coach_at_or_over_15s": sum(row["seconds"] >= 15 for row in rows),
              "observer_at_or_over_150ms": sum(row["shadow_seconds"] >= .15 for row in enabled),
              "unexpected_fallbacks": sum(row["source"] != "postflop_solve" for row in rows),
              "changed_or_illegal_advice": sum(not (row["unchanged"] and row["legal"]) for row in rows),
              "trace_write_failures_logged": sum("River shadow output failed" in text for text in exceptions),
              "worker_exits": [worker["exit"] for worker in workers], "exceptions": exceptions,
              "timings": stats, "peak_worker_mib": max((w["peak_mib"] for w in workers if "peak_mib" in w), default=None),
              "worker_import_seconds": [w["worker_import_seconds"] for w in workers if "worker_import_seconds" in w],
              "profile_replay": [w["profile_replay"] for w in workers if "profile_replay" in w]}
    result["gate"] = (all(e == 0 for e in result["worker_exits"]) and
                      len(rows) == result["coach_scheduled"] and
                      result["shadow_status"].get("complete") == result["shadow_scheduled"] and
                      all(abs(row["mix_total"] - 1) < 1e-12 for row in enabled if row["shadow_status"] == "complete") and
                      not any(result[k] for k in ("coach_at_or_over_15s", "observer_at_or_over_150ms",
                                                 "unexpected_fallbacks", "changed_or_illegal_advice",
                                                 "trace_write_failures_logged")) and
                      all(w.get("peak_mib", 768) < 768 for w in workers))
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("coach", "diagnostics"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.stage == "coach":
        observer.batch(args.output, 8)
    else:
        prior.write(args.output / "contention.json", {"coach": summarize(args.output),
                    "aggregation": independent_profiles(), "shared_trace_directory": shared_trace_directory(args.output)})


if __name__ == "__main__":
    main()
