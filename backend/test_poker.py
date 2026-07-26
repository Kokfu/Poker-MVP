import pytest
from fastapi.testclient import TestClient

from main import app
from poker_analyzer import EVALUATOR, calculate_equity, detect_draws, pot_odds, recommendation

client = TestClient(app)
BASE = {"hero_cards": ["As", "Qs"], "board_cards": ["Js", "8s", "3d"], "opponents": 1, "pot": 100, "amount_to_call": 40, "hero_stack": 850, "iterations": 10000}


@pytest.mark.parametrize("board", [[], ["Js", "8s", "3d"], ["Js", "8s", "3d", "2c"], ["Js", "8s", "3d", "2c", "Kh"]])
def test_valid_board_lengths_are_accepted(board):
    response = client.post("/api/analyze", json={**BASE, "board_cards": board})
    assert response.status_code == 200


@pytest.mark.parametrize("board", [["Js"], ["Js", "8s"], ["Js", "8s", "3d", "2c", "Kh", "4h"]])
def test_invalid_board_lengths_are_rejected(board):
    assert client.post("/api/analyze", json={**BASE, "board_cards": board}).status_code == 422


@pytest.mark.parametrize("hero", [["Xs", "Qs"], ["1s", "Qs"]])
def test_invalid_card_ranks_are_rejected(hero):
    assert client.post("/api/analyze", json={**BASE, "hero_cards": hero}).status_code == 422


@pytest.mark.parametrize("hero", [["AX", "Qs"], ["As", "QH"]])
def test_invalid_card_suits_are_rejected(hero):
    assert client.post("/api/analyze", json={**BASE, "hero_cards": hero}).status_code == 422


def test_duplicate_cards_in_hero_are_rejected():
    assert client.post("/api/analyze", json={**BASE, "hero_cards": ["As", "As"]}).status_code == 422


def test_duplicate_cards_between_hero_and_board_are_rejected():
    assert client.post("/api/analyze", json={**BASE, "board_cards": ["As", "8s", "3d"]}).status_code == 422


@pytest.mark.parametrize("opponents", [0, 2, 3])
def test_invalid_opponent_counts_are_rejected(opponents):
    assert client.post("/api/analyze", json={**BASE, "opponents": opponents}).status_code == 422


@pytest.mark.parametrize("field", ["pot", "amount_to_call", "hero_stack"])
def test_negative_money_values_are_rejected(field):
    assert client.post("/api/analyze", json={**BASE, field: -1}).status_code == 422


@pytest.mark.parametrize("call", [850, 851])
def test_all_in_and_over_stack_calls_are_rejected(call):
    response = client.post("/api/analyze", json={**BASE, "amount_to_call": call})
    assert response.status_code == 422
    assert "All-in call scenarios" in response.json()["detail"][0]["msg"]


def test_pot_odds_formula_and_free_action():
    assert pot_odds(100, 40) == (140, pytest.approx(40 / 140))
    assert pot_odds(100, 0) == (100, 0.0)


def test_zero_amount_to_call_returns_check():
    result = client.post("/api/analyze", json={**BASE, "amount_to_call": 0}).json()
    assert result["required_equity"] == 0.0
    assert result["recommendation"] == "Check"


@pytest.mark.parametrize(("equity", "required", "expected"), [(.279, .30, "Fold"), (.280, .30, "Call"), (.399, .30, "Call"), (.400, .30, "Consider raising")])
def test_recommendation_thresholds(equity, required, expected):
    assert recommendation(equity, required, 10) == expected


def test_river_uses_exact_990_combinations():
    result = calculate_equity(["As", "Qs"], ["Js", "8s", "3d", "2c", "Kh"], 10000)
    assert result["calculation_method"] == "exact_enumeration"
    assert result["hands_checked"] == 990


@pytest.mark.parametrize("board", [[], ["Js", "8s", "3d"], ["Js", "8s", "3d", "2c"]])
def test_preflop_flop_turn_use_monte_carlo(board):
    assert calculate_equity(["As", "Qs"], board, 10000, seed=7)["calculation_method"] == "monte_carlo"


def test_monte_carlo_is_deterministic_and_rates_normalize():
    first = calculate_equity(["As", "Qs"], ["Js", "8s", "3d"], 10000, seed=7)
    second = calculate_equity(["As", "Qs"], ["Js", "8s", "3d"], 10000, seed=7)
    assert first == second
    assert first["equity"] == pytest.approx(first["win_rate"] + first["tie_rate"] / 2)
    assert sum(first[key] for key in ("win_rate", "tie_rate", "loss_rate")) == pytest.approx(1.0)


