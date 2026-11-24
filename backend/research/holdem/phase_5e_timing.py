"""Timing probe of the existing Coach observer with unchanged budgets."""
from argparse import ArgumentParser
import json
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

START = perf_counter()

from coach import service as coach
from coach.store import HandStore
from research.holdem import phase_5d, river_shadow as shadow
from research.holdem.phase_4k import peak_resident_bytes, train
from research.holdem.phase_4v import coach_spot, stable
from research.holdem.phase_5e import latency, write
from solver.bot import SolverBot

IMPORT_SECONDS = perf_counter() - START
IDS = (78, 31, 0, 2)


def run(directory):
    schedule = list(phase_5d.schedule())
    store = HandStore(directory / "timing.sqlite")
    coach.log_hand(coach_spot("tight_aggressive"), "fixture", store)
    profile_replay = []
    for _ in range(8):
        started = perf_counter()
        assert coach.profile_for(store, "fixture").hands_observed == 1
        profile_replay.append(perf_counter() - started)
    timings = []
    for i in IDS:
        case, spot, style, wager, prefix, stream, _ = schedule[i]
        trained = train(style, stream, (prefix,))[prefix] if prefix else None

        class StoredSnapshot:
            hands_observed = prefix

            def snapshot(self):
                return trained.snapshot

        def attach(_store, _name, observer=None):
            if observer is not None:
                trained.attach(observer)
            return StoredSnapshot()

        given = dict(opponent="frozen" if prefix else None, store=store, seed=phase_5d.phase_5b.SEED)
        def timed(name, operation):
            def wrapped(*args, **kwargs):
                started = perf_counter()
                try:
                    return operation(*args, **kwargs)
                finally:
                    segments[name] = segments.get(name, 0.) + perf_counter() - started
            return wrapped

        with TemporaryDirectory(dir=directory) as trace_dir, patch.object(coach, "profile_for", attach):
            for attempt, enabled in enumerate(("1", "0", "1", "1")):
                segments = {}
                with patch.dict(environ, {shadow.FLAG: enabled, shadow.TRACE_DIR: trace_dir,
                                           "POKER_COACH_PERSISTENT_RANGES": "0"}), \
                        patch.object(SolverBot, "_solve", timed("cfr", SolverBot._solve)), \
                        patch.object(shadow, "snapshot", timed("snapshot", shadow.snapshot)), \
                        patch.object(shadow, "evaluate", timed("shadow_exact", shadow.evaluate)), \
                        patch.object(shadow, "write_trace", timed("trace_write", shadow.write_trace)):
                    started = perf_counter()
                    advice = coach.advise(spot, **given)
                    seconds = perf_counter() - started
                paths = sorted(Path(trace_dir).glob("*.json"))
                assert len(paths) == int(enabled == "1")
                trace = json.loads(paths[0].read_text(encoding="utf-8")) if paths else None
                if paths:
                    paths[0].unlink()
                if attempt == 0:
                    baseline = stable(advice)
                normalized = None if not trace or trace["status"] != "complete" else sum(trace["cfr_mix"].values())
                timings.append({"index": case.index, "wager": wager, "enabled": enabled == "1",
                                "seconds": seconds, "source": advice.get("explanation", {}).get("source"),
                                "legal": advice["advice"]["action"] in advice["state"]["legal_actions"],
                                "unchanged": baseline == stable(advice), "mix_total": normalized,
                                "shadow_status": trace["status"] if trace else None,
                                "shadow_seconds": trace["shadow_seconds"] if trace else None, **segments})
                print(json.dumps(timings[-1]), flush=True)
    fields = ("seconds", "cfr", "snapshot", "shadow_exact", "trace_write", "shadow_seconds")
    return {"cold_import_seconds": IMPORT_SECONDS, "profile_replay": latency(profile_replay),
            "summary": {field: latency([x[field] for x in timings if x["enabled"] and x.get(field) is not None])
                        for field in fields},
            "cases": timings, "peak_mib": peak_resident_bytes() / 2**20}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    output = parser.parse_args().directory
    with TemporaryDirectory(dir=output) as temp:
        write(output / "coach-timing.json", run(Path(temp)))
