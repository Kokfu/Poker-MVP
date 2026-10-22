import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
BASE = {
    "bot_a": "tight",
    "bot_b": "aggressive",
    "starting_stack": 1000,
    "small_blind": 5,
    "big_blind": 10,
    "max_hands": 3,
    "seed": 42,
    "equity_iterations": 500,
}
TOP_LEVEL_FIELDS = {
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
HAND_FIELDS = {
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


def post(payload=None):
    return client.post(
        "/api/matches/simulate",
        json=BASE if payload is None else payload,
    )


def test_valid_deterministic_match_returns_200():
    response = post()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_response_contains_every_required_top_level_field():
    assert TOP_LEVEL_FIELDS <= post().json().keys()


def test_hand_summaries_contain_every_required_field_and_no_private_cards():
    summaries = post().json()["hand_summaries"]
    assert summaries
    assert all(HAND_FIELDS <= hand.keys() for hand in summaries)
    assert all(
        "hole_cards" not in hand
        and "opponent_cards" not in hand
        and "opponent_hole_cards" not in hand
        for hand in summaries
    )


def test_same_request_and_seed_produce_the_same_poker_result():
    first = post().json()
    second = post().json()
    first.pop("match_id")
    second.pop("match_id")
    assert first == second


def test_api_result_conserves_chips_and_has_opposite_nets():
    result = post().json()
    assert result["final_stack_a"] + result["final_stack_b"] == 2000
    assert result["bot_a_net_chips"] == -result["bot_b_net_chips"]
    assert result["bot_a_net_chips"] + result["bot_b_net_chips"] == 0


def test_api_hand_and_aggregate_invariants():
    result = post().json()
    hands = result["hand_summaries"]
    assert result["hands_played"] <= result["max_hands"]
    assert len(hands) == result["hands_played"]
    assert result["showdowns"] + result["fold_ended_hands"] == result[
        "hands_played"
    ]
    assert result["illegal_actions"] == sum(
        hand["illegal_actions"] for hand in hands
    )
    assert result["fallback_diagnostics"] == sum(
        len(hand["fallback_diagnostics"]) for hand in hands
    )
    assert all(hand["settlement_complete"] for hand in hands)
    assert all(
        min(
            hand["starting_stack_a"],
            hand["starting_stack_b"],
            hand["ending_stack_a"],
            hand["ending_stack_b"],
        )
        >= 0
        for hand in hands
    )


def test_hand_limit_termination_is_represented_correctly():
    result = post({**BASE, "max_hands": 1}).json()
    assert result["termination_reason"] == "hand_limit"
    assert result["hands_played"] == 1


def test_elimination_termination_is_represented_correctly():
    result = post(
        {
            **BASE,
            "bot_a": "random",
            "bot_b": "random",
            "starting_stack": 1,
            "small_blind": 1,
            "big_blind": 1,
            "max_hands": 10,
            "seed": 0,
        }
    ).json()
    assert result["termination_reason"] == "elimination"
    assert 0 in (result["final_stack_a"], result["final_stack_b"])
    assert result["hands_played"] <= 10


def test_initial_stack_below_blinds_is_safe():
    response = post(
        {
            **BASE,
            "starting_stack": 25,
            "small_blind": 50,
            "big_blind": 100,
            "max_hands": 1,
        }
    )
    assert response.status_code == 200
    result = response.json()
    assert result["final_stack_a"] + result["final_stack_b"] == 50
    assert min(result["final_stack_a"], result["final_stack_b"]) >= 0
    assert all(
        hand["settlement_complete"] for hand in result["hand_summaries"]
    )


def test_bot_names_are_case_normalized():
    response = post({**BASE, "bot_a": "TiGhT", "bot_b": "AGGRESSIVE"})
    assert response.status_code == 200
    assert response.json()["bot_a"] == "TightBot"
    assert response.json()["bot_b"] == "AggressiveBot"


def test_unknown_fields_follow_existing_ignore_policy():
    response = post({**BASE, "future_option": "ignored"})
    assert response.status_code == 200


@pytest.mark.parametrize("field", ["bot_a", "bot_b"])
def test_unsupported_bot_returns_422(field):
    response = post({**BASE, field: "unsupported"})
    assert response.status_code == 422
    assert "input" in response.text.lower()


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_starting_stack_returns_422(value):
    assert post({**BASE, "starting_stack": value}).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("small_blind", 0),
        ("small_blind", -1),
        ("big_blind", 0),
        ("big_blind", -1),
    ],
)
def test_invalid_blinds_return_422(field, value):
    assert post({**BASE, field: value}).status_code == 422


def test_small_blind_greater_than_big_blind_returns_422():
    response = post({**BASE, "small_blind": 11, "big_blind": 10})
    assert response.status_code == 422
    assert "small blind" in response.text.lower()


@pytest.mark.parametrize("value", [0, 10_001])
def test_invalid_hand_limits_return_422(value):
    assert post({**BASE, "max_hands": value}).status_code == 422


@pytest.mark.parametrize("value", [1, 499, 501, 2001])
def test_invalid_equity_iterations_return_422(value):
    response = post({**BASE, "equity_iterations": value})
    assert response.status_code == 422
    assert "equity iterations" in response.text.lower()


@pytest.mark.parametrize("value", ["bad", 3.5, None])
def test_invalid_seed_returns_422(value):
    assert post({**BASE, "seed": value}).status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "starting_stack",
        "small_blind",
        "big_blind",
        "max_hands",
        "seed",
        "equity_iterations",
    ],
)
def test_boolean_values_are_not_accepted_as_integers(field):
    assert post({**BASE, field: True}).status_code == 422


def test_malformed_json_returns_useful_422_not_500():
    response = client.post(
        "/api/matches/simulate",
        content="{broken",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


def test_existing_independent_simulation_endpoint_is_unchanged():
    response = client.post(
        "/api/simulations/run",
        json={
            "bot_a": "random",
            "bot_b": "tight",
            "hands": 5,
            "seed": 42,
            "starting_stack_bb": 100,
            "equity_iterations": 500,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["hands_played"] == 5
    assert result["bot_a_net_chips"] + result["bot_b_net_chips"] == 0
    assert "match_id" not in result


def test_existing_analyzer_endpoint_remains_compatible():
    response = client.post(
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
    assert response.status_code == 200
    assert {"equity", "recommendation"} <= response.json().keys()
