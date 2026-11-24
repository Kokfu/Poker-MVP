"""Frozen offline Phase 4T comparison using the Phase 4S exact river evaluator."""
from argparse import ArgumentParser
import cProfile
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import pstats
from statistics import mean
from time import perf_counter

import numpy as np

from coach.service import HERO, _replay
from research.holdem import phase_4o, phase_4p, phase_4q, phase_4r, phase_4s
from research.holdem.decoupled_replay import DecoupledReplay, hand_tiers
from research.holdem.phase_4k import BIG_BLIND, RANKER, STYLES, label, peak_resident_bytes, train
from research.holdem.phase_4l import modeled_continuation, normalize, payoff_values
from research.holdem.phase_4m import oracle_response, reply_nodes
from research.holdem.range_support import ResearchReplay, closing_bounds
from research.holdem.river_ev import ExactRiverEV
from research.holdem.river_wager_calibration import Opening, hand_group
from research.holdem.river_wager_reference import law as reference_law
from simulation.actions import Action
from solver.bot import _EQUITY_CACHE, _full_equity, replay_hand
from solver.combos import combo_index


PANELS = {"development": (440201, 4, (181,)), "holdout": (440202, 8, (191, 192, 193))}
ARMS = ("A", "B", "C", "D", "E")
CONTRASTS = {"B-A": (-1, 1, 0, 0, 0), "C-A": (-1, 0, 1, 0, 0),
             "D-A": (-1, 0, 0, 1, 0), "E-A": (-1, 0, 0, 0, 1),
             "D-B": (0, -1, 0, 1, 0), "E-D": (0, 0, 0, -1, 1),
             "E-C": (0, 0, -1, 0, 1), "interaction": (0, 1, -1, -1, 1)}
REPO = Path(__file__).resolve().parents[3]


def schedule(panel):
    seed, count, streams = PANELS[panel]
    by_stream = [list(phase_4q.cases(seed, count, i)) for i in range(len(streams))]
    return [(cases[index], stream, phase_4r.PREFIXES[(index + i) % 4], name)
            for index in range(count) for i, (cases, stream) in enumerate(zip(by_stream, streams))
            for name in STYLES]


class BaselineTrace(ResearchReplay):
    def __init__(self, bounded):
        super().__init__(bounded)
        self.solves = []

    def _solve(self, state, *args, **kwargs):
        result = super()._solve(state, *args, **kwargs)
        self.solves.append({"street": state.street, "iterations": self.iterations[state.street],
                            "columns": [len(ids) for ids in result.combos], "seconds": result.seconds})
        return result


def tv(first, second):
    return float(np.abs(first - second).sum() / 2)


