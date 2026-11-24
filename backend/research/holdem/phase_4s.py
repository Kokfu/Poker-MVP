"""Bounded, offline Phase 4S four-arm exact river benchmark."""
from argparse import ArgumentParser
import cProfile
from dataclasses import asdict
from hashlib import sha256
import json
from math import fsum
from pathlib import Path
import pstats
from statistics import mean, median
from time import perf_counter

import numpy as np

from coach.service import HERO, _replay
from research.holdem import phase_4o, phase_4p, phase_4q, phase_4r
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, peak_resident_bytes, train
from research.holdem.range_support import ResearchReplay, closing_policy
from research.holdem.river_bayes_reference import posterior
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import Opening, hand_group
from research.holdem.river_wager_reference import law
from simulation.actions import Action
from solver.bot import _EQUITY_CACHE, _full_equity, replay_hand
from solver.combos import combo_index


PANELS = {"development": (439201, 4, (161,)), "holdout": (439202, 8, (171, 172, 173))}
ARMS = ("A", "B", "C", "D")
CONTRASTS = {"B-A": (-1, 1, 0, 0), "C-A": (-1, 0, 1, 0), "D-A": (-1, 0, 0, 1),
             "D-B": (0, -1, 0, 1), "interaction": (1, -1, -1, 1)}


def schedule(panel):
    seed, count, streams = PANELS[panel]
    by_stream = [list(phase_4q.cases(seed, count, i)) for i in range(len(streams))]
    return [(cases[index], stream, phase_4r.PREFIXES[(index + i) % 4], name)
            for index in range(count) for i, (cases, stream) in enumerate(zip(by_stream, streams))
            for name in STYLES]


def exact_reference(case, ds, style):
    replay = replay_hand(ds)
    villain = 1 - replay.current.to_act
    steps = [step for step in replay.steps if step.player == villain]
    preflop = tuple(phase_4p.observations(replay, villain, case.seat == "button"))
    universe = ExactRiverEV(case.hero, case.board, lambda *_: 1).holdings
    pairs = [holding.combo for holding in universe]
    prior = phase_4p.reference_weights(pairs, preflop, case.depth, style)
    for step in steps[:-1]:
        if step.street != "preflop":
            board = list(case.board[:3 if step.street == "flop" else 4])
            prior *= [phase_4p.reference_likelihood(step, style, pair, RANKER.score(list(pair), board))
                      for pair in pairs]
    before = steps[-1].before
    opening = Opening(before.pot, before.stack[villain], before.stack[1 - villain],
                      before.last_full_raise, case.line[1] != "check")
    observed, _, _ = opening.action(steps[-1].target)
    wager = [law(opening, hand_group(h.combo, case.board, h.rank), style)[observed] for h in universe]
    pre, likelihood = dict(zip(pairs, prior, strict=True)), dict(zip(pairs, wager, strict=True))
    truth = posterior(case.hero, case.board, pre.__getitem__, likelihood.__getitem__)
    exact = ExactRiverEV(case.hero, case.board, lambda pair, _: pre[pair] * likelihood[pair])
    np.testing.assert_allclose(list(truth.values()), [h.weight for h in exact.holdings], atol=1e-14, rtol=0)
    return exact


def decision_factor(bot, ds, parent):
    started = perf_counter()
    if "failure" in parent:
        return {**parent, "decision_seconds": perf_counter() - started}
    node = bot.live_node
    mix, bounds = closing_policy(bot, node, ds)
    chosen = bot._pick(ds, mix)
    keys = parent["keys"]
    values = parent["exact_action_ev"]
    seconds = perf_counter() - started
    assert np.isfinite(mix).all() and (mix >= 0).all() and abs(fsum(mix) - 1) < 1e-12
    ev = float(mix @ list(values.values()))
    if bounds:
        truth = values[keys[1]] * BIG_BLIND
        bounds["covered"] = bounds["lower"] - 1e-8 <= truth <= bounds["upper"] + 1e-8
        bounds["true_call_ev"] = truth
    return {"mix": dict(zip(keys, mix.tolist(), strict=True)), "ev": ev, "regret": max(values.values()) - ev,
            "chosen": keys[chosen], "bounds": bounds, "decision_seconds": seconds,
            "seconds": parent["seconds"] + seconds}