def test_monte_carlo_never_deals_known_or_duplicate_cards(monkeypatch):
    hero, board, observed = ["As", "Qs"], ["Js", "8s", "3d"], []
    real_score = EVALUATOR.score
    def capture_score(hole, final_board):
        observed.append((hole, final_board))
        return real_score(hole, final_board)
    monkeypatch.setattr(EVALUATOR, "score", capture_score)
    calculate_equity(hero, board, 10000, seed=12)
    assert len(observed) == 20000
    for index in range(0, len(observed), 2):
        hero_hole, final_board = observed[index]
        opponent_hole, opponent_board = observed[index + 1]
        assert hero_hole == hero and final_board == opponent_board
        all_cards = hero_hole + opponent_hole + final_board
        assert len(all_cards) == len(set(all_cards)) == 9


def test_preflop_skips_made_hand_evaluation(monkeypatch):
    monkeypatch.setattr(EVALUATOR, "category", lambda *_: pytest.fail("category should not run preflop"))
    result = client.post("/api/analyze", json={**BASE, "board_cards": []}).json()
    assert result["street"] == "Preflop" and result["made_hand"] is None


def test_pair_beats_high_card():
    assert EVALUATOR.score(["9s", "9d"], ["Qh", "Jc", "Tc", "2d", "3s"]) < EVALUATOR.score(["As", "Kd"], ["Qh", "Jc", "8c", "2d", "3s"])


def test_straight_beats_pair():
    assert EVALUATOR.score(["As", "Kd"], ["Qh", "Jc", "Tc", "2d", "3s"]) < EVALUATOR.score(["9s", "9d"], ["Qh", "Jc", "Tc", "2d", "3s"])


def test_flush_beats_straight():
    assert EVALUATOR.score(["As", "2s"], ["Ks", "Qs", "Js", "Tc", "9d"]) < EVALUATOR.score(["9s", "8d"], ["Qh", "Jc", "Tc", "7d", "6s"])


def test_full_house_beats_flush():
    assert EVALUATOR.score(["As", "Ad"], ["Ks", "Kd", "Kc", "2d", "3s"]) < EVALUATOR.score(["As", "2s"], ["Ks", "Qs", "Js", "Tc", "9d"])


def test_four_of_a_kind_beats_full_house():
    assert EVALUATOR.score(["As", "Ad"], ["Ac", "Ah", "Ks", "Kd", "2s"]) < EVALUATOR.score(["As", "Ad"], ["Ks", "Kd", "Kc", "2d", "3s"])


def test_hero_flush_draw_is_detected():
    assert any(draw["type"] == "flush_draw" for draw in detect_draws(["Ah", "Kd"], ["2h", "5h", "8h"]))


def test_board_only_flush_draw_is_not_personal():
    assert not any(draw["type"] == "flush_draw" for draw in detect_draws(["As", "Kd"], ["2h", "5h", "8h", "Jh"]))


def test_hero_open_ended_straight_draw_is_detected():
    draws = detect_draws(["6s", "Kd"], ["7h", "8d", "9c"])
    assert any(draw["type"] == "open_ended_straight_draw" for draw in draws)


def test_hero_gutshot_straight_draw_is_detected():
    draws = detect_draws(["7s", "Kd"], ["5h", "6d", "9c"])
    assert any(draw["type"] == "gutshot_straight_draw" for draw in draws)


def test_board_only_straight_draw_is_not_personal():
    draws = detect_draws(["As", "Kd"], ["5h", "6d", "7c", "8s"])
    assert not any("straight" in draw["type"] for draw in draws)


def test_river_has_no_draw_labels():
    assert detect_draws(["As", "Qs"], ["Js", "8s", "3d", "2c", "Kh"]) == []


def test_api_health_endpoint():
    assert client.get("/api/health").json() == {"status": "OK"}


def test_api_analyze_valid_request_has_expected_fields():
    response = client.post("/api/analyze", json=BASE)
    assert response.status_code == 200
    assert {"street", "equity", "recommendation", "calculation_method", "draws"} <= response.json().keys()


def test_api_analyze_invalid_request_returns_validation_error():
    assert client.post("/api/analyze", json={**BASE, "iterations": 1}).status_code == 422
