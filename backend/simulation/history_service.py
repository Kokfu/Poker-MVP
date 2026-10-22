"""Public JSON serialization and execution services for hand histories."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .bots import BOT_TYPES
from .engine import HandEngine
from .history import (
    HISTORY_SCHEMA_VERSION,
    HandHistory,
    HandHistoryEvent,
    validate_hand_history,
)
from .match_service import (
    DEFAULT_BIG_BLIND,
    DEFAULT_EQUITY_ITERATIONS,
    DEFAULT_MATCH_SEED,
    DEFAULT_MAX_HANDS,
    DEFAULT_SMALL_BLIND,
    DEFAULT_STARTING_STACK,
    SUPPORTED_EQUITY_ITERATIONS,
    match_result_to_public_dict,
    normalize_bot_name,
    run_builtin_match_result,
)


HAND_DOCUMENT_TYPE = "hand_history"
MATCH_DOCUMENT_TYPE = "match_history"
FORBIDDEN_HISTORY_KEYS = {
    "deck",
    "deck_order",
    "remaining_deck",
    "remaining_cards",
    "burn_cards",
    "future_cards",
}


def validate_hand_parameters(
    bot_a: str,
    bot_b: str,
    starting_stack_a: int,
    starting_stack_b: int,
    small_blind: int,
    big_blind: int,
    button_player: str,
    seed: int,
    equity_iterations: int,
) -> tuple[str, str]:
    bot_a = normalize_bot_name(bot_a)
    bot_b = normalize_bot_name(bot_b)
    values = {
        "starting_stack_a": starting_stack_a,
        "starting_stack_b": starting_stack_b,
        "small_blind": small_blind,
        "big_blind": big_blind,
        "seed": seed,
        "equity_iterations": equity_iterations,
    }
    for name, value in values.items():
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    if bot_a not in BOT_TYPES:
        raise ValueError(f"unsupported bot_a: {bot_a}")
    if bot_b not in BOT_TYPES:
        raise ValueError(f"unsupported bot_b: {bot_b}")
    if starting_stack_a <= 0 or starting_stack_b <= 0:
        raise ValueError("starting stacks must be positive")
    if small_blind <= 0 or big_blind <= 0:
        raise ValueError("blinds must be positive")
    if small_blind > big_blind:
        raise ValueError("small_blind cannot exceed big_blind")
    if button_player not in {"a", "b"}:
        raise ValueError("button_player must be a or b")
    if equity_iterations not in SUPPORTED_EQUITY_ITERATIONS:
        supported = ", ".join(map(str, SUPPORTED_EQUITY_ITERATIONS))
        raise ValueError(f"equity_iterations must be one of: {supported}")
    return bot_a, bot_b


def _assert_no_forbidden_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_HISTORY_KEYS:
                raise ValueError(f"forbidden history key at {path}.{key}")
            _assert_no_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_keys(child, f"{path}[{index}]")


def serialize_hand_history(history: HandHistory) -> dict:
    validation = validate_hand_history(history)
    if not validation.valid:
        raise ValueError(
            "invalid internal hand history: " + "; ".join(validation.errors)
        )
    payload = asdict(history)
    _assert_no_forbidden_keys(payload)
    return payload


def make_hand_document(history: HandHistory) -> dict:
    payload = serialize_hand_history(history)
    return {
        "document_type": HAND_DOCUMENT_TYPE,
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "history": payload,
        "validation": {
            "valid": True,
            "errors": [],
            "warnings": [],
        },
    }


def _deterministic_hand_id(configuration: dict) -> str:
    identity = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    identifier = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"poker-analyzer-history-hand:{identity}",
    )
    return f"history-hand-{identifier}"


def run_builtin_hand_history(
    *,
    bot_a: str = "random",
    bot_b: str = "random",
    starting_stack_a: int = DEFAULT_STARTING_STACK,
    starting_stack_b: int = DEFAULT_STARTING_STACK,
    small_blind: int = DEFAULT_SMALL_BLIND,
    big_blind: int = DEFAULT_BIG_BLIND,
    button_player: str = "a",
    seed: int = DEFAULT_MATCH_SEED,
    equity_iterations: int = DEFAULT_EQUITY_ITERATIONS,
) -> dict:
    bot_a, bot_b = validate_hand_parameters(
        bot_a,
        bot_b,
        starting_stack_a,
        starting_stack_b,
        small_blind,
        big_blind,
        button_player,
        seed,
        equity_iterations,
    )
    configuration = {
        "bot_a": bot_a,
        "bot_b": bot_b,
        "starting_stack_a": starting_stack_a,
        "starting_stack_b": starting_stack_b,
        "small_blind": small_blind,
        "big_blind": big_blind,
        "button_player": button_player,
        "seed": seed,
        "equity_iterations": equity_iterations,
    }
    first = BOT_TYPES[bot_a](
        seed=seed,
        equity_iterations=equity_iterations,
    )
    second = BOT_TYPES[bot_b](
        seed=seed + 1,
        equity_iterations=equity_iterations,
    )
    engine = HandEngine(
        first,
        second,
        bb=big_blind,
        seed=seed,
        hand_id=_deterministic_hand_id(configuration),
        button=button_player,
        hand_number=1,
        simulation_seed=seed,
        starting_stacks={
            "a": starting_stack_a,
            "b": starting_stack_b,
        },
        small_blind=small_blind,
    )
    result = engine.play()
    return make_hand_document(result["history"])


def run_builtin_match_history(
    *,
    bot_a: str = "random",
    bot_b: str = "random",
    starting_stack: int = DEFAULT_STARTING_STACK,
    small_blind: int = DEFAULT_SMALL_BLIND,
    big_blind: int = DEFAULT_BIG_BLIND,
    max_hands: int = DEFAULT_MAX_HANDS,
    seed: int = DEFAULT_MATCH_SEED,
    equity_iterations: int = DEFAULT_EQUITY_ITERATIONS,
) -> dict:
    result, config = run_builtin_match_result(
        bot_a=bot_a,
        bot_b=bot_b,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        max_hands=max_hands,
        seed=seed,
        equity_iterations=equity_iterations,
    )
    match_payload = match_result_to_public_dict(result, config)
    histories = [
        serialize_hand_history(summary.history)
        for summary in result.per_hand_summaries
    ]
    invalid_count = 0
    errors: list[str] = []
    if len(histories) != result.hands_played:
        errors.append("history_count must equal hands_played")
    for previous, current in zip(histories, histories[1:]):
        if (
            current["starting_stack_a"] != previous["final_stack_a"]
            or current["starting_stack_b"] != previous["final_stack_b"]
        ):
            errors.append("history starting stacks do not carry forward")
        if current["button_player"] == previous["button_player"]:
            errors.append("button position did not alternate")
        if current["small_blind_player"] != current["button_player"]:
            errors.append("small blind position does not match button")
        if current["big_blind_player"] == current["button_player"]:
            errors.append("big blind position does not alternate from button")
    if match_payload["final_stack_a"] + match_payload["final_stack_b"] != (
        match_payload["starting_stack"] * 2
    ):
        errors.append("aggregate chip conservation failed")
    if match_payload["bot_a_net_chips"] + match_payload["bot_b_net_chips"] != 0:
        errors.append("aggregate net zero-sum failed")

    document = {
        "document_type": MATCH_DOCUMENT_TYPE,
        "history_schema_version": HISTORY_SCHEMA_VERSION,
        "match": match_payload,
        "histories": histories,
        "history_count": len(histories),
        "aggregate_validation": {
            "valid": not errors and invalid_count == 0,
            "errors": errors,
            "warnings": [],
        },
        "invalid_history_count": invalid_count,
        "aggregate_illegal_action_count": sum(
            history["illegal_action_count"] for history in histories
        ),
        "aggregate_fallback_count": sum(
            len(history["fallback_diagnostics"]) for history in histories
        ),
    }
    if errors:
        raise ValueError("invalid match history document: " + "; ".join(errors))
    _assert_no_forbidden_keys(document)
    return document


def hand_history_from_dict(payload: dict) -> HandHistory:
    if not isinstance(payload, dict):
        raise ValueError("history must be a JSON object")
    data = dict(payload)
    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("history events must be a JSON array")
    try:
        events = []
        for event in raw_events:
            if not isinstance(event, dict):
                raise ValueError("history event must be a JSON object")
            events.append(HandHistoryEvent(**event))
        data["events"] = events
        return HandHistory(**data)
    except TypeError as error:
        raise ValueError(f"invalid history fields: {error}") from error


def validate_history_document(document: Any) -> dict:
    errors: list[dict] = []
    warnings: list[str] = []
    schema_versions: set[str] = set()
    histories_payload: list[Any] = []
    document_type = None

    if not isinstance(document, dict):
        return {
            "document_type": None,
            "histories_checked": 0,
            "valid_histories": 0,
            "invalid_histories": 1,
            "errors": [{"document": ["document must be a JSON object"]}],
            "warnings": [],
            "schema_versions_found": [],
            "valid": False,
        }

    document_type = document.get("document_type")
    top_schema = document.get("history_schema_version")
    if isinstance(top_schema, str):
        schema_versions.add(top_schema)
    else:
        errors.append({"document": ["history_schema_version must be a string"]})
    if top_schema != HISTORY_SCHEMA_VERSION:
        errors.append(
            {
                "document": [
                    f"unsupported history schema version: {top_schema}"
                ]
            }
        )

    if document_type == HAND_DOCUMENT_TYPE:
        histories_payload = [document.get("history")]
    elif document_type == MATCH_DOCUMENT_TYPE:
        raw_histories = document.get("histories")
        if isinstance(raw_histories, list):
            histories_payload = raw_histories
        else:
            errors.append({"document": ["histories must be a JSON array"]})
    else:
        errors.append({"document": [f"unsupported document_type: {document_type}"]})

    valid_histories = 0
    invalid_histories = 0
    parsed_histories: list[tuple[int, HandHistory]] = []
    for index, payload in enumerate(histories_payload):
        try:
            _assert_no_forbidden_keys(payload, f"$.histories[{index}]")
            history = hand_history_from_dict(payload)
            schema_versions.add(history.history_schema_version)
            parsed_histories.append((index, history))
            validation = validate_hand_history(history)
            if validation.valid:
                valid_histories += 1
            else:
                invalid_histories += 1
                errors.append(
                    {"history_index": index, "errors": validation.errors}
                )
        except (TypeError, ValueError) as error:
            invalid_histories += 1
            errors.append({"history_index": index, "errors": [str(error)]})

    if document_type == MATCH_DOCUMENT_TYPE:
        declared_count = document.get("history_count")
        if declared_count != len(histories_payload):
            errors.append(
                {
                    "document": [
                        "history_count does not match histories array length"
                    ]
                }
            )
        for (previous_index, previous), (index, current) in zip(
            parsed_histories,
            parsed_histories[1:],
        ):
            if index != previous_index + 1:
                continue
            if (
                current.starting_stack_a != previous.final_stack_a
                or current.starting_stack_b != previous.final_stack_b
            ):
                errors.append(
                    {
                        "history_index": index,
                        "errors": [
                            "history starting stacks do not carry forward"
                        ],
                    }
                )
            if current.button_player == previous.button_player:
                errors.append(
                    {
                        "history_index": index,
                        "errors": ["button position did not alternate"],
                    }
                )
            if (
                current.small_blind_player != current.button_player
                or current.big_blind_player == current.button_player
            ):
                errors.append(
                    {
                        "history_index": index,
                        "errors": ["blind positions are inconsistent"],
                    }
                )

    return {
        "document_type": document_type,
        "histories_checked": len(histories_payload),
        "valid_histories": valid_histories,
        "invalid_histories": invalid_histories,
        "errors": errors,
        "warnings": warnings,
        "schema_versions_found": sorted(schema_versions),
        "valid": not errors and invalid_histories == 0,
    }


def load_and_validate_history(path: str | Path) -> dict:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "document_type": None,
            "histories_checked": 0,
            "valid_histories": 0,
            "invalid_histories": 1,
            "errors": [{"document": [f"unable to read valid JSON: {error}"]}],
            "warnings": [],
            "schema_versions_found": [],
            "valid": False,
        }
    return validate_history_document(document)


def json_document_text(document: dict) -> str:
    return json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


def write_json_document(
    document: dict,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    path = Path(output_path)
    if path.exists() and not overwrite:
        raise ValueError(
            f"output already exists: {path}; use --overwrite to replace it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_document_text(document) + "\n", encoding="utf-8")
    return path
