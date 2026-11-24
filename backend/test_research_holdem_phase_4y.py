from types import SimpleNamespace

import numpy as np
import pytest

from research.holdem.phase_4k import STYLES
from research.holdem.phase_4m import oracle_response
from research.holdem.phase_4y import action_risk, Field, grid_scores, grouped, wager_category
from research.holdem.reply_forecast import ResponseAssumptions, forecast, reply_geometry
from research.holdem.river_ev import ExactRiverEV
from solver.tree import POSTFLOP_MENU, StreetState, StreetTree


def test_bounded_policy_can_draw_a_severely_harmful_action():
    incumbent = {"mix": {"fold": 1.}, "action": "fold"}
    candidate = {"mix": {"fold": .98, "all_in": .02}, "action": "all_in"}
    result = action_risk(candidate, {"fold": 0., "all_in": -20.}, incumbent)
    assert result["ev"] == pytest.approx(-.4)
    assert result["modal"] == "fold"
    assert result["selected_delta"] == -20.
    assert result["selected_regret"] == 20.
    assert result["harmful_mass"] == .02


def test_short_reply_has_zero_raise_mass_and_refunds_uncollectible_chips():
    tree = StreetTree(StreetState("river", 1, (600, 0), (0, 300), (200, 200), 600,
                                  acted=(True, False)), POSTFLOP_MENU)
    node = tree.nodes[tree.root]
    geometry = reply_geometry(node.state)
    assert (geometry.cost, geometry.refundable, geometry.pot_before_call) == (300, 300, 700)
    assert wager_category(node) == "closing_shove"
    assert node.labels == ["fold", "call"]
    assert tree.nodes[node.children[1]].contribution == (500, 500)
    probabilities = forecast(node, np.array([0, 1, 2]), ResponseAssumptions.from_counts(0, 0, 0))
    np.testing.assert_array_equal(grouped(node, probabilities)[2], [0, 0, 0])
    assert probabilities[1, 0] < probabilities[1, 1] < probabilities[1, 2]
    with pytest.raises(AssertionError, match="invalid concrete reply law"):
        grouped(node, probabilities * .99)


def test_exact_price_grid_has_legal_reraises_and_independent_transfers():
    hero = ("Ah", "Ad")
    board = ("As", "Ks", "2s", "3d", "8c")
    case = SimpleNamespace(hero=hero, board=board, pot=400)
    ds = SimpleNamespace(board_cards=board, acting_player="a")
    style = STYLES["loose_aggressive"]
    field = Field(ExactRiverEV(hero, board, lambda *_: 1))
    rows = grid_scores(case, ds, field, style, (0, 0, 0))
    assert {row["category"] for row in rows} == {"small", "medium", "pot", "overbet", "closing_shove"}
    by_cost = {row["geometry"]["cost"]: row for row in rows if row["geometry"]["effective_stack"] == 1200}
    assert {100, 200, 400, 600, 1200} == set(by_cost)
    assert by_cost[100]["predicted"][1] > by_cost[200]["predicted"][1]
    assert by_cost[400]["truth"][2] > by_cost[600]["truth"][2] > by_cost[1200]["truth"][2] == 0
    for row in rows:
        assert sum(row["predicted"]) == pytest.approx(1.)
        assert sum(row["truth"]) == pytest.approx(1.)


def test_closing_call_is_a_hero_action_with_no_future_reply():
    from research.holdem.river_ev import RiverState
    from simulation.actions import Action

    exact = ExactRiverEV(("Ah", "Ad"), ("As", "Ks", "2s", "3d", "8c"),
                         lambda combo, _: float(set(combo) == {"Qd", "Qc"}))
    state = RiverState(1000, 0, 600, 300, 0, 600, raising_reopened=False)
    action = Action("all_in")
    assert state.branch(action) == (300, 600, False)
    assert exact.action_ev(state, action) == pytest.approx(700.)
