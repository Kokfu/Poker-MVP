"""Regression witnesses for the sparse-profile loss and bounded comparison."""
from itertools import product

import pytest

from research.holdem import phase_4w, phase_4x
from research.holdem.phase_4k import train
from research.holdem.river_adjustment import bounded_adjustment, lower_transfer
from research.holdem.river_ev import RiverState


def test_sparse_profile_shove_reply_substitution_reverses_preference():
    # The historical fixture is generated from the frozen Phase 4W schedule.
    case, stream, prefix, name = next(
        item for item in phase_4w.schedule("holdout")
        if (item[0].index, item[1], item[3]) == (5, 311, "tight_passive"))
    profile = train(name, stream, (prefix,))[prefix]
    recorded = phase_4w.holdout_row(case, stream, prefix, name, profile, False)
    row = phase_4x.case_diagnostic(case, stream, prefix, name, profile, recorded)
    assert row["delta"] == pytest.approx(-17.6899535014822)
    assert row["arms"]["B"]["range"]["omitted_opponent_mass"] < .00002
    assert row["cells"]["000"]["values"]["all_in"] > 0
    assert row["cells"]["001"]["values"]["all_in"] < -11
    assert row["cells"]["001"]["mix"] == {"fold": 1.}
    assert row["responses"]["all_in"]["model_fold_on_model"] > .63
    assert row["responses"]["all_in"]["truth_fold_on_model"] < .31


def test_bounded_adjustment_matches_exhaustive_terminal_extremes():
    state = RiverState(1501, 0, 500, 2600, 1700, 500, hero_gets_odd_chip=True)
    incumbent = {"fold": .3, "call": .2, "raise_1000": .5}
    repaired = {"fold": .15, "call": .05, "all_in": .8}
    # The all-in's 400-chip overhang is refunded when called.
    transfer = (
        ((-500,), (1501, -1000), (1501, -2200)),
        ((501,), (1501, 501), (1501, 501)),
        ((1501,), (1501, 2001), (1501, 3201)),
    )
    expected = min(-.15 * call - .5 * raise_value + .8 * shove
                   for outcome in transfer for call, raise_value, shove in product(*outcome))
    assert lower_transfer(state, incumbent, repaired) == pytest.approx(expected)
    mix, fraction, bound = bounded_adjustment(state, incumbent, repaired, 100)
    assert fraction < 1
    assert bound == pytest.approx(expected / 100)
    assert lower_transfer(state, incumbent, mix) == pytest.approx(-50.)
    assert sum(mix.values()) == pytest.approx(1.)


@pytest.mark.parametrize("state", [RiverState(1500, 0, 500, 2500, 0, 500),
                                   RiverState(1500, 0, 500, 500, 350, 500)])
def test_closing_candidate_preserves_incumbent_for_either_effective_cap(state):
    cover = "all_in" if state.hero_stack == state.villain_commit else "call"
    incumbent = {"fold": .2, cover: .8}
    assert bounded_adjustment(state, incumbent, {"fold": 1.}, 100) == (incumbent, 0., None)
