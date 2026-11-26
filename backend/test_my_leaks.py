from threading import Event

from fastapi.testclient import TestClient
import pytest

from coach.service import Spot, SpotAction, spot_to_dict
from drills import Answer, Start
from main import app
import my_leaks


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "review-copy.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return my_leaks.LeakStore(path)


def entry(category="preflop_open", street="preflop", cost=2.0, correct=False):
    return {
        "category": category, "street": street, "position": "button", "action": "fold", "amount": None,
        "correct": correct, "cost_bb": cost, "best": {"action": "call", "amount": None},
        "reference": None, "spot": {"hero_cards": ["As", "Th"], "board": [], "history": [], "pot": 150, "to_call": 50},
    }


def test_replay_uses_only_visible_cards_prior_actions_and_earlier_logged_hands(store, monkeypatch):
    full = Spot(["As", "Th"], ["3c", "5d", "9s"], villain_cards=["Kh", "Kd"], actions=[
        SpotAction("hero", "raise", 250), SpotAction("villain", "call"), SpotAction("villain", "check"),
        SpotAction("hero", "bet", 250), SpotAction("villain", "fold"),
    ])
    store.hands.add("Example", spot_to_dict(full))
    seen = []

    def fake_advice(prefix, opponent, **kwargs):
        street = "preflop" if not prefix.board else "flop"
        wager = "raise" if street == "preflop" else "bet"
        passive = "call" if street == "preflop" else "check"
        seen.append((prefix.board, len(prefix.actions), prefix.villain_cards, opponent, kwargs["through_id"]))
        return {"state": {"legal_actions": [wager, passive], "minimum_target": 100, "maximum_target": 500},
                "explanation": {"labels": [f"{wager}_250", passive], "probabilities": [1.0, 0.0], "action_ev": [200, 100]}}

    monkeypatch.setattr(my_leaks, "advise", fake_advice)
    hand = store.next_hand()
    rows = my_leaks.review_saved_hand(hand, store.hands, Event())
    assert seen == [([], 0, None, "Example", hand.id - 1), (["3c", "5d", "9s"], 3, None, "Example", hand.id - 1)]
    assert [row["category"] for row in rows] == ["preflop_open", "flop_cbet"]
    assert [row["correct"] for row in rows] == [True, True]
    assert len(rows[1]["spot"]["history"]) == 3
    assert "villain_cards" not in rows[1]["spot"]


def test_leaks_join_all_sources_without_counting_timeout_or_deleted_hands(store):
    spot = spot_to_dict(Spot(["As", "Th"], actions=[SpotAction("hero", "fold")]))
    coach = store.hands.add("Example", spot)
    practice = store.hands.add("Practice bot", spot, practice_source="test-session:1")
    skipped = store.hands.add("Other", spot)
    pending = store.hands.add("Pending", spot)
    assert store.next_hand().id == pending
    store.save_review(coach, [entry(cost=0.5)])
    store.save_review(practice, [entry("flop_cbet", "flop", cost=3.0)])
    store.save_review(skipped, None)

    drill = {**entry()["spot"], "category": "preflop_open", "street": "preflop", "position": "button",
             "big_blind": 100, "legal_actions": ["call", "fold"]}
    advice = {"source": "preflop_chart", "options": [
        {"action": "call", "amount": None, "frequency": 1.0, "ev": 150},
        {"action": "fold", "amount": None, "frequency": 0.0, "ev": 0},
    ]}
    for action in ("fold", "timeout"):
        store.add(drill, advice)
        issued = store.start(Start())
        store.answer(issued["id"], Answer(action=action))

    response = TestClient(app).get("/api/drills/leaks")
    assert response.headers["cache-control"] == "no-store"
    report = response.json()
    assert report["all"] == {"decisions": 3, "different": 3, "costed": 3, "deviation_rate": 1, "total_cost_bb": 5, "average_cost_bb": 1.667}
    assert report["coverage"] == {"coach": {"pending": 1, "reviewed": 1, "skipped": 1},
                                  "practice": {"pending": 0, "reviewed": 1, "skipped": 0}}
    assert report["drill_attempts"] == 2 and report["drill_timeouts"] == 1
    assert [row["category"] for row in report["top"]] == ["flop_cbet", "preflop_open"]
    assert [row["example"]["source"] for row in report["top"]] == ["practice", "drills"]
    assert "test-session" not in response.text
    store.hands.delete_hand(practice)
    assert store.report()["all"]["decisions"] == 2
    with store.connect() as db:
        assert not db.execute("SELECT 1 FROM drill_leak_reviews WHERE hand_id = ?", (practice,)).fetchone()


def test_session_trend_keeps_practice_sessions_and_ranks_only_costed_differences():
    records = [
        ("2026-11-26T00:00:00+00:00", "coach", None, [entry(cost=8.0, correct=True)]),
        ("2026-11-26T00:00:00+00:00", "practice", "session-1", [entry("preflop_defend", cost=None)]),
        ("2026-11-26T00:29:00+00:00", "coach", None, [entry(cost=4.0)]),
        ("2026-11-26T00:35:00+00:00", "practice", "session-2", [entry("turn", "turn", cost=1.0)]),
        ("2026-11-26T01:00:00+00:00", "coach", None, [entry("river_call", "river", cost=3.0)]),
        ("2026-11-26T01:01:00+00:00", "practice", "session-1", [entry("flop_defend", "flop", cost=2.0)]),
    ]
    report = my_leaks.summarize(records[::-1])
    assert [(session["source"], session["decisions"]) for session in report["sessions"]] == [
        ("coach", 2), ("practice", 1), ("coach", 1), ("practice", 2),
    ]
    assert [row["category"] for row in report["top"]] == ["preflop_open", "river_call", "flop_defend"]
    assert report["all"]["costed"] == 5
    assert report["all"]["deviation_rate"] == 0.8333
