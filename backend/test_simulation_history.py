from dataclasses import asdict

import pytest

from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.bots import (
    AggressiveBot,
    EquityBot,
    RandomBot,
    TightBot,
)
from simulation.engine import HandEngine, SimulationRunner
from simulation.history import HISTORY_SCHEMA_VERSION, validate_hand_history
from simulation.match import MatchConfig, run_match


def events(history, event_type):
    return [event for event in history.events if event.event_type == event_type]


def fold_preflop(seed=100):
    engine = HandEngine(
        ScriptedBot([Action("fold")]),
        ScriptedBot([]),
        seed=seed,
        hand_id="fold-preflop",
    )
    return engine, engine.play()


def check_down(seed=101):
    engine = HandEngine(
        ScriptedBot(
            [Action("call"), Action("check"), Action("check"), Action("check")]
        ),
        ScriptedBot(
            [Action("check"), Action("check"), Action("check"), Action("check")]
        ),
        seed=seed,
        hand_id="check-down",
    )
    return engine, engine.play()


def postflop_fold(seed=102):
    engine = HandEngine(
        ScriptedBot([Action("call"), Action("fold")]),
        ScriptedBot([Action("check"), Action("bet", 100)]),
        seed=seed,
        hand_id="postflop-fold",
    )
    return engine, engine.play()


def test_fold_ended_preflop_history_and_exactly_one_settlement():
    engine, result = fold_preflop()
    history = result["history"]
    assert history.history_schema_version == HISTORY_SCHEMA_VERSION == "1.0"
    assert history.ending_type == "fold"
    assert history.showdown is False
    assert history.final_board == []
    assert len(events(history, "hand_started")) == 1
    assert len(events(history, "hand_settled")) == 1
    assert events(history, "hand_settled")[0] is history.events[-1]
    assert engine.settlement_count == 1
    assert validate_hand_history(history).valid


def test_postflop_fold_history_stops_board_at_flop():
    _, result = postflop_fold()
    history = result["history"]
    fold = [event for event in events(history, "action_taken") if event.applied_action == "fold"]
    assert len(fold) == 1
    assert fold[0].street == "flop"
    assert len(history.final_board) == 3
    assert not events(history, "showdown")
    assert validate_hand_history(history).valid


def test_check_check_progresses_every_street():
    _, result = check_down()
    history = result["history"]
    checks = [
        event for event in events(history, "action_taken")
        if event.applied_action == "check"
    ]
    assert len(checks) == 7
    assert {event.street for event in checks} == {
        "preflop",
        "flop",
        "turn",
        "river",
    }
    assert [event.street for event in events(history, "board_revealed")] == [
        "flop",
        "turn",
        "river",
    ]


def test_call_records_exact_payment_and_total_target():
    _, result = check_down()
    call = next(
        event for event in events(result["history"], "action_taken")
        if event.applied_action == "call"
    )
    assert call.amount_to_call_before == 50
    assert call.amount_paid == 50
    assert call.target_total == 100
    assert call.street_commitment_a_before == 50
    assert call.street_commitment_a_after == 100


def test_bet_and_raise_record_total_targets():
    engine = HandEngine(
        ScriptedBot([Action("call"), Action("raise", 300)]),
        ScriptedBot([Action("check"), Action("bet", 100), Action("fold")]),
        seed=103,
    )
    result = engine.play()
    actions = events(result["history"], "action_taken")
    bet = next(event for event in actions if event.applied_action == "bet")
    raise_event = next(
        event for event in actions if event.applied_action == "raise"
    )
    assert bet.target_total == 100
    assert bet.amount_paid == 100
    assert raise_event.target_total == 300
    assert raise_event.amount_paid == 300
    assert raise_event.last_full_raise_size_after == 200


def test_full_raise_reopens_action_in_history():
    engine = HandEngine(
        ScriptedBot([Action("raise", 200), Action("call")]),
        ScriptedBot([Action("all_in")]),
        starting_stacks={"a": 1000, "b": 500},
        seed=104,
    )
    result = engine.play()
    all_in = next(
        event for event in events(result["history"], "action_taken")
        if event.applied_action == "all_in"
    )
    assert all_in.all_in_classification == "full_raise"
    assert all_in.raising_reopened_after == {"a": True, "b": True}
    assert all_in.pending_players_after == ["a"]


