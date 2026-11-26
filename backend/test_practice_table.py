from concurrent.futures import ThreadPoolExecutor
from sqlite3 import OperationalError
from threading import Event

from fastapi.testclient import TestClient
import pytest

import practice_table
from coach.store import HandStore
from main import app
from practice_table import _CREATES, _TABLES
from simulation.actions import Action


@pytest.fixture(autouse=True)
def close_test_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("COACH_DB_PATH", str(tmp_path / "practice.sqlite"))
    yield
    for table in _TABLES.values():
        with table.lock:
            if table.timer is not None:
                table.timer.cancel()
    _TABLES.clear()
    _CREATES.clear()


def without_clock(table):
    return {key: value for key, value in table.items() if key != "remaining_ms"}


def test_table_requires_its_key_and_rejects_invalid_or_stale_actions():
    client = TestClient(app)
    created = client.post("/api/practice/table")
    assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
    key, table = created.json()["key"], created.json()["table"]
    headers = {"Authorization": f"Bearer {key}"}
    assert client.get("/api/practice/table").status_code == 401
    assert client.get("/api/practice/table", headers={"Authorization": "Bearer wrong"}).status_code == 404
    assert without_clock(client.get("/api/practice/table", headers=headers).json()) == without_clock(table)
    assert table["turn_seconds"] == 20 and 0 < table["remaining_ms"] <= 20_000
    assert table["position"] == "BTN" and table["status"] == "your_turn"
    assert "shown_bot_cards" not in table and "seed" not in table and table["board"] == []
    assert table["your_stack"] + table["bot_stack"] + table["pot"] == 20_000

    revision = {"revision": table["revision"]}
    assert client.post("/api/practice/table/next", headers=headers, json=revision).status_code == 409
    invalid = {**revision, "action": "raise", "amount": table["minimum_target"] - 1}
    assert client.post("/api/practice/table/action", headers=headers, json=invalid).status_code == 422
    assert without_clock(client.get("/api/practice/table", headers=headers).json()) == without_clock(table)
    fold = {**revision, "action": "fold"}
    settled = client.post("/api/practice/table/action", headers=headers, json=fold).json()
    assert settled["status"] == "complete" and settled["net_chips"] == -50
    assert settled["learned_hands"] == 1 and "shown_bot_cards" not in settled
    assert settled["your_stack"] + settled["bot_stack"] == 20_000
    assert client.post("/api/practice/table/action", headers=headers, json=fold).status_code == 409
    new_hand = client.post("/api/practice/table/next", headers=headers, json={"revision": settled["revision"]})
    assert new_hand.status_code == 200
    assert new_hand.json()["hand"] == 2 and new_hand.json()["position"] == "BB"
    assert new_hand.json()["learned_hands"] >= 1


def test_all_in_reveals_bot_cards_at_showdown_only(monkeypatch):
    client = TestClient(app)
    created = client.post("/api/practice/table").json()
    headers = {"Authorization": f"Bearer {created['key']}"}
    seen = []
    bot = _TABLES[created["key"]].bot
    completed_memory = object()

    def call_all_in(observation):
        seen.append(observation)
        bot.memory = completed_memory
        return Action("all_in")

    monkeypatch.setattr(bot, "decide_decision", call_all_in)
    response = client.post("/api/practice/table/action", headers=headers,
                           json={"revision": created["table"]["revision"], "action": "all_in"})
    assert response.status_code == 200
    settled = response.json()
    assert settled["status"] == "complete" and settled["learned_hands"] == 1
    assert settled["your_stack"] + settled["bot_stack"] == 20_000
    assert len(set(settled["your_cards"] + settled["shown_bot_cards"] + settled["board"])) == 9
    assert len(seen) == 1
    assert tuple(settled["shown_bot_cards"]) == seen[0].decision_state.hole_cards
    assert bot.memory is None and bot.showdown_model.hands == 1
    assert settled["learned_hands"] == 1


