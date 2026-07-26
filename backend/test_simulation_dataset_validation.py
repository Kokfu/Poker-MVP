import copy
import json

import pytest

from simulation.dataset import HIDDEN_FIELDS, SCHEMA_VERSION, validate_dataset


def valid_record():
    return {
        "schema_version": SCHEMA_VERSION,
        "simulation_id": "validation-simulation",
        "hand_id": "hand-1",
        "hand_number": 1,
        "decision_index": 0,
        "seed": 42,
        "bot_name": "ScriptedBot",
        "acting_player": "a",
        "position": "BTN",
        "street": "preflop",
        "hero_cards": ["As", "Kd"],
        "board_cards": [],
        "hero_stack": 9950,
        "opponent_stack": 9900,
        "starting_stack": 10000,
        "big_blind": 100,
        "pot": 150,
        "hero_street_commitment": 50,
        "opponent_street_commitment": 100,
        "current_highest_bet": 100,
        "amount_to_call": 50,
        "last_full_raise_size": 100,
        "raising_reopened": True,
        "pending_players": ["a"],
        "minimum_target_to": 200,
        "maximum_target_to": 10000,
        "all_in_target_to": 10000,
        "legal_actions": ["fold", "call", "raise", "all_in"],
        "chosen_action": {"type": "call", "amount": None},
        "chosen_target_to": 100,
        "action_classification": "normal_call",
        "all_in_classification": None,
        "hand_ended_by": "fold",
        "winner": "a",
        "showdown": False,
        "net_chips": 100,
        "final_reward_bb": 1.0,
    }


MISSING_FIELDS = [
    "schema_version",
    "simulation_id",
    "hand_number",
    "decision_index",
    "acting_player",
    "street",
    "chosen_action",
    "legal_actions",
]


@pytest.mark.parametrize("field", MISSING_FIELDS)
def test_validator_rejects_missing_required_fields(tmp_path, field):
    record = valid_record()
    del record[field]
    path = tmp_path / f"missing-{field}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = validate_dataset(str(path))
    assert result["invalid_records"] == 1
    assert result["errors"][0]["line"] == 1
    assert field in result["errors"][0]["reason"]


