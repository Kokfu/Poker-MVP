"""Bet-size-conditioned reads (proposal B, off by default): equivalence, statistics, lookup, persistence, instrumentation."""
import json
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from coach.service import Spot, SpotAction, _replay, log_hand, profile_for, spot_to_dict
from coach.store import HandStore
from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine
from simulation.opponent_model import SIZE_BUCKETS, OpponentModel, SizedStats, size_bucket
from solver.bot import AdaptiveSolverBot, GatedAdaptiveSolverBot, SizedAdaptiveSolverBot, SolverBot
from solver.exploit import (SIZED_MIN_N, SIZED_PRIOR, _normalized, facing_size_ratio, node_aggregates, sized_facing_nodes,
                            sized_locks, sized_needs_aggregates, sized_node_lock, tree_locks)
from solver.cfr import RangeSolver
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree
from test_solver_gated import _session


# ------------------------------------------------------------ equivalence / flags
def test_sized_is_off_everywhere_except_its_own_bot():
    assert SolverBot.sized_reads is False and AdaptiveSolverBot.sized_reads is False and GatedAdaptiveSolverBot.sized_reads is False
    assert AdaptiveSolverBot(seed=1).sized_reads is False
    assert AdaptiveSolverBot(seed=1, sized_reads=True).sized_reads is True
    bot = BOT_TYPES["solver_adaptive_sized"](seed=1)
    assert isinstance(bot, SizedAdaptiveSolverBot) and bot.sized_reads is True and bot.exploit and not bot.gated_locks


@pytest.mark.slow
def test_default_path_matches_phase_4h_reference(adaptive_learning_reference):
    expected, actual = adaptive_learning_reference
    assert actual == expected


# ------------------------------------------------------------ buckets and statistics
def test_bucket_edges():
    assert SIZE_BUCKETS == ("<=0.5", "0.5-1.0", ">1.0")
    assert [size_bucket(r) for r in (0.0, 0.33, 0.5, 0.5001, 0.99, 1.0, 1.0001, 3.0)] == [
        "<=0.5", "<=0.5", "<=0.5", "0.5-1.0", "0.5-1.0", "0.5-1.0", ">1.0", ">1.0"]


def _scripted(a_actions, b_actions, seed=1):
    a, b = ScriptedBot(a_actions), ScriptedBot(b_actions)
    return HandEngine(a, b, seed=seed, button="a").play()["history"]


def test_model_buckets_responses_to_our_bets_with_the_pre_registered_ratio():
    model = OpponentModel("b")
    check, call = Action("check"), Action("call")
    # hand 1: pot 200, we bet 100 (0.5 -> "<=0.5"), opponent folds
    model.update(_scripted([call, Action("bet", 100)], [check, check, Action("fold")]))
    # hand 2: we bet 200 (1.0 -> "0.5-1.0"), opponent raises to 600, we fold
    model.update(_scripted([call, Action("bet", 200), Action("fold")], [check, check, Action("raise", 600)]))
    # hand 3: flop bet 300 (1.5 -> ">1.0") called; turn: opponent bets 200, we raise to 600 over it:
    #         (600 - 200) / (800 + 2 * 200) = 0.33 -> "<=0.5", opponent folds
    model.update(_scripted([call, Action("bet", 300), Action("raise", 600)], [check, check, call, Action("bet", 200), Action("fold")]))
    cells = {bucket: (v.opportunities, v.folds, v.calls, v.raises) for bucket, v in model.snapshot().sized_statistics.items()}
    assert cells == {"<=0.5": (2, 2, 0, 0), "0.5-1.0": (1, 0, 0, 1), ">1.0": (1, 0, 1, 0)}


def test_sized_statistics_are_not_serialized_and_do_not_change_equality():
    model = OpponentModel("b")
    model.update(_scripted([Action("call"), Action("bet", 100)], [Action("check"), Action("check"), Action("fold")]))
    snapshot = model.snapshot()
    assert snapshot.sized_statistics and "sized_statistics" not in snapshot.as_dict()
    json.dumps(snapshot.as_dict(), allow_nan=False)
    assert snapshot == OpponentModel("b").snapshot().__class__(*[getattr(snapshot, f) for f in
        ("hands_observed", "decisions_observed", "statistics", "street_statistics", "sizing", "classification")])


# ------------------------------------------------------------ lookup and shrinkage
def _tree():
    return StreetTree(StreetState("flop", 1, (0, 0), (9_000, 9_000), (500, 500), 100), POSTFLOP_MENU)


def _aggregates(tree, opponent=0, n=6):
    rng = np.random.default_rng(0)
    solver = RangeSolver(tree, (np.ones(n), np.ones(n)), rng.uniform(-1, 1, (n, n)), np.ones((n, n)))
    return node_aggregates(tree, opponent, np.ones(n), solver.solve(20).average)


