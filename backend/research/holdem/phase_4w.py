"""Offline Phase 4W architecture audit and independently scored holdout."""
from argparse import ArgumentParser
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import mean
from time import perf_counter
from unittest.mock import patch

import numpy as np

from coach import service as coach
from research.holdem import phase_4q, phase_4s, phase_4v
from research.holdem.decoupled_replay import CFRWorkingSet, DecoupledReplay
from research.holdem.live_persistent import ReplayBeliefs
from research.holdem.live_trace import assert_legal
from research.holdem.phase_4k import STYLES, label, peak_resident_bytes, to_action, train
from research.holdem.phase_4l import exact_values
from research.holdem.river_ev import RiverState
from simulation.actions import Action
from simulation.history_service import hand_history_from_dict, run_builtin_hand_history, run_builtin_match_history
from solver.bot import AdaptiveSolverBot, SolverBot, _EQUITY_CACHE, _full_equity
from solver.combos import card_mask


REPO = Path(__file__).resolve().parents[3]
COACH_FLAG = "POKER_COACH_PERSISTENT_RANGES"
MATCH_FLAG = "POKER_MATCH_PERSISTENT_RANGES"
PANELS = {"development": (447101, 4, (301,)), "holdout": (447102, 8, (311, 312, 313))}
PROJECTIONS = [(limit, seed) for limit in (32, 128, 384, 896) for seed in (None, 17, 29)]
ARCHIVE = REPO / "benchmark-results/phase-4v-2026-11-19/final13"


def distribution(weights):
    total = float(weights.sum())
    return {"positive": int(np.count_nonzero(weights)), "total": total,
            "effective": total ** 2 / float(weights @ weights) if total else 0.}


def concrete_mix(bot, ds, action, info, raw):
    if raw is None:
        assert info["source"] == "fallback"
        return {label(action): 1.}
    nominal = [to_action(key) for key in info["labels"]] if ds.street != "preflop" else []
    menu = (info["concrete_labels"] if ds.street == "preflop" else
            [label(bot._concrete_postflop(ds, (item.type, item.amount))) for item in nominal])
    assert np.isfinite(raw).all() and (raw >= 0).all() and abs(raw.sum() - 1.) < 1e-12
    mix = {}
    for key, probability in zip(menu, raw, strict=True):
        assert_legal(ds, to_action(key))
        mix[key] = mix.get(key, 0.) + float(probability)
    assert label(action) in mix
    return mix


