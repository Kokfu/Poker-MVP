import json

import pytest

from simulation import agent_cli
from simulation.actions import Action
from simulation.duplicate_evaluation import DuplicateConfig, DuplicatePair
from solver.showdown import ShowdownModel


def test_resume_replays_only_an_uncommitted_session(monkeypatch, tmp_path):
    config = DuplicateConfig(pairs=3, session_hands=5)
    first, second, third = config.seeds()
    played = []
    interrupt = True

    def play(config, strategy, opponent, seed, *, diagnostics):
        assert strategy == "solver_adaptive" and opponent == "tight"
        played.append(seed)
        if seed == second and interrupt:
            raise KeyboardInterrupt
        diagnostics["solver_fallback_actions"] = 0
        return DuplicatePair(seed, seed - first + 100, -50, 0, 0, True, config.session_hands)

    monkeypatch.setattr(agent_cli, "play_duplicate_pair", play)
    with pytest.raises(KeyboardInterrupt):
        agent_cli.run_sessions(tmp_path, "test", "tight", config, resume=False)
    assert played == [first, second]
    ledger_path = tmp_path / "test.jsonl"
    header, legacy_session = ledger_path.read_text().splitlines()
    legacy_record = json.loads(legacy_session)
    del legacy_record["solver_fallback_actions"]
    ledger_path.write_text(f"{header}\n{json.dumps(legacy_record)}\n")
    with ledger_path.open("ab") as ledger:
        ledger.write(b'{"session":2,"partial')
    interrupt = False
    played.clear()
    summary = agent_cli.run_sessions(tmp_path, "test", "tight", config, resume=True)
    assert played == [second, third]
    assert summary["sessions"] == 3 and summary["hands"] == 30
    assert summary["bb_per_100"] == pytest.approx(5.5)
    assert [row["bb_per_100"] for row in summary["by_session"]] == [5, 5.5, 6]
    assert summary["early_vs_late"]["early_bb_per_100"] == 5
    assert summary["early_vs_late"]["late_bb_per_100"] == 5.75
    assert summary["solver_fallback_coverage_sessions"] == 2
    assert summary["solver_fallback_actions"] is None
    assert summary["confidence_interval"]["lower"] <= summary["bb_per_100"] <= summary["confidence_interval"]["upper"]
    assert json.loads((tmp_path / "test.summary.json").read_text()) == summary
    rows = [json.loads(line) for line in (tmp_path / "test.jsonl").read_text().splitlines()]
    assert [row["session"] for row in rows[1:]] == [1, 2, 3]
    played.clear()
    assert agent_cli.run_sessions(tmp_path, "test", "tight", config, resume=True) == summary
    assert played == []


def test_agent_refuses_to_reuse_an_existing_ledger_with_new_settings(monkeypatch, tmp_path):
    config = DuplicateConfig(pairs=1, session_hands=2)
    def play(config, strategy, opponent, seed, *, diagnostics):
        diagnostics["solver_fallback_actions"] = 0
        return DuplicatePair(seed, 0, 0, 0, 0, True, config.session_hands)

    monkeypatch.setattr(agent_cli, "play_duplicate_pair", play)
    agent_cli.run_sessions(tmp_path, "existing", "tight", config, resume=False)
    with pytest.raises(FileExistsError):
        agent_cli.run_sessions(tmp_path, "existing", "tight", config, resume=False)
    with pytest.raises(ValueError, match="parameters"):
        agent_cli.run_sessions(tmp_path, "existing", "random", config, resume=True)


def test_learning_profile_persists_and_resumes_only_from_committed_session(monkeypatch, tmp_path):
    profile_dir = tmp_path / "profiles"
    config = DuplicateConfig(pairs=2, session_hands=4)
    first, second = config.seeds()
    starts = []
    interrupt = True

    def play(config, strategy, opponent, seed, *, learning, diagnostics):
        modeled = learning["a"].models["b"]
        showdown = learning["a"].showdowns.setdefault("a", ShowdownModel())
        starts.append((seed, modeled.hands_observed, showdown.percentiles["call"].copy()))
        modeled.hands_observed += config.session_hands
        modeled.stats["vpip"].observe(True)
        modeled.sizing.observe(.55)
        showdown.percentiles["call"].append(.25)
        learning["b"].models["a"].hands_observed += config.session_hands
        if seed == second and interrupt:
            raise KeyboardInterrupt
        diagnostics["solver_fallback_actions"] = 0
        return DuplicatePair(seed, 200, 100, 0, 0, True, config.session_hands)

    monkeypatch.setattr(agent_cli, "play_duplicate_pair", play)
    with pytest.raises(KeyboardInterrupt):
        agent_cli.run_sessions(tmp_path, "first", "tight", config, resume=False, profile_dir=profile_dir)
    assert starts == [(first, 0, []), (second, 4, [.25])]
    with pytest.raises(ValueError, match="unfinished"):
        agent_cli.run_sessions(tmp_path, "second", "tight", config, resume=False, profile_dir=profile_dir)

    interrupt = False
    resumed = agent_cli.run_sessions(tmp_path, "first", "tight", config, resume=True, profile_dir=profile_dir)
    assert starts[-1] == (second, 4, [.25])
    assert resumed["profile_hands"] == {"initial": {"a": 0, "b": 0}, "final": {"a": 8, "b": 8}}
    assert resumed["early_vs_late"]["late_bb_per_100"] == 37.5
    assert "confidence_interval" not in resumed
    with pytest.raises(ValueError, match="overlap"):
        agent_cli.run_sessions(tmp_path, "second", "tight", config, resume=False, profile_dir=profile_dir)
    next_config = DuplicateConfig(pairs=2, session_hands=4, seed_offset=200)
    later = agent_cli.run_sessions(tmp_path, "second", "tight", next_config, resume=False, profile_dir=profile_dir)
    assert starts[-2] == (next_config.seeds()[0], 8, [.25, .25])
    assert later["profile_hands"] == {"initial": {"a": 8, "b": 8}, "final": {"a": 16, "b": 16}}
    assert agent_cli.run_sessions(tmp_path, "first", "tight", config, resume=True, profile_dir=profile_dir) == resumed
    with pytest.raises(FileExistsError):
        agent_cli.run_sessions(tmp_path, "first", "tight", config, resume=False)


@pytest.mark.parametrize("session_hands", [1, 3])
def test_agent_counts_solver_fallbacks_separately_from_engine_fallbacks(monkeypatch, tmp_path, session_hands):
    class FakeSolver:
        def __init__(self):
            self.fallback_count = 0

        def decide(self, observation):
            self.fallback_count += 1
            return Action("check" if "check" in observation.legal_actions else "fold")

    monkeypatch.setattr("simulation.duplicate_evaluation._bot", lambda *args: FakeSolver())
    config = DuplicateConfig(pairs=2, session_hands=session_hands)
    report = agent_cli.run_sessions(tmp_path, "fallback", "tight", config, resume=False)
    assert report["solver_fallback_actions"] == 4 * session_hands
    assert report["solver_fallback_coverage_sessions"] == 2
    assert report["fallback_actions"] == report["illegal_actions"] == report["deal_mismatches"] == 0
