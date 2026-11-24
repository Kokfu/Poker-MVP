"""Measure real Coach observer calls in isolation and across four processes."""
from argparse import ArgumentParser
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

START = perf_counter()
from research.holdem import phase_5e_timing as timing
from research.holdem.phase_5e import latency, write

IMPORT_SECONDS = perf_counter() - START
WORKERS = 4


def child(directory):
    with TemporaryDirectory(dir=directory) as scratch:
        result = timing.run(Path(scratch))
    write(directory / "coach-timing.json", {**result, "worker_import_seconds": IMPORT_SECONDS})


def batch(output, workers):
    group = output / ("observer-isolated" if workers == 1 else "observer-concurrent")
    group.mkdir(exist_ok=False)
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "PYTHONHASHSEED": "13"}
    processes = []
    started = perf_counter()
    for worker in range(workers):
        directory = group / str(worker)
        directory.mkdir()
        with (directory / "worker.log").open("w", encoding="utf-8") as log:
            processes.append((directory, subprocess.Popen(
                [sys.executable, "-m", __spec__.name, str(directory), "--worker"],
                stdout=log, stderr=subprocess.STDOUT, env=env)))
    results = []
    for directory, process in processes:
        try:
            exit_code = process.wait(timeout=max(0., 360 - (perf_counter() - started)))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            exit_code = "worker_timeout"
        path = directory / "coach-timing.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        results.append({"exit": exit_code, **data})
    write(group / "results.json", {"wall_seconds": perf_counter() - started, "workers": results})
    cases = [case for row in results for case in row.get("cases", [])]
    enabled = [case for case in cases if case["enabled"]]
    checks = {
        "schedule_complete": len(cases) == 16 * workers and all(row["exit"] == 0 for row in results),
        "valid_advice": len(cases) == 16 * workers and all(case["source"] == "postflop_solve"
                          and case["legal"] and case["unchanged"] for case in cases),
        "all_traces_complete": len(enabled) == 12 * workers and all(case["shadow_status"] == "complete"
                               and abs(case["mix_total"] - 1) < 1e-12 for case in enabled),
        "coach_within_15s": len(cases) == 16 * workers and all(case["seconds"] < 15 for case in cases),
        "observer_within_150ms": len(enabled) == 12 * workers and all(case["shadow_seconds"] < .150
                                 for case in enabled),
        "memory_within_768mib": all(row.get("peak_mib", float("inf")) < 768 for row in results),
    }
    segments = {key: latency(values) for key in ("seconds", "cfr", "snapshot", "shadow_exact",
                "trace_write", "shadow_seconds") if (values := [case[key] for case in enabled if key in case])}
    for label, selection in (("first_per_case", enabled[::3]), ("repeat", [case for i, case in
                             enumerate(enabled) if i % 3])):
        if selection:
            segments[label] = latency([case["seconds"] for case in selection])
    write(group / "summary.json", {"checks": checks, "segments": segments, "enabled": len(enabled),
                                  "statuses": {status: sum(case["shadow_status"] == status for case in enabled)
                                               for status in ("complete", "error", "timeout")}})


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        child(args.directory)
    else:
        batch(args.directory, 1)
        batch(args.directory, WORKERS)
