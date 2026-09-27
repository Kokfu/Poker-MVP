"""Phase 5F Coach: engine-validated manual spots, advice, and opponent profiles."""
import pytest
from fastapi.testclient import TestClient

import main
from coach.service import Spot, SpotAction, advise, log_hand, profile_for
from coach.store import HandStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "coach.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return HandStore(path)


def spot(*actions, board=(), position="button", cards=("As", "Kd"), villain_cards=None):
    return Spot(hero_cards=list(cards), board=list(board), hero_position=position,
                actions=[SpotAction(*a) for a in actions], villain_cards=villain_cards)


def test_first_decision_gets_solver_advice(store):
    result = advise(spot(), store=store)
    assert result["status"] == "hero_to_act"
    explanation = result["explanation"]
    assert explanation["source"] == "preflop_chart"
    assert sum(explanation["probabilities"]) == pytest.approx(1.0, abs=1e-3)
    assert result["advice"]["action"] in {"fold", "call", "raise", "all_in"}
    assert 0.5 < explanation["hero_equity_vs_range"] < 0.75
    assert result["state"]["legal_actions"] and result["exploiting"] is False


def test_big_blind_waits_for_villain_then_board():
    waiting = advise(spot(position="big_blind"))
    assert waiting["status"] == "villain_to_act" and waiting["state"]["to_call"] == 50
    need = advise(spot(("villain", "raise", 250), ("hero", "call"), position="big_blind"))
    assert need == {"status": "need_board", "street": "flop", "cards_needed": 3}
    flop = advise(spot(("villain", "raise", 250), ("hero", "call"), board=("7h", "8d", "2c"), position="big_blind"))
    assert flop["status"] == "hero_to_act" and flop["explanation"]["source"] == "postflop_solve"


@pytest.mark.parametrize("actions,message", [
    ((("villain", "call"),), "hero's turn"),
    ((("hero", "raise", 120),), "between"),
    ((("hero", "check"),), "not legal"),
    ((("hero", "fold"), ("villain", "check")), "remove the later actions"),
])
def test_illegal_entries_are_rejected(actions, message):
    with pytest.raises(ValueError, match=message):
        advise(spot(*actions))


def test_invalid_cards_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        advise(spot(cards=("As", "As")))
    with pytest.raises(ValueError, match="0, 3, 4, or 5"):
        advise(spot(("hero", "call"), ("villain", "check"), board=("2c", "3c")))


def test_logging_builds_a_profile_and_enables_exploitation(store):
    completed = spot(("hero", "raise", 250), ("villain", "fold"))
    with pytest.raises(ValueError, match="only completed hands"):
        log_hand(spot(("hero", "raise", 250)), "Villain One", store)
    for _ in range(3):
        summary = log_hand(completed, "Villain One", store)
    assert summary["opponent_profile"]["hands_observed"] == 3
    model = profile_for(store, "villain one")  # names are normalized per exact text
    assert model.hands_observed == 0
    assert profile_for(store, "Villain One").stats["fold_to_raise"].occurrences == 3
    result = advise(spot(), opponent="Villain One", store=store)
    assert result["exploiting"] is True and result["opponent_profile"]["hands_observed"] == 3
    assert advise(spot(), opponent="Villain One", exploit=False, store=store)["exploiting"] is False


def test_showdown_hand_with_shown_cards_reports_net(store):
    hand = spot(("hero", "call"), ("villain", "check"), ("villain", "check"), ("hero", "check"),
                ("villain", "check"), ("hero", "check"), ("villain", "check"), ("hero", "check"),
                board=("2c", "7d", "9h", "Js", "3c"), villain_cards=["Qh", "Qd"])
    result = advise(hand, store=store)
    assert result == {"status": "hand_complete", "summary": {"showdown": True, "board": ["2c", "7d", "9h", "Js", "3c"], "hero_net": -100}}


def test_api_routes(store):
    client = TestClient(main.app)
    response = client.post("/api/coach/advise", json={"hero_cards": ["as", "KD"], "hero_position": "button"})
    assert response.status_code == 200 and response.json()["status"] == "hero_to_act"
    bad = client.post("/api/coach/advise", json={"hero_cards": ["As", "Kd"], "actions": [{"actor": "villain", "action": "call"}]})
    assert bad.status_code == 422 and "hero's turn" in bad.json()["detail"]
    logged = client.post("/api/coach/hands", json={"hero_cards": ["As", "Kd"], "opponent": "Reg", "actions": [{"actor": "hero", "action": "raise", "amount": 250}, {"actor": "villain", "action": "fold"}]})
    assert logged.status_code == 200 and logged.json()["opponent_profile"]["hands_observed"] == 1
    assert client.get("/api/coach/opponents").json() == [{"name": "Reg", "hands": 1}]
    assert client.get("/api/coach/opponents/Reg").json()["profile"]["hands_observed"] == 1


def test_list_hands_for_opponent_newest_first_with_name_normalization(store):
    client = TestClient(main.app)
    for amount in (200, 250, 300):
        response = client.post("/api/coach/hands", json={
            "hero_cards": ["As", "Kd"], "opponent": "Villain Two",
            "actions": [{"actor": "hero", "action": "raise", "amount": amount}, {"actor": "villain", "action": "fold"}],
        })
        assert response.status_code == 200
    listed = client.get("/api/coach/opponents/Villain Two/hands")
    assert listed.status_code == 200
    hands = listed.json()
    assert [hand["spot"]["actions"][0]["amount"] for hand in hands] == [300, 250, 200]
    assert all("id" in hand and "created_at" in hand for hand in hands)
    assert hands[0]["id"] > hands[-1]["id"]
    # extra internal whitespace normalizes to the same stored name
    same = client.get("/api/coach/opponents/Villain%20%20Two/hands")
    assert same.status_code == 200 and len(same.json()) == 3
    assert client.get("/api/coach/opponents/Nobody/hands").json() == []


def test_delete_hand(store):
    client = TestClient(main.app)
    logged = client.post("/api/coach/hands", json={
        "hero_cards": ["As", "Kd"], "opponent": "Villain Three",
        "actions": [{"actor": "hero", "action": "raise", "amount": 250}, {"actor": "villain", "action": "fold"}],
    })
    hand_id = client.get("/api/coach/opponents/Villain Three/hands").json()[0]["id"]
    assert client.delete("/api/coach/hands/999999").status_code == 404
    ok = client.delete(f"/api/coach/hands/{hand_id}")
    assert ok.status_code == 200 and ok.json() == {"deleted": True}
    assert client.get("/api/coach/opponents/Villain Three/hands").json() == []
    assert client.delete(f"/api/coach/hands/{hand_id}").status_code == 404


def test_delete_opponent(store):
    client = TestClient(main.app)
    for _ in range(2):
        client.post("/api/coach/hands", json={
            "hero_cards": ["As", "Kd"], "opponent": "Villain Four",
            "actions": [{"actor": "hero", "action": "raise", "amount": 250}, {"actor": "villain", "action": "fold"}],
        })
    deleted = client.delete("/api/coach/opponents/Villain Four")
    assert deleted.status_code == 200 and deleted.json() == {"deleted": 2}
    assert client.get("/api/coach/opponents/Villain Four/hands").json() == []
    assert client.get("/api/coach/opponents").json() == []
    assert client.delete("/api/coach/opponents/Nobody").json() == {"deleted": 0}