def evaluate(case, stream, prefix, name, profile, *, exact=None, alternate=False):
    status, _, engine = _replay(case.spot())
    assert status == "hero_to_act"
    ds = engine.decision_observation(HERO).decision_state
    assert sum(engine.state.stacks.values()) + engine.state.pot == 2 * case.depth * BIG_BLIND
    style = STYLES[name]
    if exact is None:
        exact = exact_reference(case, ds, style)
    order = (("B", True), ("A", False)) if alternate else (("A", False), ("B", True))
    arms = {}
    for key, separate in order:
        bot = ResearchReplay(separate)
        record = phase_4r.arm(bot, case, profile, exact, style, ds)
        if bot.estimate is not None:
            ids = [combo_index(h.combo) for h in exact.holdings]
            modeled = bot.estimate[ids]
            assert abs(fsum(modeled) - 1) < 1e-12
            record["persistent"] = {"positive": int(np.count_nonzero(modeled)),
                                    "effective": float(1 / (modeled @ modeled))}
        record["working_sets"] = [
            {"street": street, "seats": [
                {"columns": len(w.ids), "positive": w.positive, "retained": w.retained, "omitted": w.omitted}
                for w in seats]}
            for street, seats in bot.projections
        ]
        arms[key] = record
        arms["D" if separate else "C"] = decision_factor(bot, ds, record)
    a, b = arms["A"], arms["B"]
    fallback = [key for key in ARMS if "failure" in arms[key]]
    successful = [record for record in (a, b) if "failure" not in record]
    if len(successful) == 2:
        assert a["keys"] == b["keys"] and a["exact_action_ev"] == b["exact_action_ev"]
    values = successful[0]["exact_action_ev"] if successful else {}
    for key in fallback:
        record = arms[key]
        action = label(Action(*record["fallback_action"]))
        if action in values:
            record.update(mix={action: 1.}, ev=values[action], regret=max(values.values()) - values[action])
    return {"case": asdict(case), "opponent": name, "stream": stream, "prefix": prefix,
            "closing": ds.opponent_stack == 0 and "fold" in ds.legal_actions,
            "exact_action_ev": values, "arms": arms}


def summarize(rows):
    failures = [{"case": r["case"]["index"], "stream": r["stream"], "opponent": r["opponent"],
                 "arm": key, "reason": record["failure"]}
                for r in rows for key, record in r["arms"].items() if "failure" in record]
    matched = [r for r in rows if all("ev" in r["arms"][key] for key in ARMS)]
    summary = {"rows": len(rows), "matched": len(matched), "failures": failures}
    if not matched:
        return summary
    boards = sorted({r["case"]["index"] for r in rows})
    streams = sorted({r["stream"] for r in rows})
    rng = np.random.default_rng(43903)
    bi = rng.integers(len(boards), size=(10000, len(boards), 1))
    si = rng.integers(len(streams), size=(10000, 1, len(streams)))
    ev = np.array([[r["arms"][key]["ev"] for key in ARMS] for r in matched])
    summary["contrasts"] = {}
    for key, coefficient in CONTRASTS.items():
        deltas = (ev @ coefficient).tolist()
        harms = [(r, d) for r, d in zip(matched, deltas) if d < -.01]
        by_style = {name: mean(d for r, d in zip(matched, deltas) if r["opponent"] == name) for name in STYLES
                    if any(r["opponent"] == name for r in matched)}
        interval = None
        if len(rows) == len(matched) and len(streams) > 1:
            cells = {(board, stream): [] for board in boards for stream in streams}
            for r, delta in zip(matched, deltas):
                cells[r["case"]["index"], r["stream"]].append(delta)
            matrix = np.array([[mean(cells[board, stream]) for stream in streams] for board in boards])
            interval = np.quantile(matrix[bi, si].mean(axis=(1, 2)), (.025, .975)).tolist()
        summary["contrasts"][key] = {
            "mean": mean(deltas), "interval": interval, "by_style": by_style, "worst": min(deltas),
            "harm_count": len(harms), "harm_cost": -fsum(d for d in deltas if d < 0),
            "harms": [{"case": r["case"]["index"], "stream": r["stream"], "opponent": r["opponent"], "delta": d}
                      for r, d in sorted(harms, key=lambda pair: pair[1])],
        }
    summary["arms"] = {}
    for key in ARMS:
        records = [r["arms"][key] for r in matched]
        closing = [r["arms"][key]["mix"].get("call", 0.) + r["arms"][key]["mix"].get("all_in", 0.)
                   for r in matched if r["closing"]]
        coverage = {}
        for prefix in phase_4r.PREFIXES:
            bounds = [r["arms"][key]["bounds"] for r in matched
                      if r["prefix"] == prefix and r["arms"][key].get("bounds")]
            coverage[prefix] = [sum(b["covered"] for b in bounds), len(bounds)]
        summary["arms"][key] = {
            "mean_ev": mean(r["ev"] for r in records), "mean_regret": mean(r["regret"] for r in records),
            "closing_rows": len(closing), "mean_closing_cover": mean(closing) if closing else None,
            "median_seconds": median(r["arms"][key]["seconds"] for r in rows),
            "max_seconds": max(r["arms"][key]["seconds"] for r in rows), "coverage": coverage,
        }
    return summary


