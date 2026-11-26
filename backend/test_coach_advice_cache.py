from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
import pytest

from coach.advisor import _SOLVES, CoachAdvisor
from coach.service import _PROFILES, advise, log_hand, spot_to_dict
from coach.store import HandStore
from main import app
from solver.bot import _PREFLOP_CACHE, SolverBot
from solver.preflop import load_charts, load_class_equity
from test_coach import spot


def comparable(response):
    result = deepcopy(response)
    result["explanation"].pop("solve_seconds", None)
    return result


def test_cached_advice_matches_uncached_across_requests_and_profile_mutations(monkeypatch, tmp_path):
    store = HandStore(tmp_path / "isolated.sqlite")
    opponent = "Synthetic"
    flop = spot(("villain", "raise", 250), ("hero", "call"), board=("7h", "8d", "2c"), position="big_blind")
    turn = spot(("villain", "raise", 250), ("hero", "call"), ("hero", "check"), ("villain", "check"),
                board=("7h", "8d", "2c", "Jd"), position="big_blind")
    log_hand(spot(("hero", "raise", 250), ("villain", "fold")), opponent, store)

    calls = []
    orig_solve = SolverBot._solve

    def solve(self, state, *args, **kwargs):
        calls.append(state.street)
        return orig_solve(self, state, *args, **kwargs)

    monkeypatch.setattr(SolverBot, "_solve", solve)
    _SOLVES.clear()
    _PROFILES.clear()
    monkeypatch.setenv("POKER_COACH_SOLVE_CACHE", "0")
    baseline = [advise(item, opponent=opponent, store=store) for item in (flop, turn)]
    assert calls == ["flop", "flop", "turn"]

    monkeypatch.setenv("POKER_COACH_SOLVE_CACHE", "1")
    calls.clear()
    for item, expected in zip((flop, turn), baseline, strict=True):
        assert comparable(advise(item, opponent=opponent, store=store)) == comparable(expected)
        assert comparable(advise(item, opponent=opponent, store=store)) == comparable(expected)
    assert calls == ["flop", "turn"]
    assert len(_PROFILES) == 1

    log_hand(spot(("hero", "fold")), opponent, store)
    assert advise(flop, opponent=opponent, store=store)["opponent_profile"]["hands_observed"] == 2
    assert len(_PROFILES) == 2
    assert store.delete_opponent(opponent) == 2
    after_delete = advise(turn, opponent=opponent, store=store)
    assert after_delete["opponent_profile"] is None and not after_delete["exploiting"]
    monkeypatch.setenv("POKER_COACH_SOLVE_CACHE", "0")
    assert comparable(advise(turn, opponent=opponent, store=store)) == comparable(after_delete)


def test_disk_advice_survives_memory_eviction_and_disposable_cache_damage(monkeypatch, tmp_path):
    store = HandStore(tmp_path / "reference.sqlite")
    cache = tmp_path / "reference.exact-solves.sqlite"
    flop = spot(("villain", "raise", 250), ("hero", "call"), board=("7h", "8d", "2c"), position="big_blind")
    calls = []
    solve = SolverBot._solve

    def counted(self, state, *args, **kwargs):
        calls.append(state.street)
        return solve(self, state, *args, **kwargs)

    monkeypatch.setattr(SolverBot, "_solve", counted)
    monkeypatch.setenv("POKER_COACH_SOLVE_CACHE", "1")
    monkeypatch.setenv("POKER_COACH_SOLVE_DISK_CACHE", "1")
    _SOLVES.clear()
    try:
        expected = comparable(advise(flop, store=store))
        assert calls == ["flop"]
        assert cache.is_file()
        _SOLVES.clear()
        assert comparable(advise(flop, store=store)) == expected
        assert calls == ["flop"]

        cache.write_bytes(b"unreadable SQLite cache")
        _SOLVES.clear()
        assert comparable(advise(flop, store=store)) == expected
        assert calls == ["flop", "flop"]
    finally:
        _SOLVES.clear()


def test_startup_warms_both_positions_for_an_existing_coach_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("COACH_DB_PATH", str(tmp_path / "warm.sqlite"))
    monkeypatch.setenv("POKER_COACH_WARMUP", "1")
    monkeypatch.setenv("POKER_COACH_SOLVE_CACHE", "1")
    monkeypatch.setattr("solver.bot.PREFLOP_LOCKED_ITERATIONS", 3)
    store = HandStore()
    folds = spot_to_dict(spot(("hero", "raise", 250), ("villain", "fold")))
    opens = spot_to_dict(spot(("villain", "raise", 250), ("hero", "fold"), position="big_blind"))
    for _ in range(24):
        store.add("Synthetic", folds)
        store.add("Synthetic", opens)

    load_charts.cache_clear()
    load_class_equity.cache_clear()
    _PREFLOP_CACHE.clear()
    try:
        with TestClient(app) as client:
            app.state.coach_warmup.join(timeout=30)
            assert not app.state.coach_warmup.is_alive()
            assert load_charts.cache_info().currsize == load_class_equity.cache_info().currsize == 1
            for position, actions in (
                ("button", []),
                ("big_blind", [{"actor": "villain", "action": "raise", "amount": 250}]),
            ):
                response = client.post("/api/coach/advise", json={
                    "hero_cards": ["5h", "5d"], "opponent": "Synthetic",
                    "hero_position": position, "actions": actions,
                })
                response.raise_for_status()
                result = response.json()
                assert result["explanation"]["source"] == "preflop_exploit"
                assert result["explanation"]["instrumentation"]["cache_hit"] is True
    finally:
        _PREFLOP_CACHE.clear()


