from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

import drills
from drill_spots import LINES, grade, make_spot
from main import app


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "coach-copy.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return drills.DrillStore(path)


@pytest.fixture(scope="module")
def preflop():
    return make_spot("preflop_open", 41)


@pytest.mark.parametrize("category", LINES)
def test_categories_use_legal_public_simulator_decisions(category):
    spot, advice = make_spot(category, 54 if category == "river_bluff" else 41)
    assert spot["category"] == category
    assert len(spot["hero_cards"]) == 2
    assert len(spot["board"]) == (0 if category.startswith("preflop") else 3 if category.startswith("flop") else 4 if category == "turn" else 5)
    assert {"villain_cards", "future_cards", "seed"}.isdisjoint(spot)
    assert advice["source"] != "fallback"
    assert sum(option["frequency"] for option in advice["options"]) == pytest.approx(1, abs=0.002)
    for option in advice["options"]:
        assert option["action"] in spot["legal_actions"]
        if option["amount"] is not None:
            assert spot["minimum_target"] <= option["amount"] <= spot["maximum_target"]
    if category == "river_bluff":
        assert any(option["action"] == "bet" and option["frequency"] >= 0.05 for option in advice["options"])


def test_api_filters_keeps_answer_private_and_scores_once(store, preflop, monkeypatch):
    now = 100
    monkeypatch.setattr(drills, "time", lambda: now)
    store.add(*preflop)
    client = TestClient(app)
    assert client.post("/api/drills/start", json={"category": "turn"}).json() is None
    reply = client.post("/api/drills/start", json={"category": "preflop_open"})
    assert reply.headers["Cache-Control"] == "no-store"
    spot = reply.json()
    assert spot["remaining_ms"] == 15000
    assert {"options", "advice", "best"}.isdisjoint(spot)
    url = f"/api/drills/{spot['id']}/answer"
    assert client.post(url, json={"action": "check"}).status_code == 422
    assert client.post(url, json={"action": "raise", "amount": 1}).status_code == 422
    now += 2.5
    outcome = client.post(url, json={"action": "call"}).json()
    assert outcome["correct"] is True
    assert outcome["cost_bb"] == 0
    assert outcome["elapsed_ms"] == 2500
    assert client.post(url, json={"action": "fold"}).json() == outcome
    assert client.get("/api/drills/stats").json() == {"categories": [
        {"category": "preflop_open", "attempts": 1, "correct": 1, "average_ms": 2500,
         "average_cost_bb": 0, "costed": 1},
    ], "ready": {}}


def test_timeout_and_concurrent_starts(store, preflop, monkeypatch):
    now = 100
    monkeypatch.setattr(drills, "time", lambda: now)
    store.add(*preflop)
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(store.start, (drills.Start(seconds=3), drills.Start(seconds=3))))
    assert results.count(None) == 1
    spot = next(spot for spot in results if spot is not None)
    now += 4
    result = store.answer(spot["id"], drills.Answer(action="call"))
    assert (result["action"], result["elapsed_ms"], result["correct"], result["cost_bb"]) == ("timeout", 3000, False, None)
    assert store.stats()[0]["costed"] == 0


def test_off_menu_wager_estimates_cost_using_nearest_size():
    options = [
        {"action": "check", "amount": None, "frequency": 0.7, "ev": 120},
        {"action": "bet", "amount": 300, "frequency": 0.3, "ev": 100},
    ]
    result = grade(options, "bet", 340, 100)
    assert result == {"best": options[0], "reference": options[1], "correct": False, "cost_bb": 0.2}
    assert grade(options, "bet", 300, 100)["correct"] is True