def compare_likelihood(case, bot, exact, style, vectors):
    """Score the actual river opening law under a fixed reference incoming range."""
    holdings = exact.holdings
    pairs = [hand.combo for hand in holdings]
    ids = np.array([combo_index(pair) for pair in pairs])
    truth = np.array([hand.weight for hand in holdings])
    villain = 1 - bot.live_node.player
    history = [entry for entry in bot.observations if entry.step.player == villain]
    observed = history[-1]
    step, state = observed.step, observed.step.before
    assert state.street == "river" and state.highest == 0
    opening = Opening(state.pot, state.stack[villain], state.stack[1 - villain],
                      state.last_full_raise, case.line[1] != "check")
    reference_prior = phase_4p.reference_weights(
        pairs, phase_4p.observations(replay_hand(bot.decision_state), villain, case.seat == "button"), case.depth, style)
    earlier_errors = []
    for entry in history[:-1]:
        reference_chance = np.array([
            phase_4p.reference_likelihood(entry.step, style, pair, RANKER.score(list(pair), list(entry.board)))
            for pair in pairs])
        columns = np.searchsorted(entry.law.live, ids)
        modeled = entry.law.probabilities[entry.law.index(entry.step), columns]
        reference_prior = normalize(reference_prior)
        earlier_errors.append({"street": entry.step.street, "action": entry.step.kind,
                               "weighted_abs": float(reference_prior @ np.abs(reference_chance - modeled))})
        reference_prior *= reference_chance
    reference_prior = normalize(reference_prior)
    true_probs = np.array([reference_law(opening, hand_group(h.combo, case.board, h.rank), style)
                           for h in holdings]).T
    true_probs = true_probs[[i for i, target in enumerate(opening.targets) if target is not None]]
    expected_targets = tuple(target for target in opening.targets if target is not None)
    assert tuple(target or 0 for _, target in observed.law.actions) == expected_targets
    modeled_probs = observed.law.probabilities[:, np.searchsorted(observed.law.live, ids)]
    assert np.allclose(modeled_probs.sum(axis=0), 1, rtol=0, atol=1e-12)
    which = observed.law.index(step)
    true_like, modeled_like = true_probs[which], modeled_probs[which]
    modeled_prior = normalize(observed.prior[ids])
    reconstructed = normalize(modeled_prior * modeled_like)
    np.testing.assert_allclose(reconstructed, bot.estimate[ids], rtol=0, atol=1e-14)
    np.testing.assert_allclose(normalize(reference_prior * true_like), truth, rtol=0, atol=1e-14)
    likelihood_only = normalize(reference_prior * modeled_like)
    prior_only = normalize(modeled_prior * true_like)
    result = {
        "earlier_observed_errors": earlier_errors,
        "joint_total_variation": float(reference_prior @ (np.abs(true_probs - modeled_probs).sum(axis=0) / 2)),
        "excess_brier": float(reference_prior @ ((true_probs - modeled_probs) ** 2).sum(axis=0)),
        "observed_abs_error": float(reference_prior @ np.abs(true_like - modeled_like)),
        "reference_observed_rate": float(reference_prior @ true_like),
        "same_prior_modeled_rate": float(reference_prior @ modeled_like),
        "incoming_prior_tv": tv(modeled_prior, reference_prior),
        "matched_prior_posterior_tv": tv(likelihood_only, truth),
        "matched_likelihood_posterior_tv": tv(prior_only, truth),
    }
    if vectors:
        results = np.array([h.result for h in holdings])
        state = bot.live_node.state
        hero = state.to_act
        cost = min(state.stack[hero], state.highest - state.commit[hero])
        call_leaf = bot.river.tree.nodes[bot.live_node.children[1]]
        matched_pot = sum(call_leaf.contribution)
        payoffs = np.array([-cost, (matched_pot + int(bot.decision_state.acting_player == "b")) // 2 - cost,
                            matched_pot - cost])
        crossed = {}
        for key, weights in (("nominal", reconstructed), ("truth", truth),
                             ("true_prior_only", likelihood_only), ("true_likelihood_only", prior_only)):
            masses = np.array([weights[results == outcome].sum() for outcome in (-1, 0, 1)])
            crossed[key] = {"call_bb": float(masses @ payoffs / BIG_BLIND), "outcomes": masses.tolist(),
                            "bounds_bb": (np.array(closing_bounds(masses, payoffs)) / BIG_BLIND).tolist()}
        result["closing_sensitivity"] = {"cost": cost, "contested_pot": matched_pot,
                                         "price": cost / matched_pot, "fold_bb": 0., "crossed": crossed}
        result["vectors"] = {"combos": pairs, "modeled_prior": modeled_prior.tolist(),
                             "true_prior": reference_prior.tolist(), "modeled_likelihood": modeled_like.tolist(),
                             "true_likelihood": true_like.tolist()}
    return result


def future_reply_diagnostic(bot, exact, style):
    """Change future reply forecasts while holding the exact posterior fixed."""
    node = bot.live_node
    tree = bot.river.tree
    nodes = reply_nodes(tree, node)
    if not nodes:
        return None
    _, _, modeled, hero_policy, _ = modeled_continuation(bot, node, exact.holdings)
    truth = np.array([h.weight for h in exact.holdings])
    oracle = {reply.index: oracle_response(reply, exact.holdings, style, False) for reply in nodes}
    errors = [float(truth @ ((modeled[index] - sigma) ** 2).sum(axis=0)) for index, sigma in oracle.items()]
    delta = (payoff_values(tree, node, exact.holdings, truth, oracle, hero_policy)
             - payoff_values(tree, node, exact.holdings, truth, modeled, hero_policy)) / BIG_BLIND
    return {"excess_brier": mean(errors), "max_action_ev_change": float(np.abs(delta).max())}