def test_locked_preflop_cache_uses_the_actual_chart_tree(monkeypatch):
    first_tree, second_tree = object(), object()
    first = SolverBot(charts=SimpleNamespace(trees={100: first_tree}))
    second = SolverBot(charts=SimpleNamespace(trees={100: second_tree}))
    solved = []

    class StubSolver:
        def __init__(self, tree, *args, **kwargs):
            self.tree = tree

        def solve(self, iterations):
            solved.append(self.tree)
            choice = 0.2 if self.tree is first_tree else 0.8
            return SimpleNamespace(average={1: np.full((1, 169), choice)})

    monkeypatch.setattr("solver.bot.RangeSolver", StubSolver)
    locks = {1: (0.3, (((0,), .8), ((1,), .2)))}
    try:
        assert first._preflop_policy(100, 1, locks)(1)[0, 0] == 0.2
        assert second._preflop_policy(100, 1, locks)(1)[0, 0] == 0.8
        assert first._preflop_policy(100, 1, locks)(1)[0, 0] == 0.2
        assert solved == [first_tree, second_tree]
    finally:
        _PREFLOP_CACHE.clear()


def test_coach_warm_cache_cannot_round_distinct_opponent_locks_together(monkeypatch):
    advisor = CoachAdvisor(seed=0, exploit=True, cache_solves=True)
    simulator = SolverBot(charts=advisor.charts)
    solved = []

    class StubSolver:
        def __init__(self, *args, locks, **kwargs):
            self.weight = locks[1][0]

        def solve(self, iterations):
            solved.append(self.weight)
            return SimpleNamespace(average={1: np.full((1, 169), self.weight)})

    monkeypatch.setattr("solver.bot.RangeSolver", StubSolver)
    groups = (((0,), .8), ((1,), .2))
    try:
        assert simulator._preflop_policy(100, 1, {1: (.304, groups)})(1)[0, 0] == .304
        assert advisor._preflop_policy(100, 1, {1: (.3, groups)})(1)[0, 0] == .3
        assert advisor._preflop_policy(100, 1, {1: (.304, groups)})(1)[0, 0] == .304
        assert advisor._preflop_policy(100, 1, {1: (.3, groups)})(1)[0, 0] == .3
        assert solved == [.304, .3, .304]
    finally:
        _PREFLOP_CACHE.clear()


@pytest.mark.parametrize("fail_first", [False, True])
def test_coach_requests_share_pending_exact_preflop_policy(monkeypatch, fail_first):
    monkeypatch.setattr("solver.bot._PREFLOP_CACHE", OrderedDict())
    monkeypatch.setattr("solver.bot._PREFLOP_PENDING", {})
    solve_started, caller_waiting, release_solve = Event(), Event(), Event()
    solved = []

    class ObservedFuture(Future):
        def result(self, timeout=None):
            caller_waiting.set()
            return super().result(timeout=timeout)

    class StubSolver:
        def __init__(self, *args, locks, **kwargs):
            self.weight = locks[1][0]

        def solve(self, iterations):
            solved.append(self.weight)
            if self.weight == .3 and solved.count(.3) == 1:
                solve_started.set()
                assert release_solve.wait(10)
                if fail_first:
                    raise ValueError("induced solve failure")
            return SimpleNamespace(average={1: np.full((1, 169), self.weight)})

    monkeypatch.setattr("solver.bot.Future", ObservedFuture)
    monkeypatch.setattr("solver.bot.RangeSolver", StubSolver)
    groups = (((0,), .8), ((1,), .2))

    def solve(weight):
        advisor = CoachAdvisor(seed=0, exploit=True, cache_solves=True)
        return advisor._preflop_policy(100, 1, {1: (weight, groups)})(1)

    with ThreadPoolExecutor(max_workers=3) as workers:
        first = workers.submit(solve, .3)
        try:
            assert solve_started.wait(10)
            second = workers.submit(solve, .3)
            assert caller_waiting.wait(10)
            distinct = workers.submit(solve, .304)
            assert distinct.result(timeout=10)[0, 0] == .304
            assert solved == [.3, .304]
        finally:
            release_solve.set()
        if fail_first:
            for call in (first, second):
                with pytest.raises(ValueError, match="induced solve failure"):
                    call.result(timeout=10)
            assert solve(.3)[0, 0] == .3
            assert solved == [.3, .304, .3]
        else:
            np.testing.assert_array_equal(first.result(timeout=10), second.result(timeout=10))
            assert solved == [.3, .304]


def test_coach_store_closes_sqlite_connections_after_each_operation(monkeypatch, tmp_path):
    opened = []
    closed = []
    connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        def close(self):
            closed.append(self)
            super().close()

    def tracked_connect(path, **kwargs):
        connection = connect(path, factory=TrackedConnection, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr("coach.store.sqlite3.connect", tracked_connect)
    store = HandStore(tmp_path / "handles.sqlite")
    payload = spot_to_dict(spot(("hero", "fold")))
    store.add("practice", payload)
    assert store.hands("practice") == [payload]
    assert store.delete_all() == 1
    assert len(opened) == 5 and closed == opened
