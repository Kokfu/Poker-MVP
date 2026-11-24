import math

import pytest

from coach.service import Spot, SpotAction, _replay
from simulation.bots import BOT_TYPES, OPT_IN_BOTS
from solver.bot import _size_bracket


def test_between_sizes_blend_across_nearest_neighbour_boundary():
    actions = (("check", None), ("bet", 250), ("bet", 500), ("all_in", 9500))
    left, right, before = _size_bracket(actions, "bet", 353)
    assert (left, right) == (1, 2)
    _, _, after = _size_bracket(actions, "bet", 354)
    assert before < .5 < after
    assert after - before == pytest.approx(math.log(354 / 353) / math.log(2))
    for kind, amount in [("bet", 250), ("bet", 500), ("bet", 501), ("all_in", 9500), ("check", None)]:
        assert _size_bracket(actions, kind, amount) is None


def test_opt_in_advisor_blends_only_between_sizes_and_responds_legally():
    incumbent = BOT_TYPES["solver_adaptive"](seed=2)
    candidate = OPT_IN_BOTS["solver_adaptive_interpolated"](seed=2)
    assert not incumbent.interpolate_sizes and candidate.interpolate_sizes
    for amount in (250, 353):
        spot = Spot(hero_cards=["Jc", "9d"], hero_position="big_blind", board=["Qh", "7s", "2d"],
                    actions=[SpotAction("villain", "raise", 250), SpotAction("hero", "call"),
                             SpotAction("hero", "check"), SpotAction("villain", "bet", amount)])
        base = _replay(spot, advisor=incumbent)[1]
        status, varied, engine = _replay(spot, advisor=candidate)
        assert status == "hero_to_act"
        legal = engine.observe("a")
        assert varied["advice"]["action"] in legal.legal_actions
        amount_to = varied["advice"]["amount"]
        if amount_to is not None:
            assert legal.minimum_target_to <= amount_to <= legal.maximum_target_to
        assert candidate.fallback_count == incumbent.fallback_count == 0
        assert base["explanation"]["resolved_from_current_state"] == (amount == 353)
        assert (base["explanation"]["villain_effective_combos"] ==
                varied["explanation"]["villain_effective_combos"]) == (amount == 250)
