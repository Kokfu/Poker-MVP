from fastapi.testclient import TestClient

from main import app
from practice_table import _TABLES
from simulation.actions import Action


def test_table_requires_its_key_and_rejects_invalid_or_stale_actions():
    client = TestClient(app)
    created = client.post("/api/practice/table")
    assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
    key, table = created.json()["key"], created.json()["table"]
    headers = {"Authorization": f"Bearer {key}"}
    assert client.get("/api/practice/table").status_code == 401
    assert client.get("/api/practice/table", headers={"Authorization": "Bearer wrong"}).status_code == 404
    assert client.get("/api/practice/table", headers=headers).json() == table
    assert table["position"] == "BTN" and table["status"] == "your_turn"
    assert "shown_bot_cards" not in table and "seed" not in table and table["board"] == []
    assert table["your_stack"] + table["bot_stack"] + table["pot"] == 20_000

    revision = {"revision": table["revision"]}
    assert client.post("/api/practice/table/next", headers=headers, json=revision).status_code == 409
    invalid = {**revision, "action": "raise", "amount": table["minimum_target"] - 1}
    assert client.post("/api/practice/table/action", headers=headers, json=invalid).status_code == 422
    assert client.get("/api/practice/table", headers=headers).json() == table
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

    def call_all_in(observation):
        seen.append(observation)
        return Action("all_in")

    monkeypatch.setattr(_TABLES[created["key"]].bot, "decide_decision", call_all_in)
    response = client.post("/api/practice/table/action", headers=headers,
                           json={"revision": created["table"]["revision"], "action": "all_in"})
    assert response.status_code == 200
    settled = response.json()
    assert settled["status"] == "complete" and settled["learned_hands"] == 1
    assert settled["your_stack"] + settled["bot_stack"] == 20_000
    assert len(set(settled["your_cards"] + settled["shown_bot_cards"] + settled["board"])) == 9
    assert len(seen) == 1
    assert tuple(settled["shown_bot_cards"]) == seen[0].decision_state.hole_cards
