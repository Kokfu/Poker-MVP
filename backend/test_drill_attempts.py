from fastapi.testclient import TestClient

from drills import Answer, DrillStore, Start
from main import app


def test_history_filters_completed_attempts_and_orders_newest_first(tmp_path, monkeypatch):
    path = tmp_path / "attempts-copy.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    store = DrillStore(path)
    advice = {"source": "preflop_chart", "options": [
        {"action": "call", "amount": None, "frequency": 1.0, "ev": 200},
        {"action": "fold", "amount": None, "frequency": 0.0, "ev": 0},
    ]}
    recorded = []
    for category, action in [("preflop_open", "fold"), ("preflop_defend", "call"), ("preflop_open", "timeout")]:
        store.add({"category": category, "legal_actions": ["fold", "call"], "big_blind": 100}, advice)
        spot = store.start(Start(category=category))
        outcome = store.answer(spot["id"], Answer(action=action))
        recorded.append((spot["id"], outcome))

    store.add({"category": "preflop_open", "legal_actions": ["call"], "big_blind": 100}, advice)
    store.start(Start(category="preflop_open"))
    client = TestClient(app)
    response = client.get("/api/drills/attempts?category=preflop_open")
    assert response.headers["cache-control"] == "no-store"
    assert [(row["id"], row["feedback"]) for row in response.json()] == [recorded[2], recorded[0]]
    assert [row["id"] for row in client.get("/api/drills/attempts?limit=2").json()] == [recorded[2][0], recorded[1][0]]
    assert client.get("/api/drills/attempts?category=river_call").json() == []
    assert client.get("/api/drills/attempts?category=invalid").status_code == 422
    assert client.get("/api/drills/attempts?limit=100").status_code == 422
