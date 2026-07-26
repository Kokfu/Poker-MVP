from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poker_analyzer import RANKS, SUITS


SCHEMA_VERSION = "2.0"
ACTION_TYPES = {"fold", "check", "call", "bet", "raise", "all_in"}
STREETS = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
HIDDEN_FIELDS = {
    "opponent_cards",
    "opponent_hole_cards",
    "villain_cards",
    "future_cards",
    "undealt_board_cards",
    "deck",
    "deck_order",
    "remaining_deck",
    "burn_cards",
    "rng_state",
    "internal_rng_state",
}
REQUIRED_FIELDS = {
    "schema_version",
    "simulation_id",
    "hand_id",
    "hand_number",
    "decision_index",
    "seed",
    "bot_name",
    "acting_player",
    "position",
    "street",
    "hero_cards",
    "board_cards",
    "hero_stack",
    "opponent_stack",
    "starting_stack",
    "big_blind",
    "pot",
    "hero_street_commitment",
    "opponent_street_commitment",
    "current_highest_bet",
    "amount_to_call",
    "last_full_raise_size",
    "raising_reopened",
    "pending_players",
    "minimum_target_to",
    "maximum_target_to",
    "all_in_target_to",
    "legal_actions",
    "chosen_action",
    "chosen_target_to",
    "action_classification",
    "all_in_classification",
    "hand_ended_by",
    "winner",
    "showdown",
    "net_chips",
    "final_reward_bb",
}