def test_short_all_in_raise_does_not_reopen():
    engine = HandEngine(
        ScriptedBot([Action("raise", 300), Action("call")]),
        ScriptedBot([Action("all_in")]),
        starting_stacks={"a": 1000, "b": 350},
        seed=105,
    )
    result = engine.play()
    all_in = next(
        event for event in events(result["history"], "action_taken")
        if event.applied_action == "all_in"
    )
    assert all_in.target_total == 350
    assert all_in.all_in_classification == "short_raise"
    assert all_in.raising_reopened_after["a"] is False
    assert all_in.last_full_raise_size_before == all_in.last_full_raise_size_after


def test_exact_all_in_call_history():
    engine = HandEngine(
        ScriptedBot([Action("raise", 500)]),
        ScriptedBot([Action("all_in")]),
        starting_stacks={"a": 1000, "b": 500},
        seed=106,
    )
    result = engine.play()
    all_in = next(
        event for event in events(result["history"], "action_taken")
        if event.actor == "b"
    )
    assert all_in.target_total == 500
    assert all_in.amount_paid == 400
    assert all_in.all_in_classification == "exact_call"


def test_short_all_in_call_and_unmatched_excess_history():
    engine = HandEngine(
        ScriptedBot([Action("raise", 500)]),
        ScriptedBot([Action("all_in")]),
        starting_stacks={"a": 1000, "b": 300},
        seed=107,
    )
    result = engine.play()
    history = result["history"]
    all_in = next(
        event for event in events(history, "action_taken") if event.actor == "b"
    )
    returned = events(history, "unmatched_excess_returned")
    assert all_in.target_total == 300
    assert all_in.all_in_classification == "short_call"
    assert len(returned) == 1
    assert returned[0].returned_to == "a"
    assert returned[0].returned_amount == 200
    assert validate_hand_history(history).valid


def test_preflop_automatic_all_in_runout_reveals_each_street():
    engine = HandEngine(
        ScriptedBot([Action("all_in")]),
        ScriptedBot([Action("all_in")]),
        stack=1000,
        seed=108,
    )
    history = engine.play()["history"]
    assert len(events(history, "automatic_runout_started")) == 1
    reveals = events(history, "board_revealed")
    assert [len(event.new_cards) for event in reveals] == [3, 1, 1]
    assert [event.street for event in reveals] == ["flop", "turn", "river"]
    assert len(history.final_board) == 5


def test_postflop_automatic_all_in_runout():
    engine = HandEngine(
        ScriptedBot([Action("call"), Action("all_in")]),
        ScriptedBot([Action("check"), Action("all_in")]),
        stack=1000,
        seed=109,
    )
    history = engine.play()["history"]
    runout = events(history, "automatic_runout_started")
    assert len(runout) == 1
    assert runout[0].street == "flop"
    assert [event.street for event in events(history, "board_revealed")] == [
        "flop",
        "turn",
        "river",
    ]


def test_showdown_and_pot_award_history():
    _, result = check_down()
    history = result["history"]
    showdown = events(history, "showdown")
    award = events(history, "pot_awarded")
    assert len(showdown) == len(award) == 1
    assert set(showdown[0].revealed_hole_cards) == {"a", "b"}
    assert award[0].pot_before_award > 0
    assert award[0].awarded_to_a + award[0].awarded_to_b == award[0].pot_before_award


def test_tie_settlement_records_split_award():
    engine = HandEngine(
        ScriptedBot(
            [Action("call"), Action("check"), Action("check"), Action("check")]
        ),
        ScriptedBot(
            [Action("check"), Action("check"), Action("check"), Action("check")]
        ),
        seed=110,
    )
    engine.holes = {"a": ["As", "Kd"], "b": ["Qc", "Jh"]}
    engine.deck.cards = ["2h", "3d", "4c", "5s", "6h"]
    result = engine.play()
    award = events(result["history"], "pot_awarded")[0]
    assert result["winner"] is None
    assert result["history"].winner == "tied"
    assert award.winner == "tied"
    assert award.awarded_to_a == award.awarded_to_b == 100


def test_settlement_clears_pot_commitments_pending_and_actor():
    engine, result = postflop_fold()
    settled = events(result["history"], "hand_settled")[0]
    assert settled.pot_after == 0
    assert settled.street_commitment_a_after == 0
    assert settled.street_commitment_b_after == 0
    assert settled.commitments_cleared
    assert settled.pending_players_cleared
    assert settled.acting_player_cleared
    assert engine.state.acting_player is None


