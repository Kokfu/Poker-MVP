from __future__ import annotations

from .bots import BOT_TYPES
from .match import MatchConfig, MatchResult, run_match


DEFAULT_STARTING_STACK = 10_000
DEFAULT_SMALL_BLIND = 50
DEFAULT_BIG_BLIND = 100
DEFAULT_MAX_HANDS = 100
DEFAULT_MATCH_SEED = 0
DEFAULT_EQUITY_ITERATIONS = 1000
MAX_MATCH_HANDS = 10_000
SUPPORTED_EQUITY_ITERATIONS = (500, 1000, 2000)


def normalize_bot_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("bot name must be a string")
    return name.lower()


def validate_match_parameters(
    bot_a: str,
    bot_b: str,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    max_hands: int,
    seed: int,
    equity_iterations: int,
) -> tuple[str, str]:
    bot_a = normalize_bot_name(bot_a)
    bot_b = normalize_bot_name(bot_b)
    for name, value in {
        "starting_stack": starting_stack,
        "small_blind": small_blind,
        "big_blind": big_blind,
        "max_hands": max_hands,
        "seed": seed,
        "equity_iterations": equity_iterations,
    }.items():
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    if bot_a not in BOT_TYPES:
        raise ValueError(f"unsupported bot_a: {bot_a}")
    if bot_b not in BOT_TYPES:
        raise ValueError(f"unsupported bot_b: {bot_b}")
    if starting_stack <= 0:
        raise ValueError("starting_stack must be positive")
    if small_blind <= 0:
        raise ValueError("small_blind must be positive")
    if big_blind <= 0:
        raise ValueError("big_blind must be positive")
    if small_blind > big_blind:
        raise ValueError("small_blind cannot exceed big_blind")
    if not 1 <= max_hands <= MAX_MATCH_HANDS:
        raise ValueError(
            f"max_hands must be between 1 and {MAX_MATCH_HANDS}"
        )
    if equity_iterations not in SUPPORTED_EQUITY_ITERATIONS:
        supported = ", ".join(map(str, SUPPORTED_EQUITY_ITERATIONS))
        raise ValueError(f"equity_iterations must be one of: {supported}")
    return bot_a, bot_b


def match_result_to_public_dict(
    result: MatchResult,
    config: MatchConfig,
) -> dict:
    hand_summaries = [
        {
            "hand_number": hand.hand_number,
            "button_player": hand.button_player,
            "small_blind_player": hand.small_blind_player,
            "big_blind_player": hand.big_blind_player,
            "starting_stack_a": hand.starting_stacks["a"],
            "starting_stack_b": hand.starting_stacks["b"],
            "ending_stack_a": hand.ending_stacks["a"],
            "ending_stack_b": hand.ending_stacks["b"],
            "winner": hand.winner,
            "net_chips_a": hand.net_chips["a"],
            "net_chips_b": hand.net_chips["b"],
            "showdown": hand.showdown,
            "fold_ended": hand.fold_ended,
            "board": list(hand.board),
            "illegal_actions": hand.illegal_actions,
            "fallback_diagnostics": [
                dict(diagnostic) for diagnostic in hand.fallback_diagnostics
            ],
            "settlement_complete": hand.settlement_complete,
        }
        for hand in result.per_hand_summaries
    ]
    payload = {
        "match_id": result.match_id,
        "seed": result.seed,
        "bot_a": result.bot_a,
        "bot_b": result.bot_b,
        "starting_stack": config.starting_stack_a,
        "small_blind": config.small_blind,
        "big_blind": config.big_blind,
        "max_hands": config.max_hands,
        "hands_played": result.hands_played,
        "final_stack_a": result.final_stacks["a"],
        "final_stack_b": result.final_stacks["b"],
        "winner": result.winner,
        "termination_reason": result.termination_reason,
        "bot_a_net_chips": result.bot_a_net_chips,
        "bot_b_net_chips": result.bot_b_net_chips,
        "showdowns": result.total_showdowns,
        "fold_ended_hands": result.total_fold_ended_hands,
        "illegal_actions": result.illegal_action_count,
        "fallback_diagnostics": result.fallback_diagnostic_count,
        "hand_summaries": hand_summaries,
    }
    assert_public_match_invariants(payload)
    return payload


def assert_public_match_invariants(payload: dict) -> None:
    hands = payload["hand_summaries"]
    assert payload["final_stack_a"] + payload["final_stack_b"] == (
        payload["starting_stack"] * 2
    )
    assert payload["bot_a_net_chips"] + payload["bot_b_net_chips"] == 0
    assert payload["hands_played"] <= payload["max_hands"]
    assert len(hands) == payload["hands_played"]
    assert all(
        hand["starting_stack_a"] >= 0
        and hand["starting_stack_b"] >= 0
        and hand["ending_stack_a"] >= 0
        and hand["ending_stack_b"] >= 0
        and hand["settlement_complete"]
        for hand in hands
    )
    if payload["termination_reason"] == "elimination":
        assert 0 in (payload["final_stack_a"], payload["final_stack_b"])
    else:
        assert payload["termination_reason"] == "hand_limit"
        assert payload["hands_played"] == payload["max_hands"]
    assert payload["showdowns"] + payload["fold_ended_hands"] == payload[
        "hands_played"
    ]
    assert payload["illegal_actions"] == sum(
        hand["illegal_actions"] for hand in hands
    )
    assert payload["fallback_diagnostics"] == sum(
        len(hand["fallback_diagnostics"]) for hand in hands
    )


def run_builtin_match(
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
    bot_a, bot_b = validate_match_parameters(
        bot_a,
        bot_b,
        starting_stack,
        small_blind,
        big_blind,
        max_hands,
        seed,
        equity_iterations,
    )
    config = MatchConfig(
        starting_stack_a=starting_stack,
        starting_stack_b=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        max_hands=max_hands,
        seed=seed,
    )
    first = BOT_TYPES[bot_a](
        seed=seed,
        equity_iterations=equity_iterations,
    )
    second = BOT_TYPES[bot_b](
        seed=seed + 1,
        equity_iterations=equity_iterations,
    )
    return match_result_to_public_dict(run_match(first, second, config), config)
