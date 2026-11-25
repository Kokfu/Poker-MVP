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


def _run_report(header, pairs, config, ledger, *, learning=False):
    result = summarize_pairs(pairs, config)

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


def _learning_run(profile_dir, output, name, opponent, config, *, resume):
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

        pairs = [DuplicatePair(**record) for record in run["sessions"]]
        if len(pairs) > len(seeds) or any(
            pair.seed != seed or pair.hands_per_seat != config.session_hands or not pair.deal_verified
            for pair, seed in zip(pairs, seeds)
        ):
            raise ValueError("learning ledger has inconsistent session metadata")
        if len(pairs) < len(seeds):
            if data["active_run"] != name:
                raise ValueError("another run owns the learning checkpoint")
            profiles = restore_profiles(data["profiles"])
            for index, seed in enumerate(seeds[len(pairs):], start=len(pairs) + 1):
                pair = play_duplicate_pair(config, AGENT, opponent, seed, learning=profiles)
                if not pair.deal_verified:
                    raise ValueError(f"deal mismatch in session {index}")
                pairs.append(pair)
                run["sessions"].append(asdict(pair))
                data["profiles"] = encode_profiles(profiles)
                if index == len(seeds):
                    run["final_profile_hands"] = opponent_hands(data["profiles"])
                    data["active_run"] = None
                _save_summary(ledger, data)
        report = _run_report(header, pairs, config, ledger, learning=True)
        report["profile_hands"] = {"initial": run["initial_profile_hands"], "final": run["final_profile_hands"]}
        _save_summary(summary, report)
    return report


def run_sessions(output: Path, name: str, opponent: str, config: DuplicateConfig, *, resume: bool,
                 profile_dir: Path | None = None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("run name must start with a letter or digit and contain up to 64 letters, digits, underscores or hyphens")
    output.mkdir(parents=True, exist_ok=True)
    if profile_dir is not None:
        if opponent not in BOT_TYPES:
            raise ValueError(f"unknown opponent: {opponent}")
        return _learning_run(profile_dir, output, name, opponent, config, resume=resume)
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
        report = _run_report(header, pairs, config, ledger)
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
    parser.add_argument("--profile-dir", type=Path, help="carry one opponent profile across sessions and runs")
    parser.add_argument("--resume", action="store_true", help="continue the same run with identical parameters")
    args = parser.parse_args(argv)
    try:
        config = DuplicateConfig(pairs=args.sessions, session_hands=args.session_hands, seed_offset=args.seed_offset)
        report = run_sessions(args.output_dir, args.run, args.opponent, config, resume=args.resume,
                              profile_dir=args.profile_dir)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