def test_timer_folds_without_a_check_and_hides_review_until_settlement(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("practice_table.monotonic", lambda: now[0])
    seen = []

    def coach(spot, *args, **kwargs):
        seen.append(spot)
        return {"advice": {"action": "call", "amount": None}, "explain": None}

    monkeypatch.setattr("practice_table.advise", coach)
    client = TestClient(app)
    assert client.post("/api/practice/table", json={"turn_seconds": 0}).status_code == 422
    created = client.post("/api/practice/table", json={"turn_seconds": 5}).json()
    headers = {"Authorization": f"Bearer {created['key']}"}
    first = created["table"]
    assert first["remaining_ms"] == 5000
    assert client.get(f"/api/practice/table/review?revision={first['revision']}", headers=headers).status_code == 409
    assert not seen

    now[0] += 5
    _TABLES[created["key"]]._on_timeout(first["revision"])
    response = client.post("/api/practice/table/action", headers=headers,
                           json={"revision": first["revision"], "action": "call"})
    assert response.status_code == 409
    settled = client.get("/api/practice/table", headers=headers).json()
    assert settled["status"] == "complete" and settled["remaining_ms"] is None
    assert settled["last_action_timed_out"] is True
    assert settled["actions"][-1] == {"player": "a", "type": "fold"}
    path = f"/api/practice/table/review?revision={settled['revision']}"
    review = client.get(path, headers=headers).json()
    assert review == [{"street": "preflop", "action": {"action": "fold", "amount": None},
                       "timed_out": True, "advice": {"action": "call", "amount": None}, "explain": None,
                       "estimated_cost": None, "mistake": True}]
    assert client.get(path, headers=headers).json() == review
    assert len(seen) == 1 and seen[0].board == [] and seen[0].villain_cards is None


def test_timer_checks_when_legal_and_rearms_for_next_decision(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("practice_table.monotonic", lambda: now[0])
    client = TestClient(app)
    created = client.post("/api/practice/table", json={"turn_seconds": 5}).json()
    key = created["key"]
    headers = {"Authorization": f"Bearer {key}"}
    monkeypatch.setattr(_TABLES[key].bot, "decide_decision", lambda obs: Action("check"))
    flop = client.post("/api/practice/table/action", headers=headers,
                       json={"revision": created["table"]["revision"], "action": "call"}).json()
    assert flop["street"] == "flop" and "check" in flop["legal_actions"]
    now[0] += 5
    turn = client.get("/api/practice/table", headers=headers).json()
    assert turn["street"] == "turn" and turn["remaining_ms"] == 5000
    assert turn["revision"] > flop["revision"]
    assert turn["actions"][-2] == {"player": "a", "type": "check"}


def test_completed_hand_is_saved_once_and_session_review_uses_earlier_history(monkeypatch):
    client = TestClient(app)
    created = client.post("/api/practice/table", json={"opponent": "  Practice   opponent  "}).json()
    key = created["key"]
    headers = {"Authorization": f"Bearer {key}"}
    table = _TABLES[key]
    opponent = "Practice opponent"
    assert created["table"]["opponent"] == opponent
    assert HandStore().hands(opponent) == []

    save = table.store.add

    def committed_then_disconnected(*args, **kwargs):
        save(*args, **kwargs)
        raise OperationalError("injected failure after commit")

    monkeypatch.setattr(table.store, "add", committed_then_disconnected)
    fold = {"revision": created["table"]["revision"], "action": "fold"}
    assert client.post("/api/practice/table/action", headers=headers, json=fold).status_code == 503
    monkeypatch.setattr(table.store, "add", save)
    settled = client.post("/api/practice/table/action", headers=headers, json=fold).json()
    assert settled["status"] == "complete" and settled["learned_hands"] == 1
    saved, = HandStore().hands(opponent)
    assert saved["actions"] == [{"actor": "hero", "action": "fold", "amount": None}]
    assert saved.get("villain_cards") is None

    seen_history = []

    def coach(spot, player, *, store, through_id, include_preflop_ev):
        assert player == opponent and include_preflop_ev
        assert spot.board == [] and spot.villain_cards is None
        seen_history.append(len(store.hands(player, through_id=through_id)))
        return {"advice": {"action": "call", "amount": None}, "explain": {
            "chosen": "call", "options": [{"label": "fold", "ev": 0.0}, {"label": "call", "ev": 20.5}]}}

    monkeypatch.setattr("practice_table.advise", coach)
    monkeypatch.setattr(table.bot, "decide_decision", lambda obs: Action("raise", 250))
    next_turn = client.post("/api/practice/table/next", headers=headers, json={"revision": settled["revision"]}).json()
    assert next_turn["hand"] == 2 and next_turn["status"] == "your_turn"
    second = client.post("/api/practice/table/action", headers=headers,
                         json={"revision": next_turn["revision"], "action": "fold"}).json()
    assert second["completed_hands"] == 2
    assert len(HandStore().hands(opponent)) == 2
    review = client.get("/api/practice/table/session", headers=headers).json()
    assert review["completed_hands"] == 2
    assert [(row["hand"], row["estimated_cost"]) for row in review["hands"]] == [(1, 20.5), (2, 20.5)]
    assert seen_history == [0, 1]


def test_independent_tables_and_bounded_requests(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("practice_table.monotonic", lambda: now[0])
    monkeypatch.setattr("practice_table._CREATE_LIMIT", 2)
    monkeypatch.setattr("practice_table._READ_LIMIT", 2)
    client = TestClient(app)
    assert client.post("/api/practice/table", json={"unexpected": 1}).status_code == 422
    assert client.post("/api/practice/table", content=b" " * 2049).status_code == 413
    assert client.post("/api/practice/table", json={"turn_seconds": True}).status_code == 422
    first = client.post("/api/practice/table", json={"opponent": "First"}).json()
    second = client.post("/api/practice/table", json={"opponent": "Second"}).json()
    request = client.post("/api/practice/table", headers={"X-Forwarded-For": "192.0.2.1"})
    assert request.status_code == 429 and request.headers["retry-after"] == "60"
    first_headers = {"Authorization": f"Bearer {first['key']}"}
    second_headers = {"Authorization": f"Bearer {second['key']}"}
    settled = client.post("/api/practice/table/action", headers=first_headers,
                          json={"revision": first["table"]["revision"], "action": "fold"}).json()
    assert settled["status"] == "complete"
    for _ in range(2):
        assert client.get("/api/practice/table", headers=first_headers).status_code == 200
    assert client.get("/api/practice/table", headers=first_headers).status_code == 429
    assert client.get("/api/practice/table", headers=second_headers).json() == second["table"]
    assert client.delete("/api/practice/table", headers=first_headers).status_code == 204
    assert client.get("/api/practice/table", headers=first_headers).status_code == 404
    now[0] += 60
    assert client.post("/api/practice/table").status_code == 201


def test_timeout_and_late_action_save_once_while_another_table_settles(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(practice_table, "monotonic", lambda: now[0])
    client = TestClient(app)
    first = client.post("/api/practice/table", json={"opponent": "First", "turn_seconds": 5}).json()
    second = client.post("/api/practice/table", json={"opponent": "Second", "turn_seconds": 120}).json()
    first_table = _TABLES[first["key"]]
    original_save = first_table.store.add
    writing, release = Event(), Event()

    def slow_save(*args, **kwargs):
        writing.set()
        assert release.wait(10)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(first_table.store, "add", slow_save)
    now[0] += 5

    def act(created, action):
        return client.post(
            "/api/practice/table/action", headers={"Authorization": f"Bearer {created['key']}"},
            json={"revision": created["table"]["revision"], "action": action},
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        expiry = pool.submit(first_table._on_timeout, first["table"]["revision"])
        try:
            assert writing.wait(5)
            late = pool.submit(act, first, "call")
            other = pool.submit(act, second, "fold").result(timeout=5)
            assert other.json()["status"] == "complete"
            assert HandStore().hands("First") == []
        finally:
            release.set()
        expiry.result(timeout=5)
        assert late.result(timeout=5).status_code == 409

    assert first_table.state["status"] == "complete"
    assert first_table.state["last_action_timed_out"] is True
    assert first_table.profile.hands_observed == 1
    assert len(HandStore().hands("First")) == len(HandStore().hands("Second")) == 1


def test_closing_busy_table_does_not_block_another_table(monkeypatch):
    client = TestClient(app)
    first = client.post("/api/practice/table").json()
    second = client.post("/api/practice/table").json()
    busy = _TABLES[first["key"]]
    busy_lock = busy.lock
    waiting = Event()

    class ObservedLock:
        def __enter__(self):
            waiting.set()
            return busy_lock.__enter__()

        def __exit__(self, *args):
            return busy_lock.__exit__(*args)

    monkeypatch.setattr(busy, "lock", ObservedLock())
    with ThreadPoolExecutor(max_workers=2) as pool:
        with busy_lock:
            closing = pool.submit(client.delete, "/api/practice/table",
                                  headers={"Authorization": f"Bearer {first['key']}"})
            assert waiting.wait(5)
            second_state = pool.submit(client.get, "/api/practice/table",
                                       headers={"Authorization": f"Bearer {second['key']}"})
            assert second_state.result(timeout=5).status_code == 200
        assert closing.result(timeout=5).status_code == 204


def test_slow_creation_reserves_capacity_without_blocking_existing_table(monkeypatch):
    client = TestClient(app)
    first = client.post("/api/practice/table").json()
    original = practice_table.PracticeTable
    starting, release = Event(), Event()
    monkeypatch.setattr(practice_table, "_TABLE_LIMIT", 2)

    def slow_create(*args):
        starting.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(practice_table, "PracticeTable", slow_create)
    with ThreadPoolExecutor(max_workers=2) as pool:
        create = pool.submit(client.post, "/api/practice/table")
        try:
            assert starting.wait(5)
            lookup = pool.submit(client.get, "/api/practice/table", headers={"Authorization": f"Bearer {first['key']}"})
            assert lookup.result(timeout=5).status_code == 200
            denied = pool.submit(client.post, "/api/practice/table")
            assert denied.result(timeout=5).status_code == 503
        finally:
            release.set()
        assert create.result(timeout=5).status_code == 201


def test_review_accepts_mixed_strategy_plays_and_costs_against_best_ev():
    from practice_table import _grade_play
    result = {"advice": {"action": "bet", "amount": 200}, "explain": {"chosen": "bet_200", "options": [
        {"label": "check", "frequency": 0.40, "ev": 141.0},
        {"label": "bet_200", "frequency": 0.59, "ev": 141.2},
        {"label": "bet_600", "frequency": 0.01, "ev": 120.0}]}}
    assert _grade_play(Action("check"), result) == (0.2, False)
    assert _grade_play(Action("bet", 200), result) == (0.0, False)
    assert _grade_play(Action("bet", 600), result) == (21.2, True)
    # A free size is graded by the nearest solver size.
    assert _grade_play(Action("bet", 250), result) == (0.0, False)
    # Without solver options the play is compared with the advice.
    assert _grade_play(Action("fold"), {"advice": {"action": "call", "amount": None}, "explain": None}) == (None, True)


def test_a_second_review_is_refused_instead_of_queued():
    table = practice_table.PracticeTable()
    try:
        assert table.review_lock.acquire(blocking=False)
        with pytest.raises(practice_table.HTTPException) as refused:
            table.session_review()
        assert refused.value.status_code == 429
        with pytest.raises(practice_table.HTTPException) as refused:
            table.review(1)
        assert refused.value.status_code == 429
        table.review_lock.release()
        assert table.session_review() == {"completed_hands": 0, "hands": []}
    finally:
        table.closed = True
        if table.timer is not None:
            table.timer.cancel()
