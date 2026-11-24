import json

import pytest

from simulation import agent_cli
from simulation.duplicate_evaluation import DuplicateConfig, DuplicatePair


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