def advise(spot, arm, snapshot=None, showdown=None, selection=None, *, audit=False):
    """Use the real Coach replay and advisor wrapper. Witness only local copies."""
    bot = DecoupledReplay(selection) if arm == "C" else (AdaptiveSolverBot if snapshot else SolverBot)(seed=917)
    bot.seed_base = 917
    bot.persistent_ranges = arm == "B"
    bot.range_selection = selection
    bot.explain_ev = True
    if showdown is not None:
        bot.showdown_model = showdown
    raw, ranges, projections, stages, groups = [], [], [], [], []
    updates = []
    original_sample, report = bot._sample, bot._range_report
    project = ReplayBeliefs.project
    observe, reveal = ReplayBeliefs.observe, ReplayBeliefs.reveal
    solve = SolverBot._solve

    def sample(ds, mix):
        raw.append(mix.copy())
        return original_sample(ds, mix)

    def range_report(board, hero, villain):
        ranges.append(villain.copy())
        return report(board, hero, villain)

    def traced_project(beliefs, hero, selector):
        working = project(beliefs, hero, selector)
        stages.append((beliefs.update_seconds, beliefs.likelihood_seconds))
        assert not any(np.shares_memory(weights, scratch) for weights in
                       (beliefs.opponent, *(reach.weights for reach in beliefs.public_reaches))
                       for scratch in working.reaches)
        projections.append(working)
        return working

    def traced_solve(advisor, state, board, reaches, hero_combo, hero, profile=None, **kwargs):
        result = solve(advisor, state, board, reaches, hero_combo, hero, profile, **kwargs)
        groups.append(result.combos)
        return result

    def check_update(beliefs, prior, factor, event):
        expected = prior * factor
        posterior = beliefs.opponent
        np.testing.assert_allclose(posterior, expected / expected.sum(), rtol=0, atol=1e-15)
        assert not np.any(posterior[prior == 0]) and not posterior.flags.writeable
        updates.append({"event": event, "board_cards": len(beliefs.board), "evidence": float(expected.sum()),
                        "belief": distribution(posterior)})

    def traced_observe(beliefs, player, likelihood):
        prior = beliefs.opponent
        observe(beliefs, player, likelihood)
        if player == beliefs.villain:
            check_update(beliefs, prior, likelihood, "observation")
        else:
            assert prior is beliefs.opponent

    def traced_reveal(beliefs, board):
        prior = beliefs.opponent
        reveal(beliefs, board)
        check_update(beliefs, prior, ~card_mask(board), "board")

    bot._sample = sample
    if audit:
        bot._range_report = range_report
    started = perf_counter()
    observers = {"project": traced_project}
    if audit:
        observers.update(observe=traced_observe, reveal=traced_reveal)
    with patch.multiple(ReplayBeliefs, **observers), patch.object(SolverBot, "_solve", traced_solve):
        status, payload, engine = coach._replay(spot, bot, snapshot)
    elapsed = perf_counter() - started
    assert status == "hero_to_act"
    ds = engine.decision_observation(coach.HERO).decision_state
    action, info = payload["advice"], payload["explanation"]
    chosen = Action(action["action"], action["amount"])
    assert_legal(ds, chosen)
    row = {"action": label(chosen), "mix": concrete_mix(bot, ds, chosen, info, next(iter(raw), None)),
           "source": info["source"], "reason": info.get("reason"), "seconds": elapsed,
           "columns": [[len(ids) for ids in solve_ids] for solve_ids in groups],
           "action_ev": info.get("action_ev"), "range": info.get("range_ownership")}
    posterior = getattr(bot, "estimate", None) if arm == "C" else next(iter(ranges), None)
    if posterior is not None:
        excluded = card_mask((*ds.board_cards, *ds.hole_cards))
        legal = np.where(excluded, 0., posterior)
        row["belief"] = distribution(legal)
        if arm != "A":
            assert not posterior[excluded].any() and abs(legal.sum() - 1.) < 1e-12
        posterior = legal / legal.sum() if legal.any() else legal
    if stages:
        assert len(stages) == len(groups) == 1
        assert all(np.array_equal(a, b) for a, b in zip(projections[0].ids, groups[0], strict=True))
        row["stage_seconds"] = dict(zip(("belief_update", "likelihood"), stages[0], strict=True))
    elif arm == "C":
        row["stage_seconds"] = bot.stage_seconds
    if updates:
        row["updates"] = updates
    return row, ds, posterior, groups[-1] if groups else None


def tv(left, right):
    return sum(abs(left.get(key, 0.) - right.get(key, 0.)) for key in sorted(left.keys() | right.keys())) / 2


def compare_prefix(prefix, name, store, reverse, matrix):
    profile_bot = AdaptiveSolverBot(seed=917)
    snapshot = coach.profile_for(store, name, profile_bot).snapshot() if store else None
    showdown = profile_bot.showdown_model if store else None
    if prefix.board:
        for end in range(3, len(prefix.board) + 1):
            _full_equity(tuple(prefix.board[:end]), SolverBot.flop_runouts)
    nominal = {}
    for arm in ("CBA" if reverse and prefix.board else "ABC" if prefix.board else "AB"):
        nominal[arm] = advise(prefix, arm, snapshot, showdown, audit=True)
    a, ds, a_posterior, _ = nominal["A"]
    b, _, b_posterior, b_ids = nominal["B"]
    assert a["source"] != "fallback" or name == "tight_aggressive"
    assert b["source"] != "fallback"
    result = {"street": ds.street, "actions": len(ds.hand_actions), "arms": {key: row[0] for key, row in nominal.items()},
              "policy_tv_ab": tv(a["mix"], b["mix"])}
    if a_posterior is not None:
        result["posterior_tv_ab"] = float(np.abs(a_posterior - b_posterior).sum() / 2)
    if prefix.board:
        c, _, c_posterior, c_ids = nominal["C"]
        assert c["source"] != "fallback"
        np.testing.assert_allclose(b_posterior, c_posterior, atol=1e-15, rtol=0)
        assert all(np.array_equal(left, right) for left, right in zip(b_ids, c_ids, strict=True))
        assert tv(b["mix"], c["mix"]) < 1e-12 and b["action"] == c["action"]
        result["posterior_max_abs_bc"] = float(np.abs(b_posterior - c_posterior).max())
        result["policy_tv_bc"] = tv(b["mix"], c["mix"])
    if matrix and prefix.board:
        result["matrix"] = []
        for limit, seed in PROJECTIONS:
            if (limit, seed) == (896, None):
                varied, opponent, ids = b, b_posterior, b_ids
            else:
                varied, _, opponent, ids = advise(prefix, "B", snapshot, showdown, CFRWorkingSet(limit, seed), audit=True)
                adapter, _, c_opponent, c_ids = advise(prefix, "C", snapshot, showdown,
                                                       CFRWorkingSet(limit, seed), audit=True)
                np.testing.assert_array_equal(c_opponent, c_posterior)
                assert all(np.array_equal(left, right) for left, right in zip(ids, c_ids, strict=True))
                assert tv(varied["mix"], adapter["mix"]) < 1e-12 and varied["action"] == adapter["action"]
            np.testing.assert_array_equal(opponent, b_posterior)
            assert varied["updates"] == b["updates"]
            assert all(0 < len(group) <= limit for group in ids)
            result["matrix"].append({"limit": limit, "seed": seed, "decision": varied,
                                     "policy_tv_from_nominal": tv(b["mix"], varied["mix"])})
    return result


