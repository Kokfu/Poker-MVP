import json
from copy import deepcopy

import pytest

from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.bots import AggressiveBot, EquityBot, RandomBot, TightBot
from simulation.engine import HandEngine
from simulation.history_service import (
    HAND_DOCUMENT_TYPE,
    MATCH_DOCUMENT_TYPE,
    make_hand_document,
    run_builtin_hand_history,
    run_builtin_match_history,
    serialize_hand_history,
    validate_history_document,
)


def event(payload, event_type, actor=None):
    return next(
        item
        for item in payload["events"]
        if item["event_type"] == event_type
        and (actor is None or item["actor"] == actor)
    )


def check_down_history(seed=400):
    engine = HandEngine(
        ScriptedBot(
            [Action("call"), Action("check"), Action("check"), Action("check")]
        ),
        ScriptedBot(
            [Action("check"), Action("check"), Action("check"), Action("check")]
        ),
        seed=seed,
    )
    return engine, engine.play()["history"]


def test_hand_service_returns_required_document_and_history_fields():
    document = run_builtin_hand_history(seed=401)
    assert document["document_type"] == HAND_DOCUMENT_TYPE
    assert document["history_schema_version"] == "1.0"
    assert document["validation"] == {
        "valid": True,
        "errors": [],
        "warnings": [],
    }
    assert {
        "hand_id",
        "match_id",
        "hand_number",
        "hand_seed",
        "button_player",
        "small_blind_player",
        "big_blind_player",
        "small_blind_amount",
        "big_blind_amount",
        "starting_stack_a",
        "starting_stack_b",
        "events",
        "final_stack_a",
        "final_stack_b",
        "winner",
        "ending_type",
        "final_board",
        "showdown",
        "settlement_complete",
        "illegal_action_count",
        "fallback_diagnostics",
    } <= document["history"].keys()


def test_same_hand_configuration_is_fully_deterministic():
    first = run_builtin_hand_history(
        bot_a="tight", bot_b="aggressive", seed=42, equity_iterations=500
    )
    second = run_builtin_hand_history(
        bot_a="tight", bot_b="aggressive", seed=42, equity_iterations=500
    )
    assert first == second


def test_different_seeds_can_change_serialized_card_history():
    first = run_builtin_hand_history(seed=402)
    second = run_builtin_hand_history(seed=403)
    first_cards = [
        card
        for item in first["history"]["events"]
        for card in item["new_cards"]
    ]
    second_cards = [
        card
        for item in second["history"]["events"]
        for card in item["new_cards"]
    ]
    assert first_cards != second_cards or (
        first["history"]["ending_type"] != second["history"]["ending_type"]
    )


def test_fold_serialization_omits_all_hole_cards():
    engine = HandEngine(
        ScriptedBot([Action("fold")]), ScriptedBot([]), seed=404
    )
    payload = serialize_hand_history(engine.play()["history"])
    assert payload["ending_type"] == "fold"
    assert all(item["revealed_hole_cards"] is None for item in payload["events"])


def test_showdown_serialization_reveals_only_legitimate_cards():
    engine, history = check_down_history(seed=405)
    payload = serialize_hand_history(history)
    revealed = [
        item for item in payload["events"] if item["revealed_hole_cards"]
    ]
    assert len(revealed) == 1
    assert revealed[0]["event_type"] == "showdown"
    assert revealed[0]["revealed_hole_cards"] == engine.holes
    assert all(
        item["revealed_hole_cards"] is None
        for item in payload["events"][: revealed[0]["event_index"]]
    )


def test_future_cards_never_appear_before_public_reveal():
    _, history = check_down_history(seed=406)
    payload = serialize_hand_history(history)
    final_board = payload["final_board"]
    for item in payload["events"]:
        assert item["board"] == final_board[: len(item["board"])]
    reveals = [
        item for item in payload["events"] if item["event_type"] == "board_revealed"
    ]
    assert [len(item["new_cards"]) for item in reveals] == [3, 1, 1]


