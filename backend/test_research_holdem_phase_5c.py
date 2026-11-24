import json

import pytest

from coach.service import advise, SpotAction
from research.holdem import river_risk, river_shadow
from research.holdem.phase_4k import river_spot
from research.holdem.phase_4v import stable
from research.holdem.phase_5c import interval, schedule


@pytest.mark.parametrize("nominal, stress, selected, expected", [
    ({"check": 0, "shove": .5}, {"check": 0, "shove": -2}, "shove", True),
    ({"check": 0, "shove": 4}, {"check": 0, "shove": 1}, "shove", False),
    ({"fold": 0, "call": -1}, {"fold": 0, "call": 2}, "fold", True),
    ({"fold": 0, "call": 4}, {"fold": 0, "call": 1}, "call", False),
    ({"fold": 0, "call": -3}, {"fold": 0, "call": -3.5}, "call", False),
    ({"fold": 0, "call": 1}, {"fold": 0, "call": -1.99}, "call", False),
])
def test_diagnostic_needs_material_adverse_sensitivity(nominal, stress, selected, expected):
    result = river_risk.diagnose(nominal, {"scenario": stress}, selected)
    assert result["flagged"] is expected
    assert result["reasons"] == (["scenario"] if expected else [])
    assert result["worst_stress_regret_bb"] == max(0., max(stress.values()) - stress[selected])


def test_unique_schedule_and_interval():
    rows = list(schedule())
    assert len(rows) == len({case.board for case, *_ in rows}) == len({row[-1] for row in rows}) == 96
    assert interval(0, 0) is None
    assert interval(0, 10)["wilson95"] == pytest.approx([0., .2775328])


def test_closing_risk_is_private_and_cannot_change_advice(tmp_path, monkeypatch):
    spot = river_spot("Ah Kh", "Qh Jh Th 3c 7d", 1250)
    spot.actions[-1] = SpotAction("villain", "all_in")
    monkeypatch.delenv(river_shadow.FLAG, raising=False)
    monkeypatch.setenv(river_shadow.TRACE_DIR, str(tmp_path))
    baseline = stable(advise(spot, seed=917))
    assert not list(tmp_path.iterdir())
    monkeypatch.setenv(river_shadow.FLAG, "1")
    assert stable(advise(spot, seed=917)) == baseline
    (trace_path,) = tmp_path.glob("*.json")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["status"] == "complete"
    diagnostic = trace["decision_risk"]
    assert not diagnostic["flagged"]
    assert diagnostic["profile_hands_observed"] == diagnostic["river_reply_observations"] == 0
    assert len(diagnostic["closing_ev_bb"]) == 2
    for values in diagnostic["closing_ev_bb"].values():
        assert values == pytest.approx(trace["bounded_ev_bb"], abs=1e-10)
    assert "decision_risk" not in json.dumps(baseline)
    trace_path.unlink()

    def fail(*args):
        raise ValueError("private fixture")

    monkeypatch.setattr(river_risk, "evaluate", fail)
    assert stable(advise(spot, seed=917)) == baseline
    (trace_path,) = tmp_path.glob("*.json")
    failed = json.loads(trace_path.read_text(encoding="utf-8"))
    assert failed["status"] == "error" and failed["reason"] == "ValueError"
    assert "private fixture" not in json.dumps(failed)
