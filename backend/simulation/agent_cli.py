"""Run and resume offline paired simulator sessions."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
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


def _report_checkpoint(name: str, index: int, total: int) -> None:
    print(f"{datetime.now().astimezone().isoformat()} checkpoint {name} {index}/{total} sessions committed",
          file=sys.stderr, flush=True)


def _decode_session(record):
    fields = record.copy()
    fallback = fields.pop("solver_fallback_actions", None)
    if fallback is not None and (type(fallback) is not int or fallback < 0):
        raise ValueError("session ledger contains an invalid solver fallback count")
    return DuplicatePair(**fields), fallback


def _read_sessions(handle, header, seeds, *, repair=True):
    records = []
    for index, line in enumerate(handle):
        if not line.endswith(b"\n"):
            # Only the final incomplete record is recoverable after a crash.
            if repair:
                handle.seek(-len(line), os.SEEK_CUR)
                handle.truncate()
            break
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError("each agent ledger record must be a JSON object")
        if index == 0:
            if record != header:
                raise ValueError("resume parameters do not match the run header")
            continue
        if index > len(seeds) or record.pop("session", None) != index:
            raise ValueError("session ledger is out of sequence")
        pair, fallback = _decode_session(record)
        if (pair.seed != seeds[index - 1] or pair.hands_per_seat != header["configuration"]["session_hands"]
                or not pair.deal_verified):
            raise ValueError("session ledger has inconsistent deal metadata")
        records.append((pair, fallback))
    if repair:
        if handle.tell() == 0:
            _append(handle, header)
        handle.seek(0, os.SEEK_END)
    return records


def _save_summary(path: Path, report) -> None:
    scratch = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
            scratch = Path(out.name)
            json.dump(report, out, sort_keys=True, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        scratch.replace(path)
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)


def _run_report(header, sessions, config, ledger, *, learning=False):
    pairs = [pair for pair, _ in sessions]
    result = summarize_pairs(pairs, config)
    known = [fallback for _, fallback in sessions if fallback is not None]
    result["solver_fallback_coverage_sessions"] = len(known)
    result["solver_fallback_actions"] = sum(known) if len(known) == len(sessions) else None

    def bb_per_100(selection):
        return 100 * sum(pair.net for pair in selection) / config.big_blind / sum(pair.hands for pair in selection)

    result["by_session"] = [{"session": index, "hands": pair.hands, "bb_per_100": bb_per_100([pair])}
                            for index, pair in enumerate(pairs, start=1)]
    midpoint = len(pairs) // 2
    if midpoint:
        result["early_vs_late"] = {
            "early_bb_per_100": bb_per_100(pairs[:midpoint]),
            "late_bb_per_100": bb_per_100(pairs[midpoint:]),
            "early_sessions": midpoint, "late_sessions": len(pairs) - midpoint,
        }
    if learning:
        # A later session trains on earlier sessions, violating the
        # independent-unit assumption of this bootstrap.
        for key in ("confidence_interval", "interpretation", "standard_error_bb_per_100",
                    "unpaired_standard_error_bb_per_100", "variance_reduction"):
            result.pop(key, None)
    return {**header, **result, "sessions": len(pairs), "ledger": ledger.name}


def inspect_ledger(ledger: Path) -> dict:
    """Summarize complete records from an independent run without opening it for writes."""
    with BytesIO(ledger.read_bytes()) as snapshot:
        first = snapshot.readline()
        if not first.endswith(b"\n"):
            raise ValueError("agent ledger has no complete header")
        header = json.loads(first)
        if (not isinstance(header, dict) or header.get("format_version") != 1 or header.get("agent") != AGENT
                or header.get("opponent") not in BOT_TYPES):
            raise ValueError("file is not a supported independent agent ledger")
        config = DuplicateConfig(**header["configuration"])
        snapshot.seek(0)
        sessions = _read_sessions(snapshot, header, config.seeds(), repair=False)
    report = _run_report(header, sessions, config, ledger)
    report["planned_sessions"] = config.pairs
    report["complete"] = len(sessions) == config.pairs
    if len(sessions) < 2:
        report["confidence_interval"] = None
        report["interpretation"] = None
    if not sessions:
        report["bb_per_100"] = None
    return report


def _learning_run(profile_dir, output, name, opponent, config, *, resume, progress):
    from .agent_profiles import encode_profiles, opponent_hands, restore_profiles

    profile_dir.mkdir(parents=True, exist_ok=True)
    ledger = profile_dir / f"{opponent}.profile.json"
    header = {"format_version": 1, "agent": AGENT, "opponent": opponent,
              "configuration": config.as_dict(), "persistent_learning": True}
    identity = {"profile_version": 1, "agent": AGENT, "opponent": opponent}
    seeds = config.seeds()
    with _exclusive_run(ledger.with_suffix(".lock")), _exclusive_run(output / f"{name}.lock"):
        if (output / f"{name}.jsonl").exists():
            raise ValueError("this name is already used by an independent run")
        data = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else {
            **identity, "active_run": None, "runs": {}, "profiles": None,
        }
        if any(data.get(key) != value for key, value in identity.items()):
            raise ValueError("profile version, agent, or opponent does not match")
        runs = data["runs"]
        summary = output / f"{name}.summary.json"
        if resume:
            run = runs.get(name)
            if run is None or run["header"] != header:
                raise ValueError("resume parameters do not match a saved learning run")
        else:
            if name in runs or summary.exists():
                raise FileExistsError("this agent run already exists")
            if data["active_run"] is not None:
                raise ValueError(f"resume the unfinished run {data['active_run']} first")
            for previous in runs.values():
                prior = DuplicateConfig(**previous["header"]["configuration"])
                prior_seeds = prior.seeds()
                if seeds[0] < prior_seeds[-1] + prior.session_hands and prior_seeds[0] < seeds[-1] + config.session_hands:
                    raise ValueError("learning runs need deal seeds that do not overlap earlier runs")
            run = runs[name] = {"header": header, "sessions": [],
                                "initial_profile_hands": opponent_hands(data["profiles"])}
            data["active_run"] = name
            _save_summary(ledger, data)

        sessions = [_decode_session(record) for record in run["sessions"]]
        if len(sessions) > len(seeds) or any(
            pair.seed != seed or pair.hands_per_seat != config.session_hands or not pair.deal_verified
            for (pair, _), seed in zip(sessions, seeds)
        ):
            raise ValueError("learning ledger has inconsistent session metadata")
        if len(sessions) < len(seeds):
            if data["active_run"] != name:
                raise ValueError("another run owns the learning checkpoint")
            profiles = restore_profiles(data["profiles"])
            for index, seed in enumerate(seeds[len(sessions):], start=len(sessions) + 1):
                diagnostics = {}
                pair = play_duplicate_pair(config, AGENT, opponent, seed, learning=profiles, diagnostics=diagnostics)
                if not pair.deal_verified:
                    raise ValueError(f"deal mismatch in session {index}")
                sessions.append((pair, diagnostics["solver_fallback_actions"]))
                run["sessions"].append({**asdict(pair), **diagnostics})
                data["profiles"] = encode_profiles(profiles)
                if index == len(seeds):
                    run["final_profile_hands"] = opponent_hands(data["profiles"])
                    data["active_run"] = None
                _save_summary(ledger, data)
                if progress:
                    _report_checkpoint(name, index, len(seeds))
        report = _run_report(header, sessions, config, ledger, learning=True)
        report["profile_hands"] = {"initial": run["initial_profile_hands"], "final": run["final_profile_hands"]}
        _save_summary(summary, report)
    return report


def run_sessions(output: Path, name: str, opponent: str, config: DuplicateConfig, *, resume: bool,
                 profile_dir: Path | None = None, progress: bool = False):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("run name must start with a letter or digit and contain up to 64 letters, digits, underscores or hyphens")
    output.mkdir(parents=True, exist_ok=True)
    if profile_dir is not None:
        if opponent not in BOT_TYPES:
            raise ValueError(f"unknown opponent: {opponent}")
        return _learning_run(profile_dir, output, name, opponent, config, resume=resume, progress=progress)
    ledger = output / f"{name}.jsonl"
    summary = output / f"{name}.summary.json"
    header = {"format_version": 1, "agent": AGENT, "opponent": opponent, "configuration": config.as_dict()}
    seeds = config.seeds()
    with _exclusive_run(output / f"{name}.lock"):
        if not resume and summary.exists():
            raise FileExistsError("this agent run already exists")
        with ledger.open("r+b" if resume else "x+b") as handle:
            sessions = _read_sessions(handle, header, seeds)
            for index, seed in enumerate(seeds[len(sessions):], start=len(sessions) + 1):
                diagnostics = {}
                pair = play_duplicate_pair(config, AGENT, opponent, seed, diagnostics=diagnostics)
                if not pair.deal_verified:
                    raise ValueError(f"deal mismatch in session {index}")
                _append(handle, {"session": index, **asdict(pair), **diagnostics})
                sessions.append((pair, diagnostics["solver_fallback_actions"]))
                if progress:
                    _report_checkpoint(name, index, len(seeds))
        report = _run_report(header, sessions, config, ledger)
        _save_summary(summary, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    entry = parser.add_mutually_exclusive_group(required=True)
    entry.add_argument("--run", help="name of this run and its output files")
    entry.add_argument("--inspect", type=Path, metavar="LEDGER", help="report complete sessions from an independent JSONL ledger")
    parser.add_argument("--opponent", choices=BOT_TYPES, default="tight")
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--session-hands", type=int, default=20, help="hands in each of two orientations")
    parser.add_argument("--seed-offset", type=int, default=0, help="offset within development seeds")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--profile-dir", type=Path, help="carry one opponent profile across sessions and runs")
    parser.add_argument("--resume", action="store_true", help="continue the same run with identical parameters")
    parser.add_argument("--progress", action="store_true", help="log durable session checkpoints to stderr")
    args = parser.parse_args(argv)
    try:
        if args.inspect is not None:
            if args.resume or args.profile_dir is not None:
                parser.error("--inspect reads an independent ledger and cannot resume a run")
            report = inspect_ledger(args.inspect)
        else:
            config = DuplicateConfig(pairs=args.sessions, session_hands=args.session_hands, seed_offset=args.seed_offset)
            report = run_sessions(args.output_dir, args.run, args.opponent, config, resume=args.resume,
                                  profile_dir=args.profile_dir, progress=args.progress)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
