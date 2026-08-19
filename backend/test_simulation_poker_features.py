import json

import pytest

from simulation.bots import RandomBot
from simulation.decision_state import build_decision_observation
from simulation.engine import HandEngine


def observed(hole, board, pot=600, call=300):
    game = HandEngine(RandomBot(), RandomBot(), stack=5_000, bb=100, seed=1)
    game.holes["a"] = hole
    game.state.community_cards = board
    game.state.street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)]
    game.state.pot = pot; game.state.current_bets = {"a": 0, "b": call}; game.state.current_highest_bet = call
    return build_decision_observation(game, "a").poker_features


def test_core_pot_features_and_zero_division_are_finite():
    features = observed(["Ah", "Qh"], ["Jh", "8h", "2c"])
    assert features.pot_odds == features.required_equity == pytest.approx(1 / 3)
    assert features.stack_to_pot_ratio == pytest.approx(4_900 / 600)
    assert features.bet_faced_fraction_of_pot == pytest.approx(.5)
    free = observed(["Ah", "Qh"], [], pot=0, call=0)
    assert free.pot_odds == free.required_equity == free.stack_to_pot_ratio == free.bet_faced_fraction_of_pot == 0
    assert json.dumps(free.as_dict(), allow_nan=False)


@pytest.mark.parametrize(("hole", "board", "expected"), [
    (["Ah", "Kd"], ["As", "7c", "2h"], "pair"),
    (["Ah", "Kd"], ["As", "Kc", "2h"], "two_pair"),
    (["Ah", "Ad"], ["As", "7c", "2h"], "three_of_a_kind"),
    (["9h", "8d"], ["7s", "6c", "5h"], "straight"),
    (["Ah", "9h"], ["7h", "6h", "2h"], "flush"),
    (["Ah", "Ad"], ["As", "Kc", "Kd"], "full_house"),
    (["Ah", "Ad"], ["As", "Ac", "2h"], "four_of_a_kind"),
    (["Ah", "Kh"], ["Qh", "Jh", "Th"], "straight_flush"),
])
def test_made_hand_categories(hole, board, expected):
    assert observed(hole, board).made_hand == expected


def test_draws_and_pair_draw_combinations():
    flush = observed(["Ah", "Qh"], ["Jh", "8h", "2c"])
    assert flush.flush_draw and not flush.open_ended_straight_draw and not flush.gutshot
    oesd = observed(["9h", "8d"], ["7s", "6c", "2h"])
    assert oesd.open_ended_straight_draw
    gutshot = observed(["9h", "7d"], ["6s", "5c", "2h"])
    assert gutshot.gutshot
    combo = observed(["Ah", "Qh"], ["Ad", "Jh", "8h"])
    assert combo.pair_plus_draw and not combo.overcards


def test_board_texture_categories_are_deterministic():
    paired = observed(["Ah", "Kd"], ["Js", "Jc", "2h"])
    assert paired.paired_board and paired.rainbow_board and paired.connected_board is False
    monotone = observed(["Ah", "Kd"], ["Js", "8s", "2s"])
    assert monotone.monotone_board and not monotone.rainbow_board
    rainbow = observed(["Ah", "Kd"], ["Js", "8h", "2c"])
    assert rainbow.rainbow_board and rainbow.board_distinct_suits == 3 and rainbow.board_high_card_rank == "J"
