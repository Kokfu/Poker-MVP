import json

import pytest

from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.dataset import HIDDEN_FIELDS, JsonlDataset, SCHEMA_VERSION, validate_dataset
from simulation.engine import HandEngine


def with_dataset(engine, path):
    engine.dataset = JsonlDataset(str(path), overwrite=True)
    return engine


def fold_sequence(path):
    return with_dataset(
        HandEngine(
            ScriptedBot([Action("call"), Action("bet", 100), Action("raise", 700)]),
            ScriptedBot(
                [Action("check"), Action("check"), Action("raise", 300), Action("fold")]
            ),
            seed=60,
            simulation_id="regression",
            hand_number=1,
            simulation_seed=42,
        ),
        path,
    )


def showdown_sequence(path, seed=61):
    return with_dataset(
        HandEngine(
            ScriptedBot([Action("call"), Action("check"), Action("check"), Action("check")]),
            ScriptedBot([Action("check"), Action("check"), Action("check"), Action("check")]),
            seed=seed,
            simulation_id="regression",
            hand_number=2,
            simulation_seed=42,
        ),
        path,
    )


def all_in_sequence(path, kind):
    actions = {
        "preflop": ([Action("all_in")], [Action("all_in")], 1000, None),
        "flop": (
            [Action("call"), Action("all_in")],
            [Action("check"), Action("all_in")],
            1000,
            None,
        ),
        "turn": (
            [Action("call"), Action("check"), Action("all_in")],
            [Action("check"), Action("check"), Action("all_in")],
            1000,
            None,
        ),
        "exact_call": ([Action("raise", 500)], [Action("all_in")], 1000, 400),
        "short_call": ([Action("raise", 500)], [Action("all_in")], 1000, 200),
        "short_raise": (
            [Action("raise", 300), Action("call")],
            [Action("all_in")],
            1000,
            250,
        ),
        "full_raise": (
            [Action("raise", 200), Action("call")],
            [Action("all_in")],
            1000,
            400,
        ),
    }
    a_actions, b_actions, stack, b_remaining = actions[kind]
    engine = HandEngine(
        ScriptedBot(a_actions),
        ScriptedBot(b_actions),
        stack=stack,
        seed=62,
        simulation_id="regression",
        hand_number=3,
        simulation_seed=42,
    )
    if b_remaining is not None:
        engine.state.stacks["b"] = b_remaining
        engine.starting_stacks["b"] = b_remaining + engine.bb
        engine.total = sum(engine.state.stacks.values()) + engine.state.pot
    return with_dataset(engine, path)


def records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def assert_common_record(record):
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["simulation_id"]
    assert record["hand_number"] >= 1
    assert record["decision_index"] >= 0
    assert record["acting_player"] in {"a", "b"}
    assert record["position"] in {"BTN", "BB"}
    assert len(record["hero_cards"]) == 2
    assert len(record["board_cards"]) == {
        "preflop": 0,
        "flop": 3,
        "turn": 4,
        "river": 5,
    }[record["street"]]
    assert len(record["hero_cards"] + record["board_cards"]) == len(
        set(record["hero_cards"] + record["board_cards"])
    )
    for field in (
        "hero_stack",
        "opponent_stack",
        "pot",
        "hero_street_commitment",
        "opponent_street_commitment",
        "current_highest_bet",
        "amount_to_call",
        "last_full_raise_size",
        "maximum_target_to",
        "all_in_target_to",
    ):
        assert record[field] >= 0
    assert record["chosen_action"]["type"] in record["legal_actions"]
    assert record["final_reward_bb"] == record["net_chips"] / record["big_blind"]
    assert not HIDDEN_FIELDS & record.keys()