def historical(archive):
    case = phase_4r.failed_case()
    rows = [evaluate(case, 131, 3, "tight_aggressive", train("tight_aggressive", 131, (3,))[3])]
    specs = (("historical", ("Js", "3c"), "loose_aggressive", 91, phase_4o.Case),
             ("diagnostic-13", ("Kc", "As"), "tight_passive", 132, phase_4q.WagerCase))
    for filename, hero, name, stream, case_type in specs:
        reference = json.loads((archive / f"{filename}.json").read_text(encoding="utf-8-sig"))
        row = next(r for r in reference["rows"] if tuple(r["case"]["hero"]) == hero
                   and r["opponent"] == name and r["stream"] == stream)
        case = case_type(**{**row["case"], "hero": hero, "board": tuple(row["case"]["board"]),
                            "line": tuple(row["case"]["line"])})
        evidence = row["evidence"]
        truth = dict(zip(map(tuple, evidence["combos"]), evidence["true_posterior"], strict=True))
        exact = ExactRiverEV(case.hero, case.board, lambda pair, _: truth[pair])
        prefix = row["hands"]
        profile = train(name, stream, (prefix,))[prefix] if prefix else None
        rows.append(evaluate(case, stream, prefix, name, profile, exact=exact))
    return {"rows": rows}


def profile_replay(separate):
    case, stream, prefix, name = schedule("development")[-1]
    profile = train(name, stream, (prefix,))[prefix] if prefix else None
    _EQUITY_CACHE.clear()
    samples = {}
    for temperature in ("cold", "warm"):
        start = perf_counter()
        ResearchReplay(separate).trace(case.spot(), profile)
        samples[temperature] = perf_counter() - start
    profiler = cProfile.Profile()
    profiler.runcall(ResearchReplay(separate).trace, case.spot(), profile)
    names = {"_decide", "_solve", "_street_solve", "_apply_strategy", "_range_report", "card_mask",
             "conditional_range", "working_set", "update_reach", "_full_equity", "iterate", "_terminal_values",
             "replay_hand"}
    timings = []
    for (filename, _, function), (primitive, calls, self_time, total, _) in pstats.Stats(profiler).stats.items():
        if function in names:
            timings.append({"file": Path(filename).name, "function": function, "calls": calls,
                            "self_seconds": self_time, "cumulative_seconds": total})
    return {"samples": samples, "warm_profile": sorted(timings, key=lambda row: -row["cumulative_seconds"]),
            "process_peak_resident_bytes": peak_resident_bytes()}


def write_json(path, value):
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, allow_nan=False, separators=(",", ":"))
        out.write("\n")


def scheduled_cases():
    return [dict(case=asdict(case), stream=s, prefix=p, opponent=n) for case, s, p, n in schedule("holdout")]


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("panel", choices=(*PANELS, "historical", "profile-A", "profile-B", "freeze"))
    cli.add_argument("output", type=Path)
    cli.add_argument("--manifest", type=Path)
    cli.add_argument("--archive", type=Path)
    args = cli.parse_args()
    start = perf_counter()
    if args.panel == "freeze":
        repo = Path(__file__).resolve().parents[3]
        directories = ("coach", "simulation", "solver", "research")
        sources = [p for directory in directories for p in (repo / "backend" / directory).rglob("*")
                   if p.is_file() and p.suffix in (".py", ".npz")]
        sources.extend(repo / name for name in ("PHASE_4S_PROTOCOL.md", "backend/poker_analyzer.py"))
        write_json(args.output, {"sources": {p.relative_to(repo).as_posix(): sha256(p.read_bytes()).hexdigest()
                                               for p in sorted(sources)}, "cases": scheduled_cases()})
        return
    if args.panel == "historical":
        result = historical(args.archive)
    elif args.panel.startswith("profile"):
        result = profile_replay(args.panel == "profile-B")
    else:
        if args.panel == "holdout":
            if args.manifest is None:
                cli.error("holdout requires --manifest")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            repo = Path(__file__).resolve().parents[3]
            for name, digest in manifest["sources"].items():
                if sha256((repo / name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"frozen source changed: {name}")
            if json.dumps(manifest["cases"]) != json.dumps(scheduled_cases()):
                raise ValueError("frozen holdout case schedule changed")
        _, _, streams = PANELS[args.panel]
        profiles = {(stream, name): train(name, stream, phase_4r.PREFIXES[1:]) for stream in streams for name in STYLES}
        rows = []
        previous_board = None
        for index, (case, stream, prefix, name) in enumerate(schedule(args.panel)):
            if case.board != previous_board:
                for length in (3, 4, 5):
                    _full_equity(case.board[:length], ResearchReplay.flop_runouts)
                print(f"Board {case.index + 1} starting after {index} rows", flush=True)
                previous_board = case.board
            rows.append(evaluate(case, stream, prefix, name, profiles[stream, name].get(prefix), alternate=index % 2))
        result = {"rows": rows, "summary": summarize(rows)}
    result.update(wall_seconds=perf_counter() - start, process_peak_resident_bytes=peak_resident_bytes())
    write_json(args.output, result)


if __name__ == "__main__":
    main()