def architecture_coach(name, reverse):
    spot = phase_4v.coach_spot(name)
    prefixes = phase_4v.coach_prefixes(spot)
    opponent = "tight_aggressive" if name == "collapse-profiled" else None if name == "collapse" else name
    store = (phase_4v.FixtureStore(opponent, 131, 3) if name == "collapse-profiled" else
             phase_4v.FixtureStore(opponent) if opponent else None)
    workflows = {}
    with patch.dict(os.environ, {COACH_FLAG: "0"}):
        for prefix in prefixes:
            coach.advise(prefix, opponent, store=store, seed=917)
    for arm in ("BA" if reverse else "AB"):
        with patch.dict(os.environ, {COACH_FLAG: str(int(arm == "B"))}):
            started = perf_counter()
            workflows[arm] = {"responses": [coach.advise(prefix, opponent, store=store, seed=917) for prefix in prefixes],
                              "seconds": perf_counter() - started}
    trace = json.loads((ARCHIVE / f"{name}.json").read_text())["arms"]["control"]["responses"]
    for prior, current in zip(trace, workflows["A"]["responses"], strict=True):
        assert phase_4v.stable(prior) == phase_4v.stable(current)
    assert workflows["A"]["responses"][-1] == workflows["B"]["responses"][-1]
    status, payload, _ = coach._replay(spot)
    assert status == "hand_complete"
    timeline = phase_4v.verify_history(payload["result"]["history"])
    rows = [compare_prefix(prefix, opponent, store, reverse, name.startswith("collapse")) for prefix in prefixes[:-1]]
    for index, row in enumerate(rows):
        for arm in ("A", "B"):
            response = workflows[arm]["responses"][index]
            assert label(Action(response["advice"]["action"], response["advice"]["amount"])) == row["arms"][arm]["action"]
            assert response["explanation"]["source"] == row["arms"][arm]["source"]
    assert sum(row["arms"]["A"]["source"] == "fallback" for row in rows) == int(name == "collapse-profiled")
    if name == "collapse-profiled":
        assert rows[-1]["arms"]["B"]["belief"]["positive"] == 990
        for arm in ("BA" if reverse else "AB"):
            _EQUITY_CACHE.clear()
            with patch.dict(os.environ, {COACH_FLAG: str(int(arm == "B"))}):
                started = perf_counter()
                cold = coach.advise(prefixes[-2], opponent, store=store, seed=917)
                workflows[arm]["cold"] = {"seconds": perf_counter() - started, "advice": cold["advice"]}
                assert cold["advice"] == workflows[arm]["responses"][-2]["advice"]
    return {"workflows": workflows, "rows": rows, "timeline": timeline}


def architecture_match(name, recipe, reverse):
    bot_a, bot_b, seed, hands, stack = recipe
    config = dict(bot_a=bot_a, bot_b=bot_b, seed=seed, max_hands=hands, starting_stack=stack,
                  equity_iterations=500)
    result = {}
    for arm in ("BA" if reverse else "AB"):
        with patch.dict(os.environ, {MATCH_FLAG: str(int(arm == "B"))}):
            document = run_builtin_match_history(**config)
            traced, _ = phase_4v.run_match(config, False)
            assert traced["responses"] == document and document["aggregate_validation"]["valid"]
            assert not document["aggregate_fallback_count"]
            assert all(row["source"] != "fallback" for row in traced["decisions"])
            timelines = [phase_4v.verify_history(hand_history_from_dict(item)) for item in document["histories"]]
            result[arm] = {"match": document["match"], "timelines": timelines,
                           "decisions": traced["decisions"], "seconds": traced["elapsed"]}
    if name in phase_4v.MATCHES:
        archive = json.loads((ARCHIVE / f"{name}.json").read_text())
        assert result["A"]["match"] == archive["arms"]["control"]["responses"]
        assert result["A"]["timelines"] == archive["timelines"]
    if bot_a not in phase_4v.SOLVERS and bot_b not in phase_4v.SOLVERS:
        assert phase_4v.stable(result["A"]) == phase_4v.stable(result["B"])
    return result