def mutate(record, case):
    if case == "unsupported_old_schema":
        record["schema_version"] = "1.0"
    elif case == "unsupported_new_schema":
        record["schema_version"] = "99.0"
    elif case == "empty_simulation_id":
        record["simulation_id"] = ""
    elif case == "invalid_hand_number":
        record["hand_number"] = 0
    elif case == "invalid_acting_player":
        record["acting_player"] = "c"
    elif case == "invalid_street":
        record["street"] = "showdown"
    elif case == "invalid_card":
        record["hero_cards"][0] = "1s"
    elif case == "duplicate_hero":
        record["hero_cards"] = ["As", "As"]
    elif case == "duplicate_board":
        record.update(street="flop", board_cards=["2c", "2c", "3d"])
    elif case == "hero_board_overlap":
        record.update(street="flop", board_cards=["As", "2c", "3d"])
    elif case == "hero_count":
        record["hero_cards"] = ["As"]
    elif case == "preflop_board":
        record["board_cards"] = ["2c"]
    elif case == "flop_board_length":
        record.update(street="flop", board_cards=["2c", "3d"])
    elif case == "turn_board_length":
        record.update(street="turn", board_cards=["2c", "3d", "4h"])
    elif case == "river_board_length":
        record.update(street="river", board_cards=["2c", "3d", "4h", "5s"])
    elif case in {
        "negative_hero_stack",
        "negative_opponent_stack",
        "negative_pot",
        "negative_commitment",
        "negative_call",
    }:
        field = {
            "negative_hero_stack": "hero_stack",
            "negative_opponent_stack": "opponent_stack",
            "negative_pot": "pot",
            "negative_commitment": "hero_street_commitment",
            "negative_call": "amount_to_call",
        }[case]
        record[field] = -1
    elif case == "highest_below_commitment":
        record["current_highest_bet"] = 49
    elif case == "all_in_below_commitment":
        record["all_in_target_to"] = 49
    elif case == "minimum_wrong_type":
        record["minimum_target_to"] = "200"
    elif case == "maximum_wrong_type":
        record["maximum_target_to"] = "10000"
    elif case == "chosen_absent_from_legal":
        record["chosen_action"]["type"] = "check"
        record["action_classification"] = "free_check"
    elif case == "check_facing_wager":
        record["legal_actions"].append("check")
        record["chosen_action"] = {"type": "check", "amount": None}
        record["chosen_target_to"] = None
        record["action_classification"] = "free_check"
    elif case == "call_when_free":
        record.update(
            hero_street_commitment=100,
            amount_to_call=0,
            chosen_target_to=100,
        )
    elif case == "bet_facing_wager":
        record["legal_actions"].append("bet")
        record["chosen_action"] = {"type": "bet", "amount": 200}
        record["chosen_target_to"] = 200
        record["action_classification"] = "opening_bet"
    elif case == "raise_without_wager":
        record.update(
            hero_street_commitment=0,
            opponent_street_commitment=0,
            current_highest_bet=0,
            amount_to_call=0,
            minimum_target_to=100,
            maximum_target_to=9950,
            all_in_target_to=9950,
            chosen_target_to=100,
        )
        record["chosen_action"] = {"type": "raise", "amount": 100}
        record["action_classification"] = "full_raise"
    elif case == "raise_closed":
        record["raising_reopened"] = False
        record["chosen_action"] = {"type": "raise", "amount": 200}
        record["chosen_target_to"] = 200
        record["action_classification"] = "full_raise"
    elif case in {"raise_below_minimum", "raise_above_maximum"}:
        target = 199 if case == "raise_below_minimum" else 10001
        record["chosen_action"] = {"type": "raise", "amount": target}
        record["chosen_target_to"] = target
        record["action_classification"] = "full_raise"
    elif case == "raise_advertised_when_unaffordable":
        record.update(hero_stack=100, maximum_target_to=150, all_in_target_to=150)
    elif case == "all_in_target_mismatch":
        record["chosen_action"] = {"type": "all_in", "amount": None}
        record["chosen_target_to"] = 9999
        record["action_classification"] = "full_all_in_raise"
        record["all_in_classification"] = "full_all_in_raise"
    elif case == "increasing_all_in_closed":
        record["raising_reopened"] = False
        record["legal_actions"] = ["fold", "call", "all_in"]
        record["chosen_action"] = {"type": "all_in", "amount": None}
        record["chosen_target_to"] = 10000
        record["action_classification"] = "full_all_in_raise"
        record["all_in_classification"] = "full_all_in_raise"
    elif case == "short_all_in_as_call":
        record.update(
            hero_stack=50,
            maximum_target_to=100,
            all_in_target_to=100,
        )
    elif case == "target_on_fold":
        record["chosen_action"] = {"type": "fold", "amount": 5}
        record["chosen_target_to"] = 5
        record["action_classification"] = "fold"
    elif case == "target_on_check":
        record.update(
            hero_street_commitment=100,
            amount_to_call=0,
            chosen_target_to=100,
        )
        record["legal_actions"].append("check")
        record["chosen_action"] = {"type": "check", "amount": 100}
        record["action_classification"] = "free_check"
    elif case == "net_out_of_bounds":
        record["net_chips"] = 10001
        record["final_reward_bb"] = 100.01
    elif case == "winner_negative_net":
        record["net_chips"] = -100
        record["final_reward_bb"] = -1
    elif case == "loser_positive_net":
        record["winner"] = "b"
    elif case == "tie_nonzero":
        record["winner"] = None
    elif case == "wrong_reward":
        record["final_reward_bb"] = 100
    elif case == "invalid_hand_ended_by":
        record["hand_ended_by"] = "all_in"
    else:
        raise AssertionError(case)