def evaluate(case, stream, prefix, name, profile, *, order=0, exact=None, vectors=False):
    status, _, engine = _replay(case.spot())
    assert status == "hero_to_act"
    ds = engine.decision_observation(HERO).decision_state
    assert sum(engine.state.stacks.values()) + engine.state.pot == 2 * case.depth * BIG_BLIND
    style = STYLES[name]
    normal_reference = exact is None
    if normal_reference:
        exact = phase_4s.exact_reference(case, ds, style)
    parents = [("A", BaselineTrace(False)), ("B", BaselineTrace(True)), ("D", DecoupledReplay())]
    arms = {}
    ids = [combo_index(h.combo) for h in exact.holdings]
    truth = np.array([h.weight for h in exact.holdings])
    vectors_by_arm = {"truth": truth.tolist()} if vectors else None
    inference, replies = None, {}
    for key, bot in parents[order:] + parents[:order]:
        record = phase_4r.arm(bot, case, profile, exact, style, ds)
        arms[key] = record
        if "failure" not in record:
            modeled = bot.estimate[ids]
            assert np.isfinite(modeled).all() and (modeled >= 0).all()
            assert abs(modeled.sum() - 1) < 1e-12
            record.update(posterior_tv=tv(modeled, truth), posterior_positive=int(np.count_nonzero(modeled)),
                          persistent_effective=float(1 / (modeled @ modeled)),
                          chosen=record["keys"][bot._pick(ds, bot.probabilities)])
            if vectors:
                vectors_by_arm[key] = modeled.tolist()
            if not (ds.opponent_stack == 0 and "fold" in ds.legal_actions):
                replies[key] = future_reply_diagnostic(bot, exact, style)
        if key == "D":
            record["stage_seconds"] = bot.stage_seconds
            if "failure" not in record:
                record["solves"] = [{"street": ds.street, "iterations": bot.river.solver.iterations,
                                     "columns": [len(x) for x in bot.river.combos], "seconds": bot.river.seconds}]
                assert len(bot.projections) == 1
                assert max(len(x) for x in bot.river.combos) <= bot.selection.limit
                if normal_reference:
                    inference = compare_likelihood(case, bot, exact, style, vectors)
                if vectors:
                    vectors_by_arm["D_working_ids"] = bot.river.combos[1 - bot.live_node.player].tolist()
        else:
            record["solves"] = bot.solves
        if key in ("B", "D"):
            arms["C" if key == "B" else "E"] = phase_4s.decision_factor(bot, ds, record)

    successful = [arms[key]["exact_action_ev"] for key in ("A", "B", "D") if "failure" not in arms[key]]
    values = successful[0] if successful else {}
    assert all(value == values and list(value) == list(values) for value in successful)
    for record in arms.values():
        if "failure" in record:
            action = label(Action(*record["fallback_action"]))
            if action in values:
                record.update(mix={action: 1.}, ev=values[action],
                              regret=max(values.values()) - values[action], chosen=action)
    return {"case": asdict(case), "stream": stream, "prefix": prefix, "opponent": name,
            "closing": ds.opponent_stack == 0 and "fold" in ds.legal_actions, "exact_action_ev": values,
            "arms": arms, "inference": inference, "future_replies": replies, "posterior_vectors": vectors_by_arm}


