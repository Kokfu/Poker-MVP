"""Coach multiway advisor and saved-data controls."""
import pytest
from fastapi.testclient import TestClient

import main
from coach.multiway import advise_multiway, multiway_equity
from coach.service import Spot, SpotAction, log_hand
from coach.store import HandStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "coach.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return HandStore(path)


def test_equity_falls_as_opponents_are_added():
    one = multiway_equity(["As", "Ad"], [], 1, iterations=4000, seed=7)["equity"]
    four = multiway_equity(["As", "Ad"], [], 4, iterations=4000, seed=7)["equity"]
    eight = multiway_equity(["As", "Ad"], [], 8, iterations=4000, seed=7)["equity"]
    assert 0.80 < one < 0.88  # AA vs one random hand is ~85%
    assert 0.50 < four < 0.62  # ~56% four-way
    assert eight < four < one


def test_equity_is_seeded_and_ties_split():
    first = multiway_equity(["7s", "2d"], ["As", "Ks", "Qs", "Js", "Ts"], 3, iterations=500, seed=1)
    again = multiway_equity(["7s", "2d"], ["As", "Ks", "Qs", "Js", "Ts"], 3, iterations=500, seed=1)
    assert first == again
    # Royal flush on board: every player plays the board and splits four ways.
    assert first["tie_rate"] == 1.0 and first["equity"] == pytest.approx(0.25)


def test_advice_follows_pot_odds():
    weak = advise_multiway(["7c", "2d"], ["As", "Kh", "Qd"], 3, pot=300, to_call=300, iterations=2000, seed=3)
    assert weak["action"] == "fold" and weak["required_equity"] == pytest.approx(0.5)
    nuts = advise_multiway(["As", "Ad"], ["Ah", "Ac", "7d"], 3, pot=300, to_call=50, iterations=2000, seed=3)
    assert nuts["action"] == "raise"
    free = advise_multiway(["As", "Ad"], ["Ah", "Ac", "7d"], 3, pot=300, to_call=0, iterations=2000, seed=3)
    assert free["action"] == "bet"
    assert "random hands" in free["note"]


@pytest.mark.parametrize("hero, board, opponents, message", [
    (["As"], [], 2, "two hero cards"),
    (["As", "Kd"], ["2c"], 2, "0, 3, 4, or 5"),
    (["As", "As"], [], 2, "duplicate"),
    (["As", "Kd"], [], 9, "opponents must be"),
])
def test_bad_multiway_input_is_rejected(hero, board, opponents, message):
    with pytest.raises(ValueError, match=message):
        advise_multiway(hero, board, opponents, pot=100, to_call=0, iterations=10)


def test_multiway_api(store):
    client = TestClient(main.app)
    response = client.post("/api/coach/multiway", json={"hero_cards": ["ah", "kh"], "board": [], "opponents": 3, "pot": 150, "to_call": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["opponents"] == 3 and 0 < body["equity"] < 1 and body["action"] in {"fold", "call", "raise"}
    assert client.post("/api/coach/multiway", json={"hero_cards": ["Ah", "Kh"], "opponents": 9, "pot": 1}).status_code == 422
    assert client.post("/api/coach/multiway", json={"hero_cards": ["Ah", "Ah"], "opponents": 2, "pot": 1}).status_code == 422


def test_storage_summary_and_delete_all(store):
    hand = Spot(hero_cards=["As", "Kd"], actions=[SpotAction("hero", "fold")])
    log_hand(hand, "Alice", store=store)
    log_hand(hand, "Bob", store=store)
    client = TestClient(main.app)

    summary = client.get("/api/coach/storage").json()
    assert summary["hands"] == 2 and summary["opponents"] == 2
    assert summary["path"].endswith("coach.sqlite") and summary["size_bytes"] > 0

    assert client.delete("/api/coach/hands").status_code == 422  # confirmation is required
    assert client.delete("/api/coach/hands?confirm=delete-all").json() == {"deleted": 2}
    assert client.get("/api/coach/storage").json()["hands"] == 0
    assert client.get("/api/coach/opponents").json() == []