def architecture(reverse):
    coach_cases = (*phase_4v.COACH_LINES, "collapse", "collapse-profiled")
    matches = {**phase_4v.MATCHES,
               "gated-tight": ("solver_adaptive_gated", "tight", 42, 2, 1500),
               "sized-tight": ("solver_adaptive_sized", "tight", 42, 2, 1500)}
    with patch.dict(os.environ, {MATCH_FLAG: "1"}):
        replay = run_builtin_hand_history(bot_a="solver", bot_b="tight", seed=42, equity_iterations=500)
        phase_4v.verify_history(hand_history_from_dict(replay["history"]))
    return {"coach": {name: architecture_coach(name, reverse) for name in coach_cases},
            "match": {name: architecture_match(name, recipe, reverse) for name, recipe in matches.items()},
            "peak_mib": peak_resident_bytes() / 1024 ** 2}


def schedule(panel):
    seed, count, streams = PANELS[panel]
    deals = [list(phase_4q.cases(seed, count, index)) for index in range(len(streams))]
    return [(deals[index][board], stream, (0, 3, 30, 100)[(board + index) % 4], name)
            for board in range(count) for index, stream in enumerate(streams) for name in STYLES]


def frozen_manifest():
    backend = REPO / "backend"
    sources = [*backend.glob("*.py"), *(backend / "solver" / "data").glob("*")]
    for folder in ("coach", "research", "simulation", "solver", "test_data"):
        sources.extend((backend / folder).rglob("*.py"))
        sources.extend((backend / folder).rglob("*.json"))
    sources.append(REPO / "PHASE_4W_PROTOCOL.md")
    return {"sources": {path.relative_to(REPO).as_posix(): sha256(path.read_bytes()).hexdigest()
                        for path in sorted(set(sources)) if path.is_file()},
            "schedule": [[asdict(case), stream, prefix, name] for case, stream, prefix, name in schedule("holdout")]}


