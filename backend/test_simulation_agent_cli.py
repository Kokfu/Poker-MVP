import json

import pytest

from simulation import agent_cli
from simulation.duplicate_evaluation import DuplicateConfig, DuplicatePair
from solver.showdown import ShowdownModel


def test_resume_replays_only_an_uncommitted_session(monkeypatch, tmp_path):
    config = DuplicateConfig(pairs=3, session_hands=5)
    first, second, third = config.seeds()
    played = []
    interrupt = True

    def play(config, strategy, opponent, seed):
        assert strategy == "solver_adaptive" and opponent == "tight"
        played.append(seed)
        if seed == second and interrupt:
            raise KeyboardInterrupt
        return DuplicatePair(seed, seed - first + 100, -50, 0, 0, True, config.session_hands)

    monkeypatch.setattr(agent_cli, "play_duplicate_pair", play)
    with pytest.raises(KeyboardInterrupt):
        agent_cli.run_sessions(tmp_path, "test", "tight", config, resume=False)
    assert played == [first, second]
    with (tmp_path / "test.jsonl").open("ab") as ledger:
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
    assert summary["confidence_interval"]["lower"] <= summary["bb_per_100"] <= summary["confidence_interval"]["upper"]
    assert json.loads((tmp_path / "test.summary.json").read_text()) == summary
    rows = [json.loads(line) for line in (tmp_path / "test.jsonl").read_text().splitlines()]
    assert [row["session"] for row in rows[1:]] == [1, 2, 3]
    played.clear()
    assert agent_cli.run_sessions(tmp_path, "test", "tight", config, resume=True) == summary
    assert played == []


def test_agent_refuses_to_reuse_an_existing_ledger_with_new_settings(monkeypatch, tmp_path):
    config = DuplicateConfig(pairs=1, session_hands=2)
    monkeypatch.setattr(agent_cli, "play_duplicate_pair",
                        lambda *args: DuplicatePair(args[-1], 0, 0, 0, 0, True, config.session_hands))
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

    def play(config, strategy, opponent, seed, *, learning):
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