def test_facing_ratio_matches_the_history_definition_and_only_facing_nodes_qualify():
    tree = _tree()
    facing = sized_facing_nodes(tree, 0)
    assert facing and all(0 < facing_size_ratio(n) for n in facing)
    # pot 1000 (500 each carried): a half-pot bet of 500 is 0.5, a pot-size bet is 1.0
    ratios = sorted({round(facing_size_ratio(n), 2) for n in facing})
    assert 0.5 in ratios and 1.0 in ratios
    others = [n for n in tree.nodes if n.kind == "decision" and n.player == 0 and n not in facing]
    assert all(facing_size_ratio(n) is None for n in others)


def test_posterior_is_shrunk_toward_the_unlocked_aggregate_with_m_20():
    tree = _tree()
    aggregates = _aggregates(tree)
    node = next(n for n in sized_facing_nodes(tree, 0) if n.actions[0][0] == "fold" and len(n.actions) == 4)
    bucket = size_bucket(facing_size_ratio(node))
    cells = {bucket: SizedStats(30, 24, 4, 2)}
    lock = sized_node_lock(node, cells, aggregates[node.index])
    fold, passive, aggressive = (0,), tuple(i for i, (k, _) in enumerate(node.actions) if k in ("check", "call")), tuple(
        i for i, (k, _) in enumerate(node.actions) if k in ("bet", "raise", "all_in"))
    agg = aggregates[node.index]
    expected = _normalized([(g, (k + SIZED_PRIOR * float(sum(agg[i] for i in g))) / (30 + SIZED_PRIOR))
                            for g, k in ((fold, 24), (passive, 4), (aggressive, 2))])
    assert SIZED_PRIOR == 20.0 and lock[1] == expected
    assert lock[0] == 0.55  # 30 observations -> "medium" confidence weight, as in base
    assert sum(mass for _, mass in lock[1]) == pytest.approx(1.0)
    # the prior pulls a 24/30 fold read below 0.8 unless the solver already folds a lot
    fold_mass = dict(lock[1])[fold]
    assert fold_mass < 24 / 30 + 0.05


def test_thin_bucket_leaves_the_node_unlocked_and_never_falls_back():
    tree = _tree()
    aggregates = _aggregates(tree)
    node = sized_facing_nodes(tree, 0)[0]
    bucket = size_bucket(facing_size_ratio(node))
    info = {}
    assert sized_node_lock(node, {bucket: SizedStats(SIZED_MIN_N - 1, 9, 0, 0)}, aggregates[node.index], info=info) is None
    assert info["thin"] == 1
    other = [b for b in SIZE_BUCKETS if b != bucket]
    assert sized_node_lock(node, {b: SizedStats(500, 400, 50, 50) for b in other}, aggregates[node.index]) is None  # other cells never used
    assert sized_node_lock(node, {bucket: SizedStats(SIZED_MIN_N, 5, 3, 2)}, aggregates[node.index]) is not None
    assert SIZED_MIN_N == 10


def test_sized_locks_replace_only_facing_nodes_and_keep_base_locks_elsewhere():
    tree = _tree()
    stats = {name: SimpleNamespace(opportunities=60, occurrences=30, smoothed_frequency=0.5, confidence="high", raw_frequency=0.5)
             for name in ("fold_to_bet", "call_vs_bet", "raise_vs_bet", "bet")}
    profile = SimpleNamespace(statistics={}, street_statistics={"flop": stats}, hands_observed=60, classification="x")
    base = tree_locks(tree, 0, "flop", profile)
    facing = {n.index for n in sized_facing_nodes(tree, 0)}
    assert base and facing and set(base) - facing  # base has locks on both kinds of node
    cells = {b: SizedStats(40, 30, 6, 4) for b in SIZE_BUCKETS}
    assert sized_needs_aggregates(tree, 0, cells) and not sized_needs_aggregates(tree, 0, {})
    locks, info = sized_locks(tree, 0, base, cells, _aggregates(tree), {"aggressive": 0.9, "call": 0.5})
    assert {i: lock for i, lock in locks.items() if i not in facing} == {i: lock for i, lock in base.items() if i not in facing}
    assert info["locked"] == len(facing) and info["thin"] == 0 and info["facing_nodes"] == len(facing)
    assert all(locks[i][2] == 0.7 for i in facing)  # base strength formula for facing nodes
    # no unlocked aggregates available (all buckets thin) -> facing nodes unlocked, others untouched
    bare, info = sized_locks(tree, 0, base, {}, None)
    assert set(bare) == set(base) - facing and info["locked"] == 0 and info["thin"] == len(facing)


