import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
HAND_REQUEST = {
    "bot_a": "tight",
    "bot_b": "aggressive",
    "starting_stack_a": 1000,
    "starting_stack_b": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "button_player": "a",
    "seed": 42,
    "equity_iterations": 500,
}
MATCH_REQUEST = {
    "bot_a": "tight",
    "bot_b": "aggressive",
    "starting_stack": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "max_hands": 3,
    "seed": 42,
    "equity_iterations": 500,
}
EXISTING_MATCH_FIELDS = {
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
EXISTING_HAND_SUMMARY_FIELDS = {
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


def post_hand(payload=None):
    return client.post(
        "/api/histories/hand",
        json=HAND_REQUEST if payload is None else payload,
    )


def post_match(payload=None):
    return client.post(
        "/api/histories/match",
        json=MATCH_REQUEST if payload is None else payload,
    )


def test_single_hand_history_endpoint_returns_200_and_required_fields():
    response = post_hand()
    assert response.status_code == 200
    document = response.json()
    assert set(document) == {
        "document_type",
        "history_schema_version",
        "history",
        "validation",
    }
    assert document["document_type"] == "hand_history"
    assert document["history_schema_version"] == "1.0"
    assert document["validation"]["valid"] is True
    assert document["validation"]["errors"] == []
    assert document["validation"]["warnings"] == []


def test_single_hand_defaults_match_contract():
    document = client.post("/api/histories/hand", json={}).json()
    history = document["history"]
    assert history["starting_stack_a"] == 10000
    assert history["starting_stack_b"] == 10000
    assert history["small_blind_amount"] == 50
    assert history["big_blind_amount"] == 100
    assert history["button_player"] == "a"
    assert history["hand_seed"] == 0


def test_same_hand_request_returns_identical_document():
    assert post_hand().json() == post_hand().json()


def test_different_hand_seed_can_change_card_history():
    first = post_hand(
        {**HAND_REQUEST, "bot_a": "random", "bot_b": "random", "seed": 1}
    ).json()["history"]
    second = post_hand(
        {**HAND_REQUEST, "bot_a": "random", "bot_b": "random", "seed": 3}
    ).json()["history"]
    assert first["final_board"] != second["final_board"]


def test_short_small_and_big_blinds_return_200():
    small = post_hand(
        {
            **HAND_REQUEST,
            "starting_stack_a": 3,
            "starting_stack_b": 100,
            "small_blind": 5,
            "big_blind": 10,
        }
    )
    big = post_hand(
        {
            **HAND_REQUEST,
            "starting_stack_a": 100,
            "starting_stack_b": 7,
            "small_blind": 5,
            "big_blind": 10,
        }
    )
    assert small.status_code == big.status_code == 200
    small_event = small.json()["history"]["events"][1]
    big_event = big.json()["history"]["events"][2]
    assert small_event["posted_amount"] == 3
    assert big_event["posted_amount"] == 7


@pytest.mark.parametrize("field", ["bot_a", "bot_b"])
def test_invalid_hand_bot_returns_422(field):
    assert post_hand({**HAND_REQUEST, field: "unsupported"}).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("starting_stack_a", 0),
        ("starting_stack_a", -1),
        ("starting_stack_b", 0),
        ("starting_stack_b", -1),
        ("small_blind", 0),
        ("big_blind", 0),
    ],
)
def test_invalid_hand_stack_and_blinds_return_422(field, value):
    assert post_hand({**HAND_REQUEST, field: value}).status_code == 422


def test_invalid_hand_blind_relationship_returns_422():
    assert (
        post_hand({**HAND_REQUEST, "small_blind": 11, "big_blind": 10}).status_code
        == 422
    )


@pytest.mark.parametrize("value", ["x", 1, None])
def test_invalid_button_returns_422(value):
    assert post_hand({**HAND_REQUEST, "button_player": value}).status_code == 422


@pytest.mark.parametrize("value", ["bad", 1.5, None, True])
def test_invalid_seed_returns_422(value):
    assert post_hand({**HAND_REQUEST, "seed": value}).status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "starting_stack_a",
        "starting_stack_b",
        "small_blind",
        "big_blind",
        "seed",
        "equity_iterations",
    ],
)
def test_boolean_numeric_inputs_return_422(field):
    assert post_hand({**HAND_REQUEST, field: True}).status_code == 422


def test_unsupported_equity_iterations_returns_422():
    assert (
        post_hand({**HAND_REQUEST, "equity_iterations": 501}).status_code == 422
    )


def test_malformed_hand_json_returns_422_not_500():
    response = client.post(
        "/api/histories/hand",
        content="{broken",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_match_history_endpoint_returns_one_history_per_hand():
    response = post_match()
    assert response.status_code == 200
    document = response.json()
    assert document["document_type"] == "match_history"
    assert document["history_count"] == document["match"]["hands_played"]
    assert len(document["histories"]) == document["history_count"]
    assert document["invalid_history_count"] == 0
    assert document["aggregate_validation"]["valid"] is True


def test_match_history_stack_continuity_and_position_alternation():
    histories = post_match().json()["histories"]
    for previous, current in zip(histories, histories[1:]):
        assert current["starting_stack_a"] == previous["final_stack_a"]
        assert current["starting_stack_b"] == previous["final_stack_b"]
        assert current["button_player"] != previous["button_player"]
        assert current["small_blind_player"] == current["button_player"]
        assert current["big_blind_player"] != current["button_player"]


def test_match_history_aggregate_conservation_and_zero_sum():
    document = post_match().json()
    match = document["match"]
    assert match["final_stack_a"] + match["final_stack_b"] == (
        match["starting_stack"] * 2
    )
    assert match["bot_a_net_chips"] + match["bot_b_net_chips"] == 0
    assert document["aggregate_illegal_action_count"] == match["illegal_actions"]
    assert document["aggregate_fallback_count"] == match["fallback_diagnostics"]


def test_invalid_match_history_request_returns_422():
    assert post_match({**MATCH_REQUEST, "max_hands": 0}).status_code == 422


def test_existing_match_endpoint_field_sets_are_exactly_unchanged():
    response = client.post("/api/matches/simulate", json=MATCH_REQUEST)
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == EXISTING_MATCH_FIELDS
    assert all(
        set(summary) == EXISTING_HAND_SUMMARY_FIELDS
        for summary in payload["hand_summaries"]
    )
    assert "history" not in response.text.lower()
    assert "hole_cards" not in response.text.lower()


def test_existing_analyzer_and_independent_simulation_remain_compatible():
    analyzer = client.post(
        "/api/analyze",
        json={
            "hero_cards": ["As", "Qs"],
            "board_cards": ["Js", "8s", "3d"],
            "opponents": 1,
            "pot": 100,
            "amount_to_call": 40,
            "hero_stack": 850,
            "iterations": 10000,
        },
    )
    simulation = client.post(
        "/api/simulations/run",
        json={
            "bot_a": "random",
            "bot_b": "tight",
            "hands": 3,
            "seed": 42,
            "starting_stack_bb": 100,
            "equity_iterations": 500,
        },
    )
    assert analyzer.status_code == simulation.status_code == 200
    assert {"equity", "recommendation"} <= analyzer.json().keys()
    assert simulation.json()["hands_played"] == 3
    assert "history" not in simulation.text.lower()


def test_serialized_api_documents_contain_no_forbidden_keys():
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

    scan(post_hand().json())
    scan(post_match().json())
