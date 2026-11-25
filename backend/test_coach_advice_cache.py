from copy import deepcopy

from fastapi.testclient import TestClient

from coach.advisor import _SOLVES
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
