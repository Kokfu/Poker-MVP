from fastapi.testclient import TestClient
import pytest

import drills
from drill_spots import make_spot
from main import app


@pytest.fixture
def active_turn(tmp_path, monkeypatch):
    path = tmp_path / "resume-copy.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    clock = [100.0]
    monkeypatch.setattr(drills, "time", lambda: clock[0])
    store = drills.DrillStore(path)
    store.add(*make_spot("preflop_open", 41))
    client = TestClient(app)
    spot = client.post("/api/drills/start", json={"seconds": 15}).json()
    return client, spot, clock


def test_restore_keeps_the_original_deadline_and_private_answer(active_turn):
    client, spot, clock = active_turn
    url = f"/api/drills/turns/{spot['id']}"
    clock[0] += 5
    snapshot = client.get(url)
    assert snapshot.headers["cache-control"] == "no-store"
    assert snapshot.json() == {"spot": {**spot, "remaining_ms": 10000}, "feedback": None}
    assert client.get("/api/drills/turns/unknown").json() is None
    assert client.get("/api/drills/stats").json()["categories"] == []

    outcome = client.post(f"/api/drills/{spot['id']}/answer", json={"action": "call"}).json()
    assert outcome["elapsed_ms"] == 5000
    assert client.get(url).json() == {"spot": {**spot, "remaining_ms": 0}, "feedback": outcome}


def test_expired_turn_can_be_restored_and_recorded_once(active_turn):
    client, spot, clock = active_turn
    clock[0] += 17
    snapshot = client.get(f"/api/drills/turns/{spot['id']}").json()
    assert snapshot["spot"]["remaining_ms"] == 0 and snapshot["feedback"] is None
    url = f"/api/drills/{spot['id']}/answer"
    outcome = client.post(url, json={"action": "timeout"}).json()
    assert outcome["elapsed_ms"] == 15000 and outcome["action"] == "timeout"
    assert client.post(url, json={"action": "call"}).json() == outcome
    assert client.get("/api/drills/stats").json()["categories"][0]["attempts"] == 1