# ------------------------------------------------------------ end to end and instrumentation
@pytest.mark.slow
def test_instrumentation_has_sized_info_only_for_the_sized_bot():
    base, sized = _session(AdaptiveSolverBot, 30), _session(SizedAdaptiveSolverBot, 30)
    for entry in (t for t in base.decision_trace if t["source"] != "fallback"):
        assert "sized" not in entry["instrumentation"]
    post = [t for t in sized.decision_trace if t["source"] == "postflop_solve"]
    assert post and all("sized" in t["instrumentation"] for t in sized.decision_trace if t["source"] != "fallback")
    assert any(t["instrumentation"]["sized"] for t in post)
    for t in post:
        info = t["instrumentation"]["sized"]
        if info:
            assert info["locked"] + info["thin"] <= info["facing_nodes"] and set(info["buckets"]) <= set(SIZE_BUCKETS)


def test_sized_bot_applies_bucket_locks_in_a_coach_spot(tmp_path):
    from test_coach_learning import simulated_spots
    store = HandStore(tmp_path / "c.sqlite")
    for spot in simulated_spots("aggressive", 80):
        store.add("V", spot_to_dict(spot))
    snapshot = profile_for(store, "V").snapshot()
    assert sum(v.opportunities for v in snapshot.sized_statistics.values()) > 30
    advisor = SizedAdaptiveSolverBot(seed=0)
    spot = Spot(hero_cards=["Jc", "9d"], board=["Qh", "7s", "2d"], hero_position="button",
                actions=[SpotAction("hero", "raise", 250), SpotAction("villain", "call"), SpotAction("villain", "check")])
    status, payload, _ = _replay(spot, advisor, snapshot)  # hero to act on the flop: villain's facing-a-bet nodes are in the tree
    assert status == "hero_to_act"
    info = payload["explanation"]["instrumentation"]["sized"]
    assert info["facing_nodes"] > 0 and info["locked"] > 0 and info["thin"] >= 0


# ------------------------------------------------------------ Coach persistence
def test_sized_table_is_created_in_an_existing_database_and_old_rows_survive(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as connection:  # a database from before proposal B
        connection.execute("CREATE TABLE hands (id INTEGER PRIMARY KEY AUTOINCREMENT, opponent TEXT NOT NULL, created_at TEXT NOT NULL, spot TEXT NOT NULL)")
        connection.execute("INSERT INTO hands (opponent, created_at, spot) VALUES ('Old', 'x', '{\"hero_cards\": [\"As\", \"Kd\"]}')")
    store = HandStore(path)
    assert store.hands("Old") == [{"hero_cards": ["As", "Kd"]}] and store.sized_reads("Old") == {}
    HandStore(path)  # reopening is idempotent
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(sized_reads)")]
        assert columns == ["opponent", "street_class", "bucket", "opportunities", "folds", "calls", "raises"]


def test_sized_reads_round_trip_replace_and_cleanup(tmp_path):
    store = HandStore(tmp_path / "c.sqlite")
    store.save_sized_reads("Villain  One", {"<=0.5": (12, 5, 6, 1), ">1.0": (11, 10, 1, 0)})
    assert store.sized_reads("Villain One") == {"<=0.5": (12, 5, 6, 1), ">1.0": (11, 10, 1, 0)}
    store.save_sized_reads("Villain One", {"0.5-1.0": (10, 7, 2, 1)})  # replaces, does not accumulate
    assert store.sized_reads("Villain One") == {"0.5-1.0": (10, 7, 2, 1)}
    assert store.sized_reads("Villain One", "preflop") == {} and store.sized_reads("Other") == {}
    hand = {"hero_cards": ["As", "Kd"]}
    hand_id = store.add("Villain One", hand)
    assert store.delete_hand(hand_id) and store.sized_reads("Villain One") == {}  # stale cache dropped
    store.save_sized_reads("Villain One", {"<=0.5": (1, 1, 0, 0)})
    store.delete_opponent("Villain One")
    assert store.sized_reads("Villain One") == {}


def test_logging_a_hand_refreshes_the_sized_cache_from_the_stored_hands(tmp_path):
    store = HandStore(tmp_path / "c.sqlite")
    spot = Spot(hero_cards=["As", "Kd"], hero_position="button", actions=[
        SpotAction("hero", "call"), SpotAction("villain", "check"), SpotAction("villain", "check"), SpotAction("hero", "bet", 100),
        SpotAction("villain", "fold")], board=["2c", "7d", "9h"])
    for _ in range(2):
        log_hand(spot, "Reg", store)
    assert store.sized_reads("Reg") == {"<=0.5": (2, 2, 0, 0)}
    assert store.sized_reads("Reg") == {b: (v.opportunities, v.folds, v.calls, v.raises) for b, v in profile_for(store, "Reg").sized_stats.items()}
