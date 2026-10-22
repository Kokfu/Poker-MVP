from fastapi.testclient import TestClient

from main import app
from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.dataset import SCHEMA_VERSION
from simulation.engine import HandEngine
from simulation.history import validate_hand_history


client = TestClient(app)

MATCH_TOP_LEVEL_FIELDS = {
    "match_id",
    "seed",
    "bot_a",
    "bot_b",
    "starting_stack",
    "small_blind",
    "big_blind",
    "max_hands",
    "hands_played",
    "final_stack_a",
    "final_stack_b",
    "winner",
    "termination_reason",
    "bot_a_net_chips",
    "bot_b_net_chips",
    "showdowns",
    "fold_ended_hands",
    "illegal_actions",
    "fallback_diagnostics",
    "hand_summaries",
}
MATCH_HAND_FIELDS = {
    "hand_number",
    "button_player",
    "small_blind_player",
    "big_blind_player",
    "starting_stack_a",
    "starting_stack_b",
    "ending_stack_a",
    "ending_stack_b",
    "winner",
    "net_chips_a",
    "net_chips_b",
    "showdown",
    "fold_ended",
    "board",
    "illegal_actions",
    "fallback_diagnostics",
    "settlement_complete",
}


def showdown_engine(seed=300):
    return HandEngine(
        ScriptedBot(
            [Action("call"), Action("check"), Action("check"), Action("check")]
        ),
        ScriptedBot(
            [Action("check"), Action("check"), Action("check"), Action("check")]
        ),
        seed=seed,
    )


def test_fold_ended_history_reveals_no_hole_cards():
    engine = HandEngine(
        ScriptedBot([Action("fold")]),
        ScriptedBot([]),
        seed=301,
    )
    history = engine.play()["history"]
    assert history.ending_type == "fold"
    assert all(event.revealed_hole_cards is None for event in history.events)
    assert validate_hand_history(history).valid


def test_showdown_reveals_only_both_legitimate_hole_cards():
    engine = showdown_engine()
    history = engine.play()["history"]
    revealed_events = [
        event for event in history.events if event.revealed_hole_cards
    ]
    assert len(revealed_events) == 1
    assert revealed_events[0].event_type == "showdown"
    assert revealed_events[0].revealed_hole_cards == engine.holes
    assert all(
        event.revealed_hole_cards is None
        for event in history.events[: revealed_events[0].event_index]
    )


def test_future_board_cards_never_appear_early():
    engine = showdown_engine(seed=302)
    history = engine.play()["history"]
    final_board = history.final_board
    for event in history.events:
        assert event.board == final_board[: len(event.board)]
        if event.street == "preflop":
            assert event.board == []
        if event.street == "flop":
            assert len(event.board) in {0, 3}
        if event.street == "turn":
            assert len(event.board) in {3, 4}


def test_board_reveal_events_contain_only_new_public_cards():
    history = showdown_engine(seed=303).play()["history"]
    reveals = [
        event for event in history.events if event.event_type == "board_revealed"
    ]
    assert [len(event.new_cards) for event in reveals] == [3, 1, 1]
    assert reveals[0].new_cards == reveals[0].board
    assert reveals[1].new_cards == reveals[1].board[3:]
    assert reveals[2].new_cards == reveals[2].board[4:]


def test_history_events_never_serialize_deck_order_or_burn_cards():
    history = showdown_engine(seed=304).play()["history"]
    for event in history.events:
        payload = event.as_dict()
        assert "deck" not in payload
        assert "deck_order" not in payload
        assert "remaining_deck" not in payload
        assert "burn_cards" not in payload


def test_fallback_history_records_request_application_and_reason():
    engine = HandEngine(
        ScriptedBot([Action("check")]),
        ScriptedBot([]),
        seed=305,
    )
    history = engine.play()["history"]
    action = next(
        event for event in history.events if event.event_type == "action_taken"
    )
    assert action.requested_action == "check"
    assert action.applied_action == "fold"
    assert action.fallback_used is True
    assert action.fallback_reason == "ACTION_TYPE_NOT_ALLOWED"
    assert action.legal_actions == ["fold", "call", "raise", "all_in"]
    assert history.illegal_action_count == 1
    assert len(history.fallback_diagnostics) == 1
    assert validate_hand_history(history).valid


def test_match_api_shape_remains_exactly_unchanged_and_private():
    response = client.post(
        "/api/matches/simulate",
        json={
            "bot_a": "tight",
            "bot_b": "aggressive",
            "starting_stack": 1000,
            "small_blind": 5,
            "big_blind": 10,
            "max_hands": 3,
            "seed": 42,
            "equity_iterations": 500,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == MATCH_TOP_LEVEL_FIELDS
    assert payload["hand_summaries"]
    assert all(set(hand) == MATCH_HAND_FIELDS for hand in payload["hand_summaries"])
    serialized = response.text.lower()
    assert "history" not in serialized
    assert "hole_cards" not in serialized
    assert "deck" not in serialized


def test_dataset_schema_version_remains_2_0():
    assert SCHEMA_VERSION == "2.0"