class JsonlDataset:
    def __init__(self, path: str | None = None, overwrite: bool = False):
        self.path = path
        if path:
            target = Path(path)
            if target.exists() and not overwrite:
                raise FileExistsError(
                    "Dataset already exists; use --overwrite to replace it."
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            if overwrite:
                target.write_text("", encoding="utf-8")

    @property
    def enabled(self):
        return bool(self.path)

    def write(self, record):
        if self.path:
            with open(self.path, "a", encoding="utf-8") as output:
                output.write(json.dumps(record, separators=(",", ":")) + "\n")


def _integer(record: dict[str, Any], name: str, minimum: int = 0) -> int:
    value = record.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _optional_integer(record: dict[str, Any], name: str) -> int | None:
    value = record.get(name)
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{name} must be an integer or null")
    if isinstance(value, int) and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _validate_cards(record: dict[str, Any]) -> None:
    street = record["street"]
    hero = record["hero_cards"]
    board = record["board_cards"]
    if not isinstance(hero, list) or len(hero) != 2:
        raise ValueError("hero_cards must contain exactly two cards")
    if not isinstance(board, list) or len(board) != STREETS[street]:
        raise ValueError(
            f"board_cards must contain {STREETS[street]} cards on {street}"
        )
    cards = hero + board
    if any(
        not isinstance(card, str)
        or len(card) != 2
        or card[0] not in RANKS
        or card[1] not in SUITS
        for card in cards
    ):
        raise ValueError("invalid card notation")
    if len(cards) != len(set(cards)):
        raise ValueError("hero_cards and board_cards must be unique")


def _validate_action(record: dict[str, Any]) -> None:
    legal = record["legal_actions"]
    chosen = record["chosen_action"]
    if (
        not isinstance(legal, list)
        or not legal
        or len(legal) != len(set(legal))
        or any(action not in ACTION_TYPES for action in legal)
    ):
        raise ValueError("legal_actions must be a nonempty unique action list")
    if not isinstance(chosen, dict) or set(chosen) != {"type", "amount"}:
        raise ValueError("chosen_action must contain exactly type and amount")
    action = chosen["type"]
    amount = chosen["amount"]
    if action not in legal:
        raise ValueError("chosen action is absent from legal_actions")
    if amount is not None and (
        isinstance(amount, bool) or not isinstance(amount, int) or amount < 0
    ):
        raise ValueError("chosen action amount must be a nonnegative integer or null")

    hero_commitment = record["hero_street_commitment"]
    highest = record["current_highest_bet"]
    to_call = record["amount_to_call"]
    hero_stack = record["hero_stack"]
    minimum = record["minimum_target_to"]
    maximum = record["maximum_target_to"]
    all_in = record["all_in_target_to"]
    target = record["chosen_target_to"]
    reopened = record["raising_reopened"]
    classification = record["action_classification"]
    all_in_classification = record["all_in_classification"]

    if to_call != highest - hero_commitment:
        raise ValueError("amount_to_call does not match current betting state")
    if maximum != hero_commitment + hero_stack:
        raise ValueError("maximum_target_to does not match stack and commitment")
    if all_in != maximum:
        raise ValueError("all_in_target_to must equal maximum_target_to")
    if minimum is not None and minimum <= highest:
        raise ValueError("minimum_target_to must exceed current_highest_bet")
    if "raise" in legal and (
        not reopened or minimum is None or minimum > maximum or highest == 0
    ):
        raise ValueError("Raise is advertised without an affordable legal range")
    if minimum is not None and minimum > maximum and "raise" in legal:
        raise ValueError("Raise cannot be present when minimum exceeds maximum")
    if not reopened and "raise" in legal:
        raise ValueError("Raise cannot be present while raising is closed")

    if action in {"fold", "check"}:
        if target is not None or amount is not None:
            raise ValueError(f"{action} cannot have a target")
        if action == "check" and to_call != 0:
            raise ValueError("Check is invalid while facing a wager")
    elif action == "call":
        if to_call <= 0:
            raise ValueError("Call is invalid when amount_to_call is zero")
        if hero_stack <= to_call:
            raise ValueError("an exact or short all-in call must use AllIn")
        if target != hero_commitment + to_call or amount is not None:
            raise ValueError("Call target must be the exact matched commitment")
    elif action == "bet":
        if to_call != 0 or highest != 0:
            raise ValueError("Bet is invalid while a wager exists")
        if minimum is None or target is None or not minimum <= target <= maximum:
            raise ValueError("Bet target is outside the legal range")
        if amount != target:
            raise ValueError("Bet amount must use total-target semantics")
    elif action == "raise":
        if highest <= 0:
            raise ValueError("Raise is invalid when no wager exists")
        if not reopened:
            raise ValueError("Raise is invalid while raising is closed")
        if minimum is None or target is None or not minimum <= target <= maximum:
            raise ValueError("Raise target is outside the legal range")
        if amount != target:
            raise ValueError("Raise amount must use total-target semantics")
    elif action == "all_in":
        if target != all_in or amount is not None:
            raise ValueError("AllIn target must equal all_in_target_to")
        if target > highest and not reopened:
            raise ValueError("increasing AllIn is invalid while raising is closed")

    expected = {
        "fold": "fold",
        "check": "free_check",
        "call": "normal_call",
        "bet": "opening_bet",
        "raise": "full_raise",
    }.get(action)
    expected_all_in = None
    if action == "all_in":
        if target < highest:
            expected_all_in = "short_all_in_call"
        elif target == highest:
            expected_all_in = "exact_all_in_call"
        elif minimum is not None and target < minimum:
            expected_all_in = "short_all_in_raise"
        else:
            expected_all_in = "full_all_in_raise"
        expected = expected_all_in
    if classification != expected:
        raise ValueError("action_classification is inconsistent with the action")
    if all_in_classification != expected_all_in:
        raise ValueError("all_in_classification is inconsistent with AllIn state")


def _validate_result(record: dict[str, Any]) -> None:
    ended = record["hand_ended_by"]
    winner = record["winner"]
    showdown = record["showdown"]
    net = record["net_chips"]
    reward = record["final_reward_bb"]
    starting_stack = record["starting_stack"]
    big_blind = record["big_blind"]
    player = record["acting_player"]
    if ended not in {"fold", "showdown"}:
        raise ValueError("hand_ended_by must be fold or showdown")
    if not isinstance(showdown, bool) or showdown != (ended == "showdown"):
        raise ValueError("showdown is inconsistent with hand_ended_by")
    if winner not in {"a", "b", None}:
        raise ValueError("winner must be a, b, or null")
    if isinstance(net, bool) or not isinstance(net, int):
        raise ValueError("net_chips must be an integer")
    if not -starting_stack <= net <= starting_stack:
        raise ValueError("net_chips is outside starting-stack bounds")
    if isinstance(reward, bool) or not isinstance(reward, (int, float)):
        raise ValueError("final_reward_bb must be numeric")
    if reward != net / big_blind:
        raise ValueError("final_reward_bb is inconsistent with net_chips")
    if winner is None and net != 0:
        raise ValueError("tie records must have zero net_chips")
    if winner == player and net < 0:
        raise ValueError("winner cannot have negative net_chips")
    if winner is not None and winner != player and net > 0:
        raise ValueError("loser cannot have positive net_chips")


def _validate_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise ValueError("each JSONL line must contain one object")
    hidden = HIDDEN_FIELDS & record.keys()
    if hidden:
        raise ValueError(f"hidden-information field present: {sorted(hidden)[0]}")
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError(f"missing required field: {sorted(missing)[0]}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {record['schema_version']!r}")
    if not isinstance(record["simulation_id"], str) or not record["simulation_id"]:
        raise ValueError("simulation_id must be a nonempty string")
    if not isinstance(record["hand_id"], str) or not record["hand_id"]:
        raise ValueError("hand_id must be a nonempty string")
    _integer(record, "hand_number", 1)
    _integer(record, "decision_index")
    if record["seed"] is not None and (
        isinstance(record["seed"], bool) or not isinstance(record["seed"], int)
    ):
        raise ValueError("seed must be an integer or null")
    if record["acting_player"] not in {"a", "b"}:
        raise ValueError("acting_player must be a or b")
    if record["position"] not in {"BTN", "BB"}:
        raise ValueError("position must be BTN or BB")
    if record["street"] not in STREETS:
        raise ValueError("street is invalid")
    for field in (
        "hero_stack",
        "opponent_stack",
        "starting_stack",
        "big_blind",
        "pot",
        "hero_street_commitment",
        "opponent_street_commitment",
        "current_highest_bet",
        "amount_to_call",
        "last_full_raise_size",
        "maximum_target_to",
        "all_in_target_to",
    ):
        _integer(record, field)
    if record["starting_stack"] <= 0 or record["big_blind"] <= 0:
        raise ValueError("starting_stack and big_blind must be positive")
    _optional_integer(record, "minimum_target_to")
    if record["current_highest_bet"] < max(
        record["hero_street_commitment"],
        record["opponent_street_commitment"],
    ):
        raise ValueError("current_highest_bet is below a player commitment")
    if record["all_in_target_to"] < record["hero_street_commitment"]:
        raise ValueError("all_in_target_to is below current commitment")
    if not isinstance(record["raising_reopened"], bool):
        raise ValueError("raising_reopened must be boolean")
    pending = record["pending_players"]
    if (
        not isinstance(pending, list)
        or len(pending) != len(set(pending))
        or any(player not in {"a", "b"} for player in pending)
    ):
        raise ValueError("pending_players must be a unique player list")
    _validate_cards(record)
    _validate_action(record)
    _validate_result(record)


def validate_dataset(path: str) -> dict:
    checked = 0
    invalid = 0
    hands: set[tuple[str, int]] = set()
    errors: list[dict[str, Any]] = []
    next_index: dict[tuple[str, int], int] = {}
    simulation_ids: set[str] = set()
    hand_results: dict[tuple[str, int], tuple[Any, ...]] = {}

    with open(path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            checked += 1
            try:
                if not line.strip():
                    raise ValueError("blank JSONL record")
                record = json.loads(line)
                _validate_record(record)
                key = (record["simulation_id"], record["hand_number"])
                expected = next_index.get(key, 0)
                if record["decision_index"] != expected:
                    raise ValueError(
                        f"decision_index must be contiguous; expected {expected}"
                    )
                result = (
                    record["hand_ended_by"],
                    record["winner"],
                    record["showdown"],
                )
                if key in hand_results and hand_results[key] != result:
                    raise ValueError("inconsistent result fields within one hand")
                hand_results[key] = result
                next_index[key] = expected + 1
                hands.add(key)
                simulation_ids.add(record["simulation_id"])
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
                invalid += 1
                errors.append({"line": line_number, "reason": str(error)})

    if len(simulation_ids) > 1:
        invalid += 1
        errors.append(
            {"line": None, "reason": "dataset contains multiple simulation_id values"}
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "records_checked": checked,
        "hands_found": len(hands),
        "invalid_records": invalid,
        "errors": errors,
        "warnings": [],
    }