@pytest.mark.parametrize(
    "source,expected_classification",
    [
        ("fold", "free_check"),
        ("fold", "normal_call"),
        ("fold", "opening_bet"),
        ("fold", "full_raise"),
        ("fold", "fold"),
        ("exact_call", "exact_all_in_call"),
        ("short_call", "short_all_in_call"),
        ("short_raise", "short_all_in_raise"),
        ("full_raise", "full_all_in_raise"),
    ],
)
def test_decision_action_regression_matrix(tmp_path, source, expected_classification):
    path = tmp_path / f"{source}-{expected_classification}.jsonl"
    engine = fold_sequence(path) if source == "fold" else all_in_sequence(path, source)
    engine.play()
    data = records(path)
    assert any(r["action_classification"] == expected_classification for r in data)
    assert validate_dataset(str(path))["invalid_records"] == 0
    assert [r["decision_index"] for r in data] == list(range(len(data)))
    for record in data:
        assert_common_record(record)


@pytest.mark.parametrize("street", ["preflop", "flop", "turn"])
def test_automatic_all_in_runout_dataset_records(tmp_path, street):
    path = tmp_path / f"runout-{street}.jsonl"
    engine = all_in_sequence(path, street)
    result = engine.play()
    data = records(path)
    assert result["showdown"] is True
    assert len(engine.state.community_cards) == 5
    assert all(record["hand_ended_by"] == "showdown" for record in data)
    assert all(record["showdown"] is True for record in data)
    assert validate_dataset(str(path))["invalid_records"] == 0


def test_fold_and_showdown_result_reward_formulas(tmp_path):
    fold_path = tmp_path / "fold.jsonl"
    fold_engine = fold_sequence(fold_path)
    fold_result = fold_engine.play()
    fold_records = records(fold_path)
    assert all(record["hand_ended_by"] == "fold" for record in fold_records)
    assert all(record["showdown"] is False for record in fold_records)
    for record in fold_records:
        player = record["acting_player"]
        assert record["winner"] == fold_result["winner"]
        assert record["net_chips"] == (
            fold_result["stacks"][player] - record["starting_stack"]
        )
        assert record["final_reward_bb"] == record["net_chips"] / 100

    showdown_path = tmp_path / "showdown.jsonl"
    showdown_engine = showdown_sequence(showdown_path)
    showdown_result = showdown_engine.play()
    showdown_records = records(showdown_path)
    assert all(record["hand_ended_by"] == "showdown" for record in showdown_records)
    for record in showdown_records:
        player = record["acting_player"]
        assert record["winner"] == showdown_result["winner"]
        assert record["net_chips"] == (
            showdown_result["stacks"][player] - record["starting_stack"]
        )


def test_tie_reward_is_zero_and_not_bb_per_100(tmp_path, monkeypatch):
    path = tmp_path / "tie.jsonl"
    engine = showdown_sequence(path, seed=63)
    monkeypatch.setattr("simulation.engine.EVALUATOR.score", lambda *_: 100)
    result = engine.play()
    assert result["winner"] is None
    for record in records(path):
        assert record["winner"] is None
        assert record["net_chips"] == 0
        assert record["final_reward_bb"] == 0


def test_unmatched_excess_return_uses_settled_net_reward(tmp_path):
    path = tmp_path / "unmatched.jsonl"
    engine = all_in_sequence(path, "short_call")
    result = engine.play()
    data = records(path)
    short_call = next(
        r for r in data if r["action_classification"] == "short_all_in_call"
    )
    assert short_call["chosen_target_to"] < short_call["current_highest_bet"]
    for record in data:
        player = record["acting_player"]
        assert record["net_chips"] == (
            result["stacks"][player] - record["starting_stack"]
        )
    assert validate_dataset(str(path))["invalid_records"] == 0


def test_no_hidden_information_or_backward_board_leakage(tmp_path):
    path = tmp_path / "privacy.jsonl"
    engine = showdown_sequence(path)
    engine.play()
    for record in records(path):
        assert not HIDDEN_FIELDS & record.keys()
        assert len(record["board_cards"]) == {
            "preflop": 0,
            "flop": 3,
            "turn": 4,
            "river": 5,
        }[record["street"]]
        assert set(record["hero_cards"]).isdisjoint(record["board_cards"])
