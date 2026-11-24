from dataclasses import replace
from math import fsum

import pytest

from coach.service import Spot, SpotAction, hand_result
from research.holdem.river_ev import ExactRiverEV, RiverState
from simulation.actions import Action


FLUSH_BOARD = ("As", "Ks", "Qs", "Js", "2d")
HERO = ("9s", "3c")


def test_river_counts_and_card_removal():
    exact = ExactRiverEV(HERO, FLUSH_BOARD, lambda *_: 1)
    assert len(exact.holdings) == 990
    assert sum(hand.result == -1 for hand in exact.holdings) == 44
    assert all("Ts" in hand.combo for hand in exact.holdings if hand.result == -1)
    assert all(not set(hand.combo).intersection(HERO + FLUSH_BOARD) for hand in exact.holdings)
    assert fsum(hand.weight for hand in exact.holdings) == 1
    state = RiverState(750, 0, 250, 750, 0, 250)
    assert exact.action_ev(state, Action("call")) == pytest.approx(946 / 990 * 1000 - 250)
    assert exact.action_ev(state, Action("fold")) == 0
    blocked = ExactRiverEV(("Ts", "3c"), FLUSH_BOARD, lambda *_: 1)
    assert blocked.equity == 1


def test_river_weighted_raise_prices_and_eff_stack():
    # Only two holdings have mass, winning 3/4 and losing 1/4. The loser calls
    # with probability 1; the weaker holding calls with probability 1/2.
    weights = {frozenset(("Ts", "4d")): 1, frozenset(("6c", "6d")): 3}
    exact = ExactRiverEV(HERO, FLUSH_BOARD, lambda hand, _: weights.get(frozenset(hand), 0))
    state = RiverState(800, 100, 200, 900, 350, 100)

    def response(combo, _, price, pot_before_call):
        assert (price, pot_before_call) == (200, 1100)
        return 1 if "Ts" in combo else 0.5

    # Final pot 1300, Hero pays 300. Win +1000, loss -300, fold by Villain +800.
    assert exact.action_ev(state, Action("raise", 400), response) == 600
    # Open shove only matches 550 total. Hero pays 450, Villain adds 350,
    # and 450 excess is returned. Full pot is 1600.
    assert exact.action_ev(state, Action("all_in"), lambda *args: 1) == 750
    assert exact.action_ev(state, Action("raise", 400), lambda *args: 0) == 800


@pytest.mark.parametrize("villain_action,hero_action,reply", [
    ("check", "check", None),
    ("check", "bet", "call"),
    ("check", "all_in", "all_in"),
    ("check", "all_in", "fold"),
    ("all_in", "all_in", None),
])
def test_river_engine_settlement_with_board_royal(villain_action, hero_action, reply):
    opening = [SpotAction("hero", "raise", 250), SpotAction("villain", "call")]
    checks = [SpotAction("villain", "check"), SpotAction("hero", "check")] * 2
    stacks = (650, 850) if villain_action == "all_in" else (850, 650)
    hero, board = ("2d", "3c"), (*FLUSH_BOARD[:4], "Ts")
    target = 300 if hero_action == "bet" else None
    actions = opening + checks + [SpotAction("villain", villain_action), SpotAction("hero", hero_action, target)]
    if reply:
        actions.append(SpotAction("villain", reply))
    spot = Spot(hero_cards=list(hero), board=list(board), villain_cards=["4c", "5d"],
                hero_stack=stacks[0], villain_stack=stacks[1], actions=actions)
    state = (RiverState(500, 0, 0, 600, 400, 100, checked_to=True) if villain_action == "check"
             else RiverState(1100, 0, 600, 400, 0, 600))
    exact = ExactRiverEV(hero, board, lambda *_: 1)
    assert exact.equity == 0.5
    assert exact.action_ev(state, Action(hero_action, target), lambda *_: float(reply != "fold")) == pytest.approx(
        hand_result(spot)["hero_net"] + 250, abs=1e-10, rel=0
    )


def test_river_rejects_illegal_or_unspecified_branches_and_masses():
    state = RiverState(500, 0, 0, 500, 500, 100, checked_to=True)
    exact = ExactRiverEV(HERO, FLUSH_BOARD, lambda *_: 1)
    for action in (Action("fold"), Action("call"), Action("bet", 99), Action("bet", 501),
                   Action("raise", 200), Action("all_in", 500)):
        with pytest.raises(ValueError, match="illegal|explicit"):
            exact.action_ev(state, action)
    with pytest.raises(ValueError, match="continuation"):
        exact.action_ev(replace(state, checked_to=False), Action("check"))
    with pytest.raises(ValueError, match="explicit Villain response"):
        exact.action_ev(state, Action("bet", 100))
    with pytest.raises(ValueError, match="call probability"):
        exact.action_ev(state, Action("bet", 100), lambda *_: float("nan"))
    for weight in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="range"):
            ExactRiverEV(HERO, FLUSH_BOARD, lambda *_: weight)
    with pytest.raises(ValueError, match="distinct"):
        ExactRiverEV(("As", "3c"), FLUSH_BOARD, lambda *_: 1)
