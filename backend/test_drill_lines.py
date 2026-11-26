import pytest

from drill_lines import LINES
from drill_spots import classify, has_three_bet, make_spot, simulate_line


@pytest.mark.parametrize("category,index", [(name, index) for name, lines in LINES.items() for index in range(len(lines))])
def test_all_action_lines_end_at_a_legal_hero_decision(category, index):
    button, steps = LINES[category][index]
    observation, history = simulate_line(button, steps, seed=54, stack=5000)
    state = observation.decision_state
    assert state.acting_player == "a"
    assert state.legal_actions and state.hero_stack > 0
    assert len(history) == len(steps)
    assert len(set(state.hole_cards + state.board_cards)) == len(state.hole_cards) + len(state.board_cards)
    public = [(item["street"], item["actor"], item["action"]) for item in history]
    assert classify(state.street, public, state.amount_to_call,
                    can_bluff=category == "river_bluff",
                    can_three_bet=category == "preflop_three_bet") == category


def test_three_bet_category_contains_initiation_and_response():
    respond, _ = make_spot("preflop_three_bet", 41, line_index=0)
    assert [action["actor"] for action in respond["history"]] == ["hero", "villain"]

    # Search a fixed set of simulated deals for a real chart-supported 3-bet.
    for seed in range(64):
        candidate = make_spot("preflop_three_bet", seed, line_index=1)
        if candidate is not None:
            break
    else:
        pytest.fail("the preflop chart supplied no 3-bet in the selected deals")
    spot, advice = candidate
    assert spot["position"] == "big_blind"
    assert [action["actor"] for action in spot["history"]] == ["villain"]
    assert has_three_bet(advice["options"])
    assert make_spot("preflop_defend", seed, line_index=0) is None
