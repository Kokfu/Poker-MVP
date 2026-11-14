"""Step 16: end-to-end Coach learning loop.

Villain hands are produced by the real engine with the local bots (``tight``, ``aggressive``,
``equity``) against a fixed ``aggressive`` hero, converted to Coach spots, logged through the
HTTP API into SQLite, and the stored profile / advice are checked.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from coach.service import Spot, SpotAction, advise, spot_to_dict
from coach.store import HandStore
from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine

BACKEND = Path(__file__).resolve().parent
HANDS = 120


class _Recorder:
    def __init__(self, bot, actor, log):
        self.bot, self.actor, self.log = bot, actor, log

    def decide(self, observation):
        action = self.bot.decide(observation)
        amount = action.amount if action.type in ("bet", "raise") else None
        self.log.append(SpotAction(self.actor, action.type, amount))
        return action


def simulated_spots(villain: str, count: int, hero: str = "aggressive", seed0: int = 0) -> list[Spot]:
    """Completed heads-up hands, hero = seat a, with every action recorded as a Coach entry."""
    spots = []
    for index in range(count):
        log: list[SpotAction] = []
        button = "a" if index % 2 == 0 else "b"
        hero_bot = BOT_TYPES[hero](seed=seed0 + index, equity_iterations=100)
        villain_bot = BOT_TYPES[villain](seed=10_000 + seed0 + index, equity_iterations=100)
        engine = HandEngine(_Recorder(hero_bot, "hero", log), _Recorder(villain_bot, "villain", log),
                            seed=seed0 + index, button=button, hand_id=f"sim-{index}")
        result = engine.play()
        assert result["illegal_actions"] == 0
        spots.append(Spot(
            hero_cards=list(engine.holes["a"]), board=list(result["state"].community_cards),
            hero_position="button" if button == "a" else "big_blind", actions=log,
            villain_cards=list(engine.holes["b"]) if result["showdown"] else None))
    return spots


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "coach.sqlite"
    monkeypatch.setenv("COACH_DB_PATH", str(path))
    return path


@pytest.fixture(scope="module")
def corpus():
    return {villain: simulated_spots(villain, HANDS) for villain in ("tight", "aggressive", "equity")}


def log_all(client, spots, name):
    for spot in spots:
        response = client.post("/api/coach/hands", json={**spot_to_dict(spot), "opponent": name})
        assert response.status_code == 200, response.text


# --- (a) the stored profile converges to the villain's true type -------------------------

@pytest.mark.slow
def test_profile_converges_to_true_type(db, corpus):
    client = TestClient(main.app)
    for villain in corpus:
        log_all(client, corpus[villain][:10], villain)
    early = client.get("/api/coach/opponents/tight").json()["profile"]
    assert early["hands_observed"] == 10 and early["classification"] == "unknown" and not early["label"]["assigned"]

    for villain in corpus:
        log_all(client, corpus[villain][10:], villain)
    profiles = {villain: client.get(f"/api/coach/opponents/{villain}").json()["profile"] for villain in corpus}
    assert all(p["hands_observed"] == HANDS and p["label"]["assigned"] for p in profiles.values())
    tight, aggressive, equity = (profiles[v] for v in ("tight", "aggressive", "equity"))
    assert tight["classification"].startswith("tight_")
    assert aggressive["classification"] == "loose_aggressive"
    assert equity["classification"] == "loose_passive"
    # key stats match each bot's real behaviour: TightBot plays few hands, AggressiveBot raises almost every
    # hand, EquityBot limps and (almost) never raises or folds to a raise.
    assert tight["preflop"]["vpip"]["frequency"] < 0.5
    assert aggressive["preflop"]["vpip"]["frequency"] > 0.8 and aggressive["preflop"]["preflop_raise"]["frequency"] > 0.5
    assert equity["preflop"]["limp"]["frequency"] > 0.6 and equity["preflop"]["preflop_raise"]["frequency"] < 0.1
    assert aggressive["preflop"]["fold_to_raise"]["frequency"] < 0.2 < tight["preflop"]["fold_to_raise"]["frequency"]
    assert len(client.get("/api/coach/opponents").json()) == 3


# --- (b) advice changes in the expected direction between a cold and a warmed profile -----

FACING_BET = Spot(hero_cards=["Jc", "9d"], hero_position="big_blind", board=["Qh", "7s", "2d"],
                  actions=[SpotAction("villain", "raise", 250), SpotAction("hero", "call"),
                           SpotAction("hero", "check"), SpotAction("villain", "bet", 200)])
BTN_TRASH = Spot(hero_cards=["7c", "2d"])
BTN_KQO = Spot(hero_cards=["Kc", "Qd"])


def _probs(result):
    return dict(zip(result["explanation"]["labels"], result["explanation"]["probabilities"]))


@pytest.mark.slow
def test_warm_profile_changes_advice_in_expected_direction(db, corpus):
    store = HandStore(db)
    for villain, spots in corpus.items():
        for spot in spots:
            store.add(villain, spot_to_dict(spot))

    cold = advise(FACING_BET, store=store)
    assert cold["exploiting"] is False and cold["adjusted"] is False and _probs(cold)["fold"] > 0.5  # J-high vs a bet: mostly folds

    # Against the wide, bet-heavy aggressive villain hero stops folding a bluff-catcher.
    warm = advise(FACING_BET, opponent="aggressive", store=store)
    assert warm["exploiting"] is True and warm["adjusted"] is True
    assert warm["opponent_profile"]["classification"] == "loose_aggressive"
    assert _probs(cold)["fold"] - _probs(warm)["fold"] > 0.3

    # Against an EquityBot villain that never raises and never folds to a raise, hero no longer folds a
    # trash hand on the button (it can limp for free).
    cold_trash = advise(BTN_TRASH, store=store)
    assert _probs(cold_trash)["fold"] > 0.9
    warm_equity = advise(BTN_TRASH, opponent="equity", store=store)
    assert warm_equity["adjusted"] and _probs(warm_equity)["fold"] < _probs(cold_trash)["fold"] - 0.5

    # The adjustment is villain-specific: different opponents produce different advice somewhere.
    vectors = {v: [advise(spot, opponent=v, store=store)["explanation"]["probabilities"] for spot in (BTN_KQO, FACING_BET)]
               for v in corpus}
    assert len({json.dumps(vector) for vector in vectors.values()}) == 3

    # exploit=False ignores the stored profile, and the cold answer is deterministic.
    assert advise(FACING_BET, opponent="aggressive", exploit=False, store=store)["explanation"]["probabilities"] \
        == cold["explanation"]["probabilities"]


# --- (c) persistence across process restarts ----------------------------------------------

@pytest.mark.slow
def test_profile_and_advice_survive_a_process_restart(db, corpus):
    client = TestClient(main.app)
    log_all(client, corpus["aggressive"][:40], "Persisted Villain")
    before = client.get("/api/coach/opponents/Persisted Villain").json()
    advice_before = client.post("/api/coach/advise", json={**spot_to_dict(FACING_BET), "opponent": "Persisted Villain"}).json()

    code = (
        "import json, main\n"
        "from fastapi.testclient import TestClient\n"
        "c = TestClient(main.app)\n"
        "spot = json.loads(%r)\n"
        "print(json.dumps({'opponents': c.get('/api/coach/opponents').json(),"
        " 'profile': c.get('/api/coach/opponents/Persisted Villain').json(),"
        " 'advice': c.post('/api/coach/advise', json=dict(spot, opponent='Persisted Villain')).json()}))\n"
    ) % json.dumps(spot_to_dict(FACING_BET))
    run = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True,
                         env={**os.environ, "COACH_DB_PATH": str(db)}, timeout=300)
    assert run.returncode == 0, run.stderr[-2000:]
    after = json.loads(run.stdout.strip().splitlines()[-1])
    assert after["opponents"] == [{"name": "Persisted Villain", "hands": 40}]
    assert after["profile"] == before
    assert after["advice"]["advice"] == advice_before["advice"]
    assert after["advice"]["explanation"]["probabilities"] == advice_before["explanation"]["probabilities"]


# --- (d) bad input is rejected cleanly -----------------------------------------------------

GOOD_ACTIONS = [{"actor": "hero", "action": "raise", "amount": 250}, {"actor": "villain", "action": "fold"}]


@pytest.mark.parametrize("patch", [
    {"hero_cards": ["As"]},
    {"hero_cards": ["As", "Xx"]},
    {"hero_cards": ["As", "As"]},
    {"hero_cards": "AsKd"},
    {"board": ["2c", "3c"]},
    {"board": ["As", "2c", "3c"]},
    {"actions": [{"actor": "robot", "action": "fold"}]},
    {"actions": [{"actor": "hero", "action": "shove"}]},
    {"actions": [{"actor": "hero", "action": "raise"}]},
    {"actions": [{"actor": "hero", "action": "raise", "amount": -5}]},
    {"actions": [{"actor": "hero", "action": "raise", "amount": 10**12}]},
    {"actions": [{"actor": "villain", "action": "call"}]},
    {"actions": GOOD_ACTIONS + [{"actor": "hero", "action": "check"}]},
    {"small_blind": 0},
    {"small_blind": 500, "big_blind": 100},
    {"hero_stack": -1},
    {"hero_stack": 1.5},
    {"villain_stack": "lots"},
    {"hero_position": "cutoff"},
    {"villain_cards": ["Qh"]},
    {"villain_cards": ["As", "Qh"]},
])
def test_bad_input_is_rejected_cleanly_and_stores_nothing(db, patch):
    client = TestClient(main.app, raise_server_exceptions=False)
    body = {"hero_cards": ["As", "Kd"], "actions": GOOD_ACTIONS, **patch}
    assert client.post("/api/coach/advise", json=body).status_code == 422
    assert client.post("/api/coach/hands", json={**body, "opponent": "Bad Input"}).status_code == 422
    assert client.get("/api/coach/opponents").json() == []


@pytest.mark.parametrize("name", ["", "   ", "x" * 61])
def test_bad_opponent_names_are_rejected(db, name):
    client = TestClient(main.app, raise_server_exceptions=False)
    body = {"hero_cards": ["As", "Kd"], "actions": GOOD_ACTIONS, "opponent": name}
    assert client.post("/api/coach/hands", json=body).status_code == 422
    assert client.get("/api/coach/opponents").json() == []


def test_incomplete_hand_cannot_be_logged_and_unknown_opponent_is_empty(db):
    client = TestClient(main.app, raise_server_exceptions=False)
    body = {"hero_cards": ["As", "Kd"], "actions": GOOD_ACTIONS[:1], "opponent": "Half Hand"}
    response = client.post("/api/coach/hands", json=body)
    assert response.status_code == 422 and "completed hands" in response.json()["detail"]
    assert client.get("/api/coach/opponents/Nobody").json() == {"name": "Nobody", "profile": None}
    assert client.get("/api/coach/review").status_code == 200
    # advice for an opponent with no logged hands falls back to the plain solver
    unknown = client.post("/api/coach/advise", json={"hero_cards": ["As", "Kd"], "opponent": "Nobody"}).json()
    assert unknown["status"] == "hero_to_act" and unknown["exploiting"] is False


def test_sql_metacharacters_in_a_name_are_stored_literally(db):
    client = TestClient(main.app)
    name = "x'); DROP TABLE hands;--"
    body = {"hero_cards": ["As", "Kd"], "actions": GOOD_ACTIONS, "opponent": name}
    assert client.post("/api/coach/hands", json=body).status_code == 200
    assert client.get("/api/coach/opponents").json() == [{"name": name, "hands": 1}]
