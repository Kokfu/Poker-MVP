import json
import random
from dataclasses import replace

import numpy as np
import pytest

from coach import service as coach
from coach.store import HandStore
from research.holdem import river_shadow as shadow
from research.holdem.decoupled_replay import CFRWorkingSet
from research.holdem.phase_4k import river_spot
from research.holdem.phase_4v import coach_spot, stable, verify_history
from simulation.history_service import hand_history_from_dict, run_builtin_hand_history, run_builtin_match_history
from solver.bot import SolverBot


def read_trace(directory):
    (path,) = directory.glob("*.json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("persistent, cap", [(False, None), (True, 128), (True, 384)])
def test_coach_shadow_invariance(tmp_path, monkeypatch, persistent, cap):
    monkeypatch.setenv("POKER_COACH_PERSISTENT_RANGES", str(int(persistent)))
    directory = tmp_path / "traces"
    monkeypatch.setenv(shadow.TRACE_DIR, str(directory))
    monkeypatch.delenv(shadow.FLAG, raising=False)
    monkeypatch.setattr(SolverBot, "range_selection", CFRWorkingSet(cap) if cap else None)
    store = HandStore(tmp_path / "history.sqlite")
    coach.log_hand(coach_spot("tight_aggressive"), "fixture", store)
    spot = river_spot("9h 9d", "Kc 9s 3d 5h Js", 0)
    rng = random.getstate()
    seen = []
    finish = SolverBot._postflop_advice

    def probe(bot, ds, solved, index, hero, column_id, board, reach, info, **kwargs):
        result = finish(bot, ds, solved, index, hero, column_id, board, reach, info, **kwargs)
        column = np.searchsorted(solved.combos[hero], column_id)
        seen.append((reach.tobytes(), solved.average[index][:, column].tobytes(),
                     tuple(ids.tobytes() for ids in solved.combos), stable(result[1])))
        return result

    monkeypatch.setattr(SolverBot, "_postflop_advice", probe)
    before = store.path.read_bytes()
    baseline = coach.advise(spot, "fixture", store=store, seed=917)
    profile = coach.profile_summary(coach.profile_for(store, "fixture").snapshot())
    monkeypatch.setenv(shadow.FLAG, "0")
    assert stable(coach.advise(spot, "fixture", store=store, seed=917)) == stable(baseline)
    assert not directory.exists()
    monkeypatch.setenv(shadow.FLAG, "1")
    # An entered opponent holding is unseen at the decision and must not affect the record.
    advised = coach.advise(replace(spot, villain_cards=["Ah", "Ad"]), "fixture", store=store, seed=917)
    assert stable(advised) == stable(baseline)
    assert seen[0] == seen[1] == seen[2]
    assert random.getstate() == rng
    assert store.path.read_bytes() == before
    assert coach.profile_summary(coach.profile_for(store, "fixture").snapshot()) == profile
    record = read_trace(directory)
    assert record["status"] == "complete", record
    assert record["seeded"] == advised["advice"]["action"] or record["seeded"] == (
        f"{advised['advice']['action']}_{advised['advice']['amount']}")
    assert sum(record["cfr_mix"].values()) == pytest.approx(1., abs=1e-9)
    assert record["range"]["compatible"] == 990
    assert record["projected_ev_bb"] == pytest.approx(record["cfr_ev_bb"], abs=1e-4)
    assert "decision_id" not in advised
    assert "villain_cards" not in record
    assert "sensitivity_ev_bb" not in advised["explanation"]


@pytest.mark.parametrize("failure, expected", [(ValueError, "error"), (TimeoutError, "timeout"),
                                               (shadow.Unsupported, "unsupported")])
def test_shadow_failure_never_changes_advice(tmp_path, monkeypatch, failure, expected):
    monkeypatch.setenv(shadow.TRACE_DIR, str(tmp_path))
    monkeypatch.delenv(shadow.FLAG, raising=False)
    spot = river_spot("9h 9d", "Kc 9s 3d 5h Js", 500)
    baseline = coach.advise(spot)

    def fail(*args):
        raise failure("fixture")

    monkeypatch.setattr(shadow, "snapshot", fail)
    monkeypatch.setenv(shadow.FLAG, "1")
    assert stable(coach.advise(spot)) == stable(baseline)
    assert read_trace(tmp_path)["status"] == expected


def test_trace_write_failure_has_no_public_detail(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv(shadow.FLAG, raising=False)
    spot = river_spot("9h 9d", "Kc 9s 3d 5h Js", 500)
    baseline = coach.advise(spot)
    file = tmp_path / "a-file"
    file.touch()
    monkeypatch.setenv(shadow.TRACE_DIR, str(file))
    monkeypatch.setenv(shadow.FLAG, "1")
    assert stable(coach.advise(spot)) == stable(baseline)
    assert "River shadow output failed (FileExistsError)" in caplog.text
    assert str(file) not in caplog.text


def test_match_and_replays_ignore_coach_shadow(tmp_path, monkeypatch):
    monkeypatch.setenv(shadow.TRACE_DIR, str(tmp_path / "traces"))
    options = dict(bot_a="solver_adaptive", bot_b="tight", seed=42, equity_iterations=500)
    for persistent in ("0", "1"):
        monkeypatch.setenv("POKER_MATCH_PERSISTENT_RANGES", persistent)
        monkeypatch.delenv(shadow.FLAG, raising=False)
        single = run_builtin_hand_history(**options)
        settings = dict(options, max_hands=2, starting_stack=1500)
        match = run_builtin_match_history(**settings)
        monkeypatch.setenv(shadow.FLAG, "1")
        assert run_builtin_hand_history(**options) == single
        assert run_builtin_match_history(**settings) == match
        verify_history(hand_history_from_dict(single["history"]))
        for history in match["histories"]:
            verify_history(hand_history_from_dict(history))
    assert not (tmp_path / "traces").exists()