def test_every_event_connects_and_conserves_chips_without_negative_stacks():
    _, result = check_down()
    history = result["history"]
    total = history.starting_stack_a + history.starting_stack_b
    for prior, current in zip(history.events, history.events[1:]):
        assert prior.pot_after == current.pot_before
        assert prior.stack_a_after == current.stack_a_before
        assert prior.stack_b_after == current.stack_b_before
        assert (
            prior.street_commitment_a_after
            == current.street_commitment_a_before
        )
        assert (
            prior.street_commitment_b_after
            == current.street_commitment_b_before
        )
    for event in history.events:
        assert event.stack_a_before + event.stack_b_before + event.pot_before == total
        assert event.stack_a_after + event.stack_b_after + event.pot_after == total
        assert min(event.stack_a_before, event.stack_a_after) >= 0
        assert min(event.stack_b_before, event.stack_b_after) >= 0


def test_event_indexes_are_zero_based_and_contiguous():
    _, result = check_down()
    assert [event.event_index for event in result["history"].events] == list(
        range(len(result["history"].events))
    )


def test_same_seed_and_configuration_produce_same_history():
    first = check_down(seed=111)[1]["history"]
    second = check_down(seed=111)[1]["history"]
    assert asdict(first) == asdict(second)


def test_different_seeds_can_change_public_card_history():
    first = check_down(seed=112)[1]["history"]
    second = check_down(seed=113)[1]["history"]
    assert first.final_board != second.final_board


def test_match_histories_carry_stacks_and_alternate_positions():
    result = run_match(
        RandomBot(1),
        TightBot(2),
        MatchConfig(max_hands=4, seed=114),
    )
    assert all(summary.history is not None for summary in result.per_hand_summaries)
    for previous, current in zip(
        result.per_hand_summaries, result.per_hand_summaries[1:]
    ):
        assert current.starting_stacks == previous.ending_stacks
        assert current.history.starting_stack_a == current.starting_stacks["a"]
        assert current.history.starting_stack_b == current.starting_stacks["b"]
        assert current.history.button_player != previous.history.button_player
        assert current.history.small_blind_player == current.history.button_player
        assert current.history.big_blind_player != current.history.button_player
        assert validate_hand_history(current.history).valid


def test_short_stacked_small_blind_history():
    engine = HandEngine(
        ScriptedBot([]),
        ScriptedBot([]),
        starting_stacks={"a": 30, "b": 1000},
        small_blind=50,
        bb=100,
        seed=115,
    )
    history = engine.play()["history"]
    small_blind = events(history, "blind_posted")[0]
    assert small_blind.blind_type == "small_blind"
    assert small_blind.assigned_amount == 50
    assert small_blind.posted_amount == 30
    assert small_blind.stack_a_after == 0
    assert small_blind.post_was_all_in is True
    assert validate_hand_history(history).valid


def test_short_stacked_big_blind_history():
    engine = HandEngine(
        ScriptedBot([Action("call")]),
        ScriptedBot([]),
        starting_stacks={"a": 1000, "b": 70},
        small_blind=50,
        bb=100,
        seed=116,
    )
    history = engine.play()["history"]
    big_blind = events(history, "blind_posted")[1]
    assert big_blind.blind_type == "big_blind"
    assert big_blind.assigned_amount == 100
    assert big_blind.posted_amount == 70
    assert big_blind.stack_b_after == 0
    assert big_blind.post_was_all_in is True
    assert validate_hand_history(history).valid


def test_independent_simulation_remains_compatible():
    output = SimulationRunner(
        RandomBot(1), RandomBot(2), hands=5, seed=117
    ).run(include_hand_results=True)
    assert output["hands_played"] == 5
    assert len(output["hand_results"]) == 5
    assert output["bot_a_net_chips"] + output["bot_b_net_chips"] == 0


@pytest.mark.parametrize(
    "bot_class",
    [RandomBot, TightBot, AggressiveBot, EquityBot],
)
def test_each_builtin_bot_produces_valid_history(bot_class):
    engine = HandEngine(
        bot_class(seed=118, equity_iterations=100),
        RandomBot(seed=119),
        seed=120,
    )
    history = engine.play()["history"]
    validation = validate_hand_history(history)
    assert validation.valid, validation.errors