def summarize(rows):
    paired = [r for r in rows if all("ev" in r["arms"][key] for key in ARMS)]
    boards = sorted({row["case"]["index"] for row in rows})
    streams = sorted({row["stream"] for row in rows})
    rng = np.random.default_rng(44003)
    bi = rng.integers(len(boards), size=(10000, len(boards), 1))
    si = rng.integers(len(streams), size=(10000, 1, len(streams)))
    result = {"rows": len(rows), "matched": len(paired), "contrasts": {}, "arms": {},
              "oracle_mean_bb": mean(max(r["exact_action_ev"].values()) for r in paired) if paired else None}
    ev = np.array([[r["arms"][key]["ev"] for key in ARMS] for r in paired])
    for key, coeff in CONTRASTS.items():
        if not paired:
            break
        deltas = (ev @ coeff).tolist()
        interval = None
        if len(rows) == len(paired) and len(streams) > 1:
            cells = {(board, stream): [] for board in boards for stream in streams}
            for row, delta in zip(paired, deltas, strict=True):
                cells[row["case"]["index"], row["stream"]].append(delta)
            matrix = np.array([[mean(cells[board, stream]) for stream in streams] for board in boards])
            interval = np.quantile(matrix[bi, si].mean(axis=(1, 2)), [.025, .975]).tolist()
        result["contrasts"][key] = {
            "mean": mean(deltas), "interval": interval, "worst": min(deltas),
            "harm_total": -sum(d for d in deltas if d < 0),
            "by_style": {name: mean(d for r, d in zip(paired, deltas, strict=True) if r["opponent"] == name)
                         for name in sorted({r["opponent"] for r in paired})},
            "harms": [{"case": r["case"]["index"], "stream": r["stream"], "style": r["opponent"], "delta": d}
                      for r, d in sorted(zip(paired, deltas, strict=True), key=lambda pair: pair[1]) if d < -.01],
        }
    closing = [r for r in paired if r["closing"]]
    for key in ARMS:
        closed = [(r["arms"][key], next((ev for action, ev in r["exact_action_ev"].items() if action != "fold")))
                  for r in closing]
        cover = lambda record: 1 - record["mix"].get("fold", 0.)
        seconds = [r["arms"][key]["seconds"] for r in rows]
        result["arms"][key] = {
            "mean_ev": mean(r["arms"][key]["ev"] for r in paired) if paired else None,
            "mean_regret": mean(r["arms"][key]["regret"] for r in paired) if paired else None,
            "closing_rows": len(closed),
            "cover_rate": mean(cover(record) for record, _ in closed) if closed else None,
            "profitable_covers": sum(value > 0 for _, value in closed),
            "losing_covers": sum(value < 0 for _, value in closed),
            "profitable_foregone_mass": sum(1 - cover(record) for record, value in closed if value > 0),
            "losing_avoided_mass": sum(1 - cover(record) for record, value in closed if value < 0),
            "seeded_profitable_folds": sum(record["chosen"] == "fold" for record, value in closed if value > 0),
            "seeded_losing_folds": sum(record["chosen"] == "fold" for record, value in closed if value < 0),
            "fallbacks": [{"case": r["case"]["index"], "stream": r["stream"], "opponent": r["opponent"],
                           "reason": r["arms"][key]["failure"]} for r in rows if "failure" in r["arms"][key]],
            "replay_seconds": [float(np.median(seconds)), float(np.quantile(seconds, .95)), max(seconds)],
            "over_cap": [{"case": r["case"]["index"], "stream": r["stream"], "opponent": r["opponent"]}
                         for r in rows if r["arms"][key]["seconds"] > 15],
        }
    return result


def promotion_gates(result):
    summary = result["summary"]
    costs = summary["arms"]
    return {
        key: {
            "mean_and_interval": (contrast["mean"] >= .05 and contrast["interval"] is not None
                                  and contrast["interval"][0] > 0),
            "worst_loss": contrast["worst"] >= -.50,
            "harm_rate": len(contrast["harms"]) <= .10 * summary["rows"],
            "opponent_floor": min(contrast["by_style"].values()) >= -.03,
            "complete_no_fallbacks": (summary["matched"] == summary["rows"]
                                      and not any(arm["fallbacks"] for arm in costs.values())),
            "runtime": (not costs[key]["over_cap"]
                        and costs[key]["replay_seconds"][0] <= 2 * costs["A"]["replay_seconds"][0]),
            "memory": result["process_peak_resident_bytes"] <= 768 * 1024 ** 2,
        }
        for key in ARMS[1:] if (contrast := summary["contrasts"].get(f"{key}-A")) is not None
    }


def frozen_manifest():
    directories = ("coach", "simulation", "solver", "research")
    sources = [p for directory in directories for p in (REPO / "backend" / directory).rglob("*")
               if p.is_file() and p.suffix in (".py", ".npz")]
    sources.extend(REPO / p for p in ("PHASE_4T_PROTOCOL.md", "backend/poker_analyzer.py",
                                     "backend/test_research_holdem_phase_4t.py"))
    return {
        "sources": {p.relative_to(REPO).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(sources)},
        "cases": [dict(case=asdict(case), stream=s, prefix=p, opponent=n) for case, s, p, n in schedule("holdout")],
    }


def load_case(row, kind):
    case = row["case"]
    return kind(**{**case, "hero": tuple(case["hero"]), "board": tuple(case["board"]), "line": tuple(case["line"])})