INVALID_CASES = [
    "unsupported_old_schema",
    "unsupported_new_schema",
    "empty_simulation_id",
    "invalid_hand_number",
    "invalid_acting_player",
    "invalid_street",
    "invalid_card",
    "duplicate_hero",
    "duplicate_board",
    "hero_board_overlap",
    "hero_count",
    "preflop_board",
    "flop_board_length",
    "turn_board_length",
    "river_board_length",
    "negative_hero_stack",
    "negative_opponent_stack",
    "negative_pot",
    "negative_commitment",
    "negative_call",
    "highest_below_commitment",
    "all_in_below_commitment",
    "minimum_wrong_type",
    "maximum_wrong_type",
    "chosen_absent_from_legal",
    "check_facing_wager",
    "call_when_free",
    "bet_facing_wager",
    "raise_without_wager",
    "raise_closed",
    "raise_below_minimum",
    "raise_above_maximum",
    "raise_advertised_when_unaffordable",
    "all_in_target_mismatch",
    "increasing_all_in_closed",
    "short_all_in_as_call",
    "target_on_fold",
    "target_on_check",
    "net_out_of_bounds",
    "winner_negative_net",
    "loser_positive_net",
    "tie_nonzero",
    "wrong_reward",
    "invalid_hand_ended_by",
]


@pytest.mark.parametrize("case", INVALID_CASES)
def test_validator_rejects_schema_state_action_and_result_mutations(tmp_path, case):
    record = valid_record()
    mutate(record, case)
    path = tmp_path / f"{case}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = validate_dataset(str(path))
    assert result["invalid_records"] >= 1
    assert result["errors"][0]["line"] == 1
    assert result["errors"][0]["reason"]


@pytest.mark.parametrize("field", sorted(HIDDEN_FIELDS))
def test_validator_rejects_hidden_information_fields(tmp_path, field):
    record = valid_record()
    record[field] = ["Qc", "Jh"]
    path = tmp_path / f"hidden-{field}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = validate_dataset(str(path))
    assert result["invalid_records"] == 1
    assert "hidden-information" in result["errors"][0]["reason"]


@pytest.mark.parametrize(
    "content",
    [
        "{not-json}\n",
        "\n",
        json.dumps([valid_record()]) + "\n",
        json.dumps(valid_record()) + "\n{broken}\n",
    ],
    ids=["invalid-json", "blank", "top-level-array", "trailing-malformed"],
)
def test_validator_rejects_file_and_json_failures(tmp_path, content):
    path = tmp_path / "invalid.jsonl"
    path.write_text(content, encoding="utf-8")
    result = validate_dataset(str(path))
    assert result["invalid_records"] >= 1
    assert result["errors"]


@pytest.mark.parametrize(
    "indexes", [(0, 0), (1, 0), (0, 2)], ids=["duplicate", "decreasing", "skipped"]
)
def test_validator_rejects_noncontiguous_decision_order(tmp_path, indexes):
    records = []
    for index in indexes:
        record = valid_record()
        record["decision_index"] = index
        records.append(record)
    path = tmp_path / "ordering.jsonl"
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    result = validate_dataset(str(path))
    assert result["invalid_records"] >= 1
    assert any("decision_index" in error["reason"] for error in result["errors"])


def test_validator_rejects_inconsistent_results_within_hand(tmp_path):
    first = valid_record()
    second = copy.deepcopy(first)
    second["decision_index"] = 1
    second["winner"] = "b"
    second["net_chips"] = -100
    second["final_reward_bb"] = -1
    path = tmp_path / "inconsistent-results.jsonl"
    path.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )
    result = validate_dataset(str(path))
    assert result["invalid_records"] == 1
    assert "inconsistent result" in result["errors"][0]["reason"]


@pytest.mark.parametrize(
    "winner,net,reward",
    [("a", 10000, 100.0), ("b", -10000, -100.0)],
)
def test_exact_stack_extremes_equal_one_hundred_bb(tmp_path, winner, net, reward):
    record = valid_record()
    record["winner"] = winner
    record["net_chips"] = net
    record["final_reward_bb"] = reward
    path = tmp_path / f"reward-{net}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = validate_dataset(str(path))
    assert result["invalid_records"] == 0