def verify_exact_payoffs(reference, state, values, call_probability):
    """Cross-check the exact scorer with independent net-transfer accounting."""
    for key, value in values.items():
        if key == "fold":
            assert value == 0.
            continue
        action = to_action(key)
        price = state.villain_commit - state.hero_commit
        extra = (price if action.type == "call" else state.hero_stack if action.type == "all_in"
                 else action.amount - state.hero_commit)
        villain_paid = min(state.villain_stack, max(0, extra - price))
        hero_paid = min(extra, price + villain_paid)
        contest = state.pot - max(0, price - hero_paid) + hero_paid + villain_paid
        shares = {-1: 0, 0: (contest + state.hero_gets_odd_chip) // 2, 1: contest}
        score = 0.
        for holding in reference.holdings:
            accepted = (call_probability(holding.combo, holding.rank, villain_paid, contest - villain_paid)
                        if villain_paid else 1.)
            score += holding.weight * ((1. - accepted) * state.pot + accepted * (shares[holding.result] - hero_paid))
        assert abs(score / 100 - value) < 1e-10


def holdout_row(case, stream, prefix, name, profile, reverse):
    spot = case.spot()
    for end in (3, 4, 5):
        _full_equity(tuple(spot.board[:end]), SolverBot.flop_runouts)
    snapshot, showdown = (profile.snapshot, profile.showdown) if profile else (None, None)
    arms = {arm: advise(spot, arm, snapshot, showdown) for arm in ("BA" if reverse else "AB")}
    a, ds, _, _ = arms["A"]
    b, other_ds, _, _ = arms["B"]
    assert ds == other_ds
    style = STYLES[name]
    reference = phase_4s.exact_reference(case, ds, style)
    state = RiverState(ds.pot, ds.hero_street_commitment, ds.opponent_street_commitment, ds.hero_stack,
                       ds.opponent_stack, ds.last_full_raise_size, raising_reopened=ds.raising_reopened,
                       hero_gets_odd_chip=ds.acting_player == "b")
    values = exact_values(reference, state, sorted(a["mix"].keys() | b["mix"].keys()), style.call_probability)
    verify_exact_payoffs(reference, state, values, style.call_probability)
    for policy in (a, b):
        policy["ev"] = sum(values[key] * probability for key, probability in policy["mix"].items())
        policy["regret"] = max(values.values()) - policy["ev"]
    return {"board_index": case.index, "stream": stream, "prefix": prefix, "opponent": name,
            "closing": ds.opponent_stack == 0, "values": values, "arms": {"A": a, "B": b},
            "delta": b["ev"] - a["ev"]}


def summarize(rows):
    boards, streams = sorted({row["board_index"] for row in rows}), sorted({row["stream"] for row in rows})
    cells = {(board, stream): [] for board in boards for stream in streams}
    for row in rows:
        cells[row["board_index"], row["stream"]].append(row["delta"])
    matrix = np.array([[mean(cells[board, stream]) for stream in streams] for board in boards])
    rng = np.random.default_rng(44003)
    bi = rng.integers(len(boards), size=(10000, len(boards), 1))
    si = rng.integers(len(streams), size=(10000, 1, len(streams)))
    closing = [row for row in rows if row["closing"]]
    profitable = [row for row in closing if max(row["values"].values()) > 0.]
    losing = [row for row in closing if min(row["values"].values()) < 0.]
    by_style = {name: mean(row["delta"] for row in rows if row["opponent"] == name) for name in STYLES}
    harms = [row for row in rows if row["delta"] < -.01]
    worst = min(rows, key=lambda row: row["delta"])
    profitable_regressions = [row for row in profitable if
                             (row["arms"]["B"]["mix"].get("fold", 0.) - row["arms"]["A"]["mix"].get("fold", 0.) > 1e-12
                              or row["arms"]["B"]["action"] == "fold" != row["arms"]["A"]["action"])]
    arms = {}
    for arm in ("A", "B"):
        samples = [row["arms"][arm] for row in rows]
        regrets = [row["regret"] for row in samples]
        arms[arm] = {"ev": mean(row["ev"] for row in samples),
                     "runtime": phase_4v.runtime([row["seconds"] for row in samples]),
                     "regret": [mean(regrets), float(np.median(regrets)), max(regrets)],
                     "fallbacks": sum(row["source"] == "fallback" for row in samples),
                     "profitable_folds": sum(row["arms"][arm]["action"] == "fold" for row in profitable),
                     "losing_folds": sum(row["arms"][arm]["action"] == "fold" for row in losing),
                     "profitable_fold_mass": sum(row["arms"][arm]["mix"].get("fold", 0.) for row in profitable),
                     "losing_fold_mass": sum(row["arms"][arm]["mix"].get("fold", 0.) for row in losing)}
    paired = mean(row["delta"] for row in rows)
    interval = np.quantile(matrix[bi, si].mean(axis=(1, 2)), [.025, .975]).tolist()
    changed = sum(tv(row["arms"]["A"]["mix"], row["arms"]["B"]["mix"]) > 1e-12 for row in rows)
    peak = peak_resident_bytes() / 1024 ** 2
    gates = {"mean_and_interval": paired >= .05 and interval[0] > 0,
             "max_harm": worst["delta"] >= -.50, "harm_rate": len(harms) <= .10 * len(rows),
             "style_floor": min(by_style.values()) >= -.03, "fallbacks": not any(a["fallbacks"] for a in arms.values()),
             "closing_safety_and_coverage": not profitable_regressions and bool(changed),
             "runtime": arms["B"]["runtime"]["max"] <= 15 and
                        arms["B"]["runtime"]["median"] <= 2 * arms["A"]["runtime"]["median"],
             "memory": peak <= 768}
    return {"paired_mean": paired, "interval": interval, "by_style": by_style, "arms": arms, "gates": gates,
            "harms": len(harms), "worst": worst, "changed": changed, "closing": len(closing),
            "profitable_closes": len(profitable), "profitable_regressions": len(profitable_regressions),
            "changed_closing_actions": sum(row["arms"]["A"]["action"] != row["arms"]["B"]["action"] for row in closing),
            "peak_mib": peak}


def run_panel(panel, reverse):
    profiles = {(stream, name): train(name, stream, (3, 30, 100))
                for stream in PANELS[panel][2] for name in STYLES}
    rows = [holdout_row(case, stream, prefix, name, profiles[stream, name].get(prefix), (i % 2 == 0) == reverse)
            for i, (case, stream, prefix, name) in enumerate(schedule(panel))]
    return {"rows": rows, "summary": summarize(rows)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("architecture", "development", "freeze", "holdout"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        result = frozen_manifest()
    elif args.mode == "architecture":
        result = architecture(args.reverse)
    else:
        if args.mode == "holdout":
            if args.manifest is None:
                parser.error("--manifest is required for holdout")
            assert json.loads(args.manifest.read_text()) == json.loads(json.dumps(frozen_manifest())), "freeze mismatch"
        result = run_panel(args.mode, args.reverse)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, allow_nan=False)
        file.write("\n")


if __name__ == "__main__":
    main()