def historical(archive, previous):
    rows = [evaluate(phase_4r.failed_case(), 131, 3, "tight_aggressive",
                     train("tight_aggressive", 131, (3,))[3])]
    specs = (("historical", ("Js", "3c"), "loose_aggressive", 91, phase_4o.Case),
             ("diagnostic-13", ("Kc", "As"), "tight_passive", 132, phase_4q.WagerCase))
    for filename, hero, style, stream, kind in specs:
        old = json.loads((archive / f"{filename}.json").read_text(encoding="utf-8-sig"))
        row = next(r for r in old["rows"] if tuple(r["case"]["hero"]) == hero
                   and r["opponent"] == style and r["stream"] == stream)
        case = load_case(row, kind)
        evidence = row["evidence"]
        truth = dict(zip(map(tuple, evidence["combos"]), evidence["true_posterior"], strict=True))
        exact = ExactRiverEV(case.hero, case.board, lambda pair, _: truth[pair])
        prefix = row["hands"]
        rows.append(evaluate(case, stream, prefix, style, train(style, stream, (prefix,))[prefix] if prefix else None,
                             exact=exact))
    old = json.loads((previous / "holdout-13.json").read_text(encoding="utf-8"))
    row = next(r for r in old["rows"] if r["case"]["hero"] == ["Jd", "4h"] and r["case"]["depth"] == 9
               and r["opponent"] == "loose_aggressive" and r["stream"] == 172)
    case, style, stream, prefix = load_case(row, phase_4q.WagerCase), row["opponent"], row["stream"], row["prefix"]
    rows.append(evaluate(case, stream, prefix, style, train(style, stream, (prefix,))[prefix], vectors=True))
    return {"rows": rows}


def profile_replay(key):
    case, stream, prefix, name = schedule("development")[-1]
    profile = train(name, stream, (prefix,))[prefix] if prefix else None
    make = DecoupledReplay if key == "D" else lambda: BaselineTrace(key == "B")
    _EQUITY_CACHE.clear()
    hand_tiers.cache_clear()
    samples = []
    for temperature in ("cold", "warm", "warm"):
        bot = make()
        start = perf_counter()
        bot.trace(case.spot(), profile)
        samples.append({"temperature": temperature, "seconds": perf_counter() - start,
                        "stage_seconds": getattr(bot, "stage_seconds", None), "solve_count": bot.solve_count})
    profiler = cProfile.Profile()
    profiler.runcall(make().trace, case.spot(), profile)
    names = {"_decide", "_solve", "_street_solve", "_apply_strategy", "_range_report", "_infer", "distribution",
             "conditioned", "conditional_range", "observe", "select", "hand_tiers", "_full_equity",
             "iterate", "_terminal_values", "replay_hand"}
    timings = [{"file": Path(filename).name, "function": function, "calls": calls,
                "self_seconds": own, "cumulative_seconds": total}
               for (filename, _, function), (_, calls, own, total, _) in pstats.Stats(profiler).stats.items()
               if function in names]
    return {"samples": samples, "profile": sorted(timings, key=lambda row: -row["cumulative_seconds"])}


def run_panel(panel):
    _, _, streams = PANELS[panel]
    profiles = {(s, n): train(n, s, phase_4r.PREFIXES[1:]) for s in streams for n in STYLES}
    rows = []
    previous_board = None
    for index, (case, stream, prefix, name) in enumerate(schedule(panel)):
        if case.board != previous_board:
            for length in (3, 4, 5):
                _full_equity(case.board[:length], ResearchReplay.flop_runouts)
            print(f"Board {case.index + 1} starting after {index} rows", flush=True)
            previous_board = case.board
        rows.append(evaluate(case, stream, prefix, name, profiles[stream, name].get(prefix), order=index % 3))
    return {"rows": rows, "summary": summarize(rows)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("panel", choices=(*PANELS, "freeze", "historical", "profile-A", "profile-B", "profile-D"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archive", type=Path, default=REPO / "benchmark-results/phase-4q-2026-11-18")
    parser.add_argument("--previous", type=Path, default=REPO / "benchmark-results/phase-4s-2026-11-18")
    args = parser.parse_args()
    started = perf_counter()
    if args.panel == "freeze":
        phase_4s.write_json(args.output, frozen_manifest())
        return
    if args.panel == "holdout":
        if args.manifest is None:
            parser.error("holdout requires --manifest")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if manifest != json.loads(json.dumps(frozen_manifest())):
            raise ValueError("frozen inputs or schedule changed")
    if args.panel == "historical":
        result = historical(args.archive, args.previous)
    elif args.panel.startswith("profile-"):
        result = profile_replay(args.panel[-1])
    else:
        result = run_panel(args.panel)
    result.update(wall_seconds=perf_counter() - started, process_peak_resident_bytes=peak_resident_bytes())
    if args.panel == "holdout":
        result["gates"] = promotion_gates(result)
    phase_4s.write_json(args.output, result)


if __name__ == "__main__":
    main()
