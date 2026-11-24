"""Run and resume offline paired simulator sessions."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from .bots import BOT_TYPES
from .duplicate_evaluation import DuplicateConfig, DuplicatePair, play_duplicate_pair, summarize_pairs


AGENT = "solver_adaptive"
OUTPUT = Path(__file__).resolve().parents[2] / "benchmark-results" / "agent"


@contextmanager
def _exclusive_run(path: Path):
    # An OS lock is released even when the process is interrupted. Keep the
    # sidecar's inode in place so a new process cannot acquire a different lock.
    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("this agent run is already open") from error
        yield


def _append(handle, record):
    handle.write(json.dumps(record, sort_keys=True).encode("utf-8") + b"\n")
    handle.flush()
    os.fsync(handle.fileno())


def _read_sessions(handle, header, seeds):
    records = []
    for index, line in enumerate(handle):
        if not line.endswith(b"\n"):
            # Only the final incomplete record is recoverable after a crash.
            handle.seek(-len(line), os.SEEK_CUR)
            handle.truncate()
            break
        record = json.loads(line)
        if index == 0:
            if record != header:
                raise ValueError("resume parameters do not match the run header")
            continue
        if index > len(seeds) or record.pop("session", None) != index:
            raise ValueError("session ledger is out of sequence")
        pair = DuplicatePair(**record)
        if (pair.seed != seeds[index - 1] or pair.hands_per_seat != header["configuration"]["session_hands"]
                or not pair.deal_verified):
            raise ValueError("session ledger has inconsistent deal metadata")
        records.append(pair)
    if handle.tell() == 0:
        _append(handle, header)
    handle.seek(0, os.SEEK_END)
    return records


def _save_summary(path: Path, report) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        scratch = Path(out.name)
        json.dump(report, out, sort_keys=True, indent=2)
        out.write("\n")
    try:
        scratch.replace(path)
    finally:
        scratch.unlink(missing_ok=True)


def run_sessions(output: Path, name: str, opponent: str, config: DuplicateConfig, *, resume: bool):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("run name must start with a letter or digit and contain up to 64 letters, digits, underscores or hyphens")
    output.mkdir(parents=True, exist_ok=True)
    ledger = output / f"{name}.jsonl"
    summary = output / f"{name}.summary.json"
    header = {"format_version": 1, "agent": AGENT, "opponent": opponent, "configuration": config.as_dict()}
    seeds = config.seeds()
    with _exclusive_run(output / f"{name}.lock"), ledger.open("r+b" if resume else "x+b") as handle:
        pairs = _read_sessions(handle, header, seeds)
        for index, seed in enumerate(seeds[len(pairs):], start=len(pairs) + 1):
            pair = play_duplicate_pair(config, AGENT, opponent, seed)
            if not pair.deal_verified:
                raise ValueError(f"deal mismatch in session {index}")
            _append(handle, {"session": index, **asdict(pair)})
            pairs.append(pair)
        report = {**header, **summarize_pairs(pairs, config), "sessions": len(pairs), "ledger": ledger.name}
        _save_summary(summary, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="name of this run and its output files")
    parser.add_argument("--opponent", choices=BOT_TYPES, default="tight")
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--session-hands", type=int, default=20, help="hands in each of two orientations")
    parser.add_argument("--seed-offset", type=int, default=0, help="offset within development seeds")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--resume", action="store_true", help="continue the same run with identical parameters")
    args = parser.parse_args(argv)
    try:
        config = DuplicateConfig(pairs=args.sessions, session_hands=args.session_hands, seed_offset=args.seed_offset)
        report = run_sessions(args.output_dir, args.run, args.opponent, config, resume=args.resume)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
