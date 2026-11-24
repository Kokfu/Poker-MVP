from coach.service import Spot, SpotAction, advise
from coach.store import HandStore
from solver.bot import ReplayError, SolverBot
from test_solver_phase_4i import seed_store


def test_coach_solver_fallback_respects_disabled_adaptation(tmp_path, monkeypatch):
    store = HandStore(tmp_path / "coach.sqlite")
    seed_store(store, {"tight": 150})
    spot = Spot(hero_cards=["Jc", "9d"], board=["Qh", "7s", "2d"], actions=[
        SpotAction("hero", "call"), SpotAction("villain", "check"), SpotAction("villain", "check"),
    ])

    def fail(*args):
        raise ReplayError("forced fallback")

    monkeypatch.setattr(SolverBot, "_decide", fail)
    cold = advise(spot, exploit=False, store=store, seed=917)
    off = advise(spot, opponent="tight", exploit=False, store=store, seed=917)
    on = advise(spot, opponent="tight", exploit=True, store=store, seed=917)
    assert off == advise(spot, opponent="tight", exploit=False, store=store, seed=917)
    assert off["opponent_profile"] == on["opponent_profile"]
    assert off["opponent_profile"]["hands_observed"] == 150
    assert not off["exploiting"] and on["exploiting"]
    assert off["advice"] == cold["advice"] == {"action": "check", "amount": None}
    assert on["advice"] == {"action": "bet", "amount": 100}
    for row in (cold, off, on):
        assert row["explanation"] == {"source": "fallback", "reason": "ReplayError: forced fallback"}
        advice, state = row["advice"], row["state"]
        assert advice["action"] in state["legal_actions"]
        if advice["amount"] is not None:
            assert state["minimum_target"] <= advice["amount"] <= state["maximum_target"]
