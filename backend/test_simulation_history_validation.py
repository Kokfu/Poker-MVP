from copy import deepcopy
from dataclasses import replace

from scripted_test_support import ScriptedBot
from simulation.actions import Action
from simulation.engine import HandEngine
from simulation.history import validate_hand_history


def valid_history():
    engine = HandEngine(
        ScriptedBot(
            [Action("call"), Action("check"), Action("check"), Action("check")]
        ),
        ScriptedBot(
            [Action("check"), Action("check"), Action("check"), Action("check")]
        ),
        seed=200,
        hand_id="validator-hand",
    )
    return engine.play()["history"]


def error_text(history):
    validation = validate_hand_history(history)
    assert validation.valid is False
    return " | ".join(validation.errors)


def test_validator_accepts_complete_history():
    validation = validate_hand_history(valid_history())
    assert validation.valid
    assert validation.errors == []


def test_validator_rejects_unsupported_schema_version():
    history = valid_history()
    history.history_schema_version = "2.0"
    assert "unsupported history schema" in error_text(history)


def test_validator_rejects_missing_event_index():
    history = valid_history()
    history.events[1] = replace(history.events[1], event_index=None)
    assert "event indexes" in error_text(history)


def test_validator_rejects_reordered_events():
    history = valid_history()
    history.events[1], history.events[2] = history.events[2], history.events[1]
    assert "event indexes" in error_text(history)


def test_validator_rejects_duplicate_board_cards():
    history = valid_history()
    flop_index = next(
        index
        for index, event in enumerate(history.events)
        if event.event_type == "board_revealed" and event.street == "flop"
    )
    flop = history.events[flop_index]
    duplicate_board = [flop.board[0], flop.board[0], flop.board[2]]
    history.events[flop_index] = replace(
        flop,
        board=duplicate_board,
        new_cards=duplicate_board,
    )
    assert "duplicate card" in error_text(history)


def test_validator_rejects_broken_chip_conservation():
    history = valid_history()
    event = history.events[3]
    history.events[3] = replace(
        event,
        stack_a_after=event.stack_a_after + 1,
    )
    assert "chip conservation" in error_text(history)


def test_validator_rejects_disconnected_before_after_values():
    history = valid_history()
    event = history.events[4]
    history.events[4] = replace(
        event,
        pot_before=event.pot_before + 1,
        stack_a_before=event.stack_a_before - 1,
    )
    assert "does not connect" in error_text(history)


def test_validator_rejects_events_after_settlement():
    history = valid_history()
    final = history.events[-1]
    history.events.append(
        replace(
            final,
            event_index=len(history.events),
            event_type="street_started",
            settlement_complete=False,
        )
    )
    assert "after hand_settled" in error_text(history)


def test_validator_rejects_mismatched_final_stack():
    history = valid_history()
    history.final_stack_a += 1
    assert "final stack A" in error_text(history)


def test_validator_rejects_mismatched_final_board():
    history = valid_history()
    history.final_board = history.final_board[:-1]
    assert "final history board" in error_text(history)


def test_validator_rejects_mismatched_winner_and_ending():
    history = valid_history()
    history.winner = "tied" if history.winner != "tied" else "a"
    history.ending_type = "fold"
    errors = error_text(history)
    assert "winner does not match" in errors
    assert "ending type does not match" in errors


def test_validator_rejects_board_growth_outside_reveal_event():
    history = valid_history()
    street = next(
        event
        for event in history.events
        if event.event_type == "street_started" and event.street == "flop"
    )
    index = street.event_index
    history.events[index] = replace(street, board=["As"])
    assert "grows board outside board_revealed" in error_text(history)


def test_validator_rejects_invalid_flop_reveal_count():
    history = valid_history()
    index = next(
        event.event_index
        for event in history.events
        if event.event_type == "board_revealed" and event.street == "flop"
    )
    event = history.events[index]
    history.events[index] = replace(
        event,
        board=event.board[:2],
        new_cards=event.new_cards[:2],
    )
    assert "invalid flop card count" in error_text(history)


def test_validator_rejects_action_missing_required_fields():
    history = valid_history()
    index = next(
        event.event_index
        for event in history.events
        if event.event_type == "action_taken"
    )
    history.events[index] = replace(
        history.events[index],
        actor=None,
        amount_paid=None,
        all_in_classification=None,
    )
    errors = error_text(history)
    assert "missing actor" in errors
    assert "missing applied action/payment" in errors
    assert "lacks all-in classification" in errors


def test_validator_rejects_total_target_mismatch():
    history = valid_history()
    index = next(
        event.event_index
        for event in history.events
        if event.event_type == "action_taken"
        and event.applied_action == "call"
    )
    history.events[index] = replace(
        history.events[index],
        target_total=999,
    )
    errors = error_text(history)
    assert "target total differs" in errors
    assert "payment differs from target" in errors


def test_validator_rejects_incomplete_final_cleanup():
    history = valid_history()
    final = history.events[-1]
    history.events[-1] = replace(
        final,
        commitments_cleared=False,
        settlement_complete=False,
    )
    errors = error_text(history)
    assert "must be settlement complete" in errors
    assert "cleanup flags" in errors


def test_validator_returns_independent_useful_error_list():
    history = deepcopy(valid_history())
    history.history_schema_version = "bad"
    history.final_stack_b += 1
    validation = validate_hand_history(history)
    assert not validation.valid
    assert len(validation.errors) >= 2
    assert all(isinstance(error, str) and error for error in validation.errors)
