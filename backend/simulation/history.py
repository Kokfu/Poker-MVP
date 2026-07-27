"""Typed, deterministic, internal hand-history records and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


HISTORY_SCHEMA_VERSION = "1.0"

Player = Literal["a", "b"]
HistoryWinner = Literal["a", "b", "tied"]
EndingType = Literal["fold", "showdown"]
HandHistoryEventType = Literal[
    "hand_started",
    "blind_posted",
    "action_taken",
    "street_started",
    "board_revealed",
    "unmatched_excess_returned",
    "automatic_runout_started",
    "showdown",
    "pot_awarded",
    "hand_settled",
]
AllInClassification = Literal[
    "exact_call",
    "short_call",
    "short_raise",
    "full_raise",
    "non_raising_all_in",
    "not_applicable",
]


@dataclass(frozen=True)
class PlayerSnapshot:
    stack_a: int
    stack_b: int


@dataclass(frozen=True)
class BettingSnapshot:
    pot: int
    street_commitment_a: int
    street_commitment_b: int
    current_highest_bet: int


@dataclass(frozen=True)
class HandHistoryEvent:
    event_index: int
    event_type: HandHistoryEventType
    street: str
    actor: Player | None
    board: list[str]
    pot_before: int
    pot_after: int
    stack_a_before: int
    stack_a_after: int
    stack_b_before: int
    stack_b_after: int
    street_commitment_a_before: int
    street_commitment_a_after: int
    street_commitment_b_before: int
    street_commitment_b_after: int
    current_highest_bet_before: int
    current_highest_bet_after: int
    settlement_complete: bool

    blind_type: Literal["small_blind", "big_blind"] | None = None
    assigned_amount: int | None = None
    posted_amount: int | None = None
    post_was_all_in: bool | None = None

    requested_action: str | None = None
    requested_target_total: int | None = None
    applied_action: str | None = None
    legal_actions: list[str] | None = None
    fallback_used: bool | None = None
    fallback_reason: str | None = None
    amount_to_call_before: int | None = None
    amount_paid: int | None = None
    target_total: int | None = None
    minimum_legal_target: int | None = None
    maximum_legal_target: int | None = None
    action_classification: str | None = None
    all_in_classification: AllInClassification | None = None
    raising_reopened_before: dict[Player, bool] | None = None
    raising_reopened_after: dict[Player, bool] | None = None
    last_full_raise_size_before: int | None = None
    last_full_raise_size_after: int | None = None
    pending_players_before: list[Player] | None = None
    pending_players_after: list[Player] | None = None
    acting_player_before: Player | None = None
    acting_player_after: Player | None = None

    new_cards: list[str] = field(default_factory=list)
    returned_to: Player | None = None
    returned_amount: int | None = None
    ending_type: EndingType | None = None
    winner: HistoryWinner | None = None
    pot_before_award: int | None = None
    awarded_to_a: int | None = None
    awarded_to_b: int | None = None
    revealed_hole_cards: dict[Player, list[str]] | None = None
    commitments_cleared: bool | None = None
    pending_players_cleared: bool | None = None
    acting_player_cleared: bool | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class HandHistory:
    history_schema_version: str
    hand_id: str
    match_id: str | None
    hand_number: int
    hand_seed: int | None
    simulation_seed: int | None
    button_player: Player
    small_blind_player: Player
    big_blind_player: Player
    small_blind_amount: int
    big_blind_amount: int
    starting_stack_a: int
    starting_stack_b: int
    events: list[HandHistoryEvent] = field(default_factory=list)
    final_stack_a: int | None = None
    final_stack_b: int | None = None
    winner: HistoryWinner | None = None
    ending_type: EndingType | None = None
    final_board: list[str] = field(default_factory=list)
    showdown: bool = False
    settlement_complete: bool = False
    illegal_action_count: int = 0
    fallback_diagnostics: list[dict] = field(default_factory=list)

    def append(self, event: HandHistoryEvent) -> None:
        if event.event_index != len(self.events):
            raise ValueError("history event index must be contiguous")
        self.events.append(event)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HistoryValidationResult:
    valid: bool
    errors: list[str]


def _event_total(event: HandHistoryEvent, suffix: str) -> int:
    return (
        getattr(event, f"stack_a_{suffix}")
        + getattr(event, f"stack_b_{suffix}")
        + getattr(event, f"pot_{suffix}")
    )


def validate_hand_history(history: HandHistory) -> HistoryValidationResult:
    """Validate deterministic state continuity, settlement, cards, and privacy."""

    errors: list[str] = []
    events = history.events
    total_chips = history.starting_stack_a + history.starting_stack_b

    if history.history_schema_version != HISTORY_SCHEMA_VERSION:
        errors.append(
            f"unsupported history schema version: {history.history_schema_version}"
        )
    indexes = [event.event_index for event in events]
    if indexes != list(range(len(events))):
        errors.append("event indexes must start at zero and be contiguous")
    if sum(event.event_type == "hand_started" for event in events) != 1:
        errors.append("history must contain exactly one hand_started event")
    settled_indexes = [
        index for index, event in enumerate(events) if event.event_type == "hand_settled"
    ]
    if len(settled_indexes) != 1:
        errors.append("history must contain exactly one hand_settled event")
    elif settled_indexes[0] != len(events) - 1:
        errors.append("no events may occur after hand_settled")

    previous: HandHistoryEvent | None = None
    previous_board: list[str] = []
    seen_cards: set[str] = set()
    for index, event in enumerate(events):
        if min(
            event.pot_before,
            event.pot_after,
            event.stack_a_before,
            event.stack_a_after,
            event.stack_b_before,
            event.stack_b_after,
            event.street_commitment_a_before,
            event.street_commitment_a_after,
            event.street_commitment_b_before,
            event.street_commitment_b_after,
        ) < 0:
            errors.append(f"event {index} contains a negative chip value")
        if _event_total(event, "before") != total_chips:
            errors.append(f"event {index} breaks chip conservation before transition")
        if _event_total(event, "after") != total_chips:
            errors.append(f"event {index} breaks chip conservation after transition")

        if previous is not None:
            connected_fields = (
                ("pot_after", "pot_before"),
                ("stack_a_after", "stack_a_before"),
                ("stack_b_after", "stack_b_before"),
                ("street_commitment_a_after", "street_commitment_a_before"),
                ("street_commitment_b_after", "street_commitment_b_before"),
                ("current_highest_bet_after", "current_highest_bet_before"),
            )
            for prior_field, current_field in connected_fields:
                if getattr(previous, prior_field) != getattr(event, current_field):
                    errors.append(
                        f"event {index} {current_field} does not connect to "
                        f"event {index - 1} {prior_field}"
                    )

        if event.board[: len(previous_board)] != previous_board:
            errors.append(f"event {index} board lost or changed public cards")
        if len(event.board) > len(previous_board):
            if event.event_type != "board_revealed":
                errors.append(f"event {index} grows board outside board_revealed")
            new_cards = event.board[len(previous_board) :]
            expected_count = {"flop": 3, "turn": 1, "river": 1}.get(event.street)
            if expected_count != len(new_cards):
                errors.append(
                    f"event {index} reveals invalid {event.street} card count"
                )
            if event.new_cards != new_cards:
                errors.append(f"event {index} new_cards does not match board growth")
            for card in new_cards:
                if card in seen_cards:
                    errors.append(f"event {index} reveals duplicate card {card}")
                seen_cards.add(card)
        elif event.event_type == "board_revealed" and event.new_cards:
            errors.append(f"event {index} new_cards does not grow the board")

        if event.event_type == "action_taken":
            if event.actor is None or event.requested_action is None:
                errors.append(f"event {index} action is missing actor/requested action")
            if event.applied_action is None or event.amount_paid is None:
                errors.append(f"event {index} action is missing applied action/payment")
            if event.fallback_used is None or event.amount_to_call_before is None:
                errors.append(f"event {index} action is missing fallback/call evidence")
            if event.all_in_classification is None:
                errors.append(f"event {index} action lacks all-in classification")
            if event.applied_action in {"bet", "raise"} and event.target_total is None:
                errors.append(f"event {index} bet/raise lacks total target")
            if event.target_total is not None and event.actor is not None:
                before_commitment = (
                    event.street_commitment_a_before
                    if event.actor == "a"
                    else event.street_commitment_b_before
                )
                after_commitment = (
                    event.street_commitment_a_after
                    if event.actor == "a"
                    else event.street_commitment_b_after
                )
                if after_commitment != event.target_total:
                    errors.append(f"event {index} target total differs from commitment")
                if event.amount_paid != event.target_total - before_commitment:
                    errors.append(f"event {index} payment differs from target delta")

        if event.revealed_hole_cards:
            if event.event_type != "showdown":
                errors.append(f"event {index} leaks hole cards outside showdown")
            if set(event.revealed_hole_cards) != {"a", "b"}:
                errors.append(f"event {index} showdown must reveal both players")
            revealed = [
                card
                for cards in event.revealed_hole_cards.values()
                for card in cards
            ]
            if len(revealed) != 4 or len(set(revealed)) != 4:
                errors.append(f"event {index} has invalid showdown hole cards")
            if set(revealed) & set(event.board):
                errors.append(f"event {index} duplicates a board card at showdown")

        if event.settlement_complete and index != len(events) - 1:
            errors.append("settlement_complete may only be true on the final event")
        if index == len(events) - 1 and event.event_type == "hand_settled":
            if not event.settlement_complete:
                errors.append("final hand_settled event must be settlement complete")
            if (
                event.pot_after != 0
                or event.street_commitment_a_after != 0
                or event.street_commitment_b_after != 0
            ):
                errors.append("pot and commitments must be zero after settlement")
            if not (
                event.commitments_cleared
                and event.pending_players_cleared
                and event.acting_player_cleared
            ):
                errors.append("final settlement cleanup flags must all be true")

        previous = event
        previous_board = list(event.board)

    if history.ending_type == "fold" and any(
        event.revealed_hole_cards for event in events
    ):
        errors.append("fold-ended history must not reveal hole cards")
    if history.final_board != previous_board:
        errors.append("final history board does not match final event")
    if events:
        final = events[-1]
        if history.final_stack_a != final.stack_a_after:
            errors.append("final stack A does not match authoritative history result")
        if history.final_stack_b != final.stack_b_after:
            errors.append("final stack B does not match authoritative history result")
        if history.winner != final.winner:
            errors.append("winner does not match authoritative history result")
        if history.ending_type != final.ending_type:
            errors.append("ending type does not match authoritative history result")
    if not history.settlement_complete:
        errors.append("completed history must be settlement complete")

    return HistoryValidationResult(valid=not errors, errors=errors)