def test_no_deck_or_burn_keys_appear_recursively():
    document = run_builtin_match_history(max_hands=3, seed=407)
    forbidden = {
        "deck",
        "deck_order",
        "remaining_deck",
        "remaining_cards",
        "burn_cards",
        "future_cards",
    }

    def scan(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(document)


def test_short_small_blind_is_serialized_exactly():
    document = run_builtin_hand_history(
        starting_stack_a=30,
        starting_stack_b=1000,
        small_blind=50,
        big_blind=100,
        button_player="a",
        seed=408,
    )
    blind = event(document["history"], "blind_posted", "a")
    assert blind["assigned_amount"] == 50
    assert blind["posted_amount"] == 30
    assert blind["post_was_all_in"] is True
    assert blind["stack_a_after"] == 0


def test_short_big_blind_is_serialized_exactly():
    document = run_builtin_hand_history(
        starting_stack_a=1000,
        starting_stack_b=70,
        small_blind=50,
        big_blind=100,
        button_player="a",
        seed=409,
    )
    blind = event(document["history"], "blind_posted", "b")
    assert blind["assigned_amount"] == 100
    assert blind["posted_amount"] == 70
    assert blind["post_was_all_in"] is True
    assert blind["stack_b_after"] == 0


def test_total_target_bet_and_raise_are_preserved():
    engine = HandEngine(
        ScriptedBot([Action("call"), Action("raise", 300)]),
        ScriptedBot([Action("check"), Action("bet", 100), Action("fold")]),
        seed=410,
    )
    payload = serialize_hand_history(engine.play()["history"])
    bet = next(
        item for item in payload["events"] if item["applied_action"] == "bet"
    )
    raise_event = next(
        item for item in payload["events"] if item["applied_action"] == "raise"
    )
    assert bet["target_total"] == 100
    assert bet["amount_paid"] == 100
    assert raise_event["target_total"] == 300
    assert raise_event["amount_paid"] == 300


@pytest.mark.parametrize(
    "starting_b,a_actions,expected",
    [
        (500, [Action("raise", 500)], "exact_call"),
        (300, [Action("raise", 500)], "short_call"),
        (350, [Action("raise", 300), Action("call")], "short_raise"),
        (500, [Action("raise", 200), Action("call")], "full_raise"),
    ],
)
def test_all_in_classifications_serialize(starting_b, a_actions, expected):
    engine = HandEngine(
        ScriptedBot(a_actions),
        ScriptedBot([Action("all_in")]),
        starting_stacks={"a": 1000, "b": starting_b},
        seed=411,
    )
    payload = serialize_hand_history(engine.play()["history"])
    all_in = next(
        item
        for item in payload["events"]
        if item["event_type"] == "action_taken" and item["actor"] == "b"
    )
    assert all_in["all_in_classification"] == expected


def test_automatic_runout_serializes_flop_turn_and_river():
    engine = HandEngine(
        ScriptedBot([Action("all_in")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=412,
    )
    payload = serialize_hand_history(engine.play()["history"])
    assert sum(
        item["event_type"] == "automatic_runout_started"
        for item in payload["events"]
    ) == 1
    reveals = [
        item for item in payload["events"] if item["event_type"] == "board_revealed"
    ]
    assert [item["street"] for item in reveals] == ["flop", "turn", "river"]


def test_serialized_settlement_is_exactly_once_and_cleared():
    _, history = check_down_history(seed=413)
    payload = serialize_hand_history(history)
    settled = [
        item for item in payload["events"] if item["event_type"] == "hand_settled"
    ]
    assert len(settled) == 1
    assert settled[0] == payload["events"][-1]
    assert settled[0]["pot_after"] == 0
    assert settled[0]["street_commitment_a_after"] == 0
    assert settled[0]["street_commitment_b_after"] == 0


def test_invalid_internal_history_is_refused():
    _, history = check_down_history(seed=414)
    damaged = deepcopy(history)
    damaged.final_stack_a += 1
    with pytest.raises(ValueError, match="invalid internal hand history"):
        serialize_hand_history(damaged)


def test_match_document_has_one_valid_history_per_hand():
    document = run_builtin_match_history(
        bot_a="tight",
        bot_b="aggressive",
        starting_stack=1000,
        small_blind=5,
        big_blind=10,
        max_hands=4,
        seed=42,
        equity_iterations=500,
    )
    assert document["document_type"] == MATCH_DOCUMENT_TYPE
    assert document["history_count"] == document["match"]["hands_played"]
    assert len(document["histories"]) == document["history_count"]
    assert document["invalid_history_count"] == 0
    assert document["aggregate_validation"]["valid"] is True


def test_match_histories_carry_stacks_and_alternate_positions():
    histories = run_builtin_match_history(max_hands=5, seed=415)["histories"]
    for previous, current in zip(histories, histories[1:]):
        assert current["starting_stack_a"] == previous["final_stack_a"]
        assert current["starting_stack_b"] == previous["final_stack_b"]
        assert current["button_player"] != previous["button_player"]
        assert current["small_blind_player"] == current["button_player"]
        assert current["big_blind_player"] != current["button_player"]


def test_match_document_conserves_chips_and_zero_sum_net():
    document = run_builtin_match_history(max_hands=5, seed=416)
    match = document["match"]
    assert match["final_stack_a"] + match["final_stack_b"] == (
        match["starting_stack"] * 2
    )
    assert match["bot_a_net_chips"] + match["bot_b_net_chips"] == 0


def test_zero_stack_no_op_call_records_actual_commitment():
    histories = run_builtin_match_history(max_hands=3, seed=407)["histories"]
    no_op_call = next(
        item
        for history in histories
        for item in history["events"]
        if item["event_type"] == "action_taken"
        and item["applied_action"] == "call"
        and item["amount_paid"] == 0
    )
    actor = no_op_call["actor"]
    commitment_after = no_op_call[
        f"street_commitment_{actor}_after"
    ]
    assert no_op_call["target_total"] == commitment_after


def test_serialized_history_round_trips_without_nan_or_infinity():
    document = run_builtin_match_history(max_hands=3, seed=417)
    text = json.dumps(document, allow_nan=False)
    assert json.loads(text) == document
    assert "NaN" not in text
    assert "Infinity" not in text


@pytest.mark.parametrize(
    "bot_class",
    [RandomBot, TightBot, AggressiveBot, EquityBot],
)
def test_all_builtin_bots_produce_valid_serializable_histories(bot_class):
    engine = HandEngine(
        bot_class(seed=418, equity_iterations=100),
        RandomBot(seed=419),
        seed=420,
    )
    document = make_hand_document(engine.play()["history"])
    validation = validate_history_document(document)
    assert validation["valid"], validation["errors"]
