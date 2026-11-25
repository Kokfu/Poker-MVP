"""Coach multiway advisor and saved-data controls."""
from collections import Counter
from random import Random

import pytest
from fastapi.testclient import TestClient

import main
from coach.multiway import PublicAction, advise_multiway, multiway_equity
from coach.service import Spot, SpotAction, log_hand
from coach.store import HandStore
from poker_analyzer import FULL_DECK, _weighted_multiway_deals
from simulation.range_intelligence import PublicRangeTracker, legal_opponent_combos


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


def test_uniform_range_matches_published_aces_equity():
    # DeucesCracked published 73.6%, 55.8%, and 34.5% for 2, 4, and 8 opponents.
    hero = ["As", "Ad"]
    candidates = [combo.cards for combo in legal_opponent_combos(hero, [])]
    uniform = (candidates, [1.0] * len(candidates))
    for opponents, published in [(2, .736), (4, .558), (8, .345)]:
        result = multiway_equity(hero, [], opponents, 8000, seed=511,
                                 opponent_ranges=[uniform, uniform])
        assert result["equity"] == pytest.approx(published, abs=.018)


def test_weighted_sampler_draws_the_joint_conditional_distribution():
    first = ([("Qc", "Jc"), ("2h", "3h")], [4, 1])
    second = ([("Qc", "Td"), ("4h", "5h")], [4, 1])
    samples = Counter()
    for deal in _weighted_multiway_deals(Random(19), FULL_DECK, 3, 2, [first, second], 6000):
        assert len(deal) == len(set(deal)) == 7
        samples[tuple(deal[3:])] += 1
    # Non-colliding pairs have weights 4, 4, and 1.
    assert sorted(samples.values()) == pytest.approx([6000 / 9, 24000 / 9, 24000 / 9], rel=.10)


def test_action_ranges_use_only_the_board_visible_at_each_action(monkeypatch):
    seen = []
    observe = PublicRangeTracker.observe

    def track(self, action, board, fraction):
        seen.append((action, tuple(board)))
        return observe(self, action, board, fraction)

    monkeypatch.setattr(PublicRangeTracker, "observe", track)
    hero = ["7s", "2d"]
    board = ["As", "Ks", "Qs", "Js", "Ts"]
    actions = (PublicAction(2, "preflop", "raise"), PublicAction(1, "flop", "bet", .8))
    result = advise_multiway(hero, board, 3, 100, 10, 500, 14, actions=actions)
    assert result == advise_multiway(hero, board, 3, 100, 10, 500, 14, actions=actions)
    assert seen == [("raise", ()), ("bet", tuple(board[:3]))] * 2
    assert result["tie_rate"] == 1 and result["equity"] == pytest.approx(.25)
    assert [item["seat"] for item in result["opponent_ranges"]] == [1, 2]
    assert all(0 < item["effective_combos"] < 990 for item in result["opponent_ranges"])


def test_multiway_action_api_flag_and_validation(store, monkeypatch):
    monkeypatch.delenv("POKER_COACH_MULTIWAY_RANGES", raising=False)
    client = TestClient(main.app)
    path = "/api/coach/multiway"
    request = {"hero_cards": ["As", "Kd"], "opponents": 3, "pot": 150}
    action = {"seat": 2, "action": "call", "street": "preflop"}
    assert client.get(path + "/settings").json() == {"opponent_actions": False}
    assert client.post(path, json={**request, "actions": [action]}).status_code == 422
    assert "opponent_ranges" not in client.post(path, json=request).json()
    monkeypatch.setenv("POKER_COACH_MULTIWAY_RANGES", "1")
    assert client.get(path + "/settings").json() == {"opponent_actions": True}
    assert client.post(path, json={**request, "actions": [{**action, "street": "turn"}]}).status_code == 422
    assert client.post(path, json={**request, "actions": [{**action, "seat": 4}]}).status_code == 422
    assert client.post(path, json={**request, "board": ["2h", "3d", "4c"],
                                  "actions": [{**action, "street": "flop"}, action]}).status_code == 422
    response = client.post(path, json={**request, "actions": [action]})
    assert response.status_code == 200 and response.json()["opponent_ranges"][0]["effective_combos"] < 1225


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
