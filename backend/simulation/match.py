from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

from .engine import HandEngine
from .history import HandHistory


Player = Literal["a", "b"]
MatchWinner = Literal["Bot A", "Bot B", "tied"]
TerminationReason = Literal["elimination", "hand_limit"]


@dataclass(frozen=True)
class MatchConfig:
    starting_stack_a: int = 10_000
    starting_stack_b: int = 10_000
    small_blind: int = 50
    big_blind: int = 100
    max_hands: int = 100
    seed: int = 0

    def __post_init__(self) -> None:
        integer_fields = {
            "starting_stack_a": self.starting_stack_a,
            "starting_stack_b": self.starting_stack_b,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "max_hands": self.max_hands,
            "seed": self.seed,
        }
        if any(type(value) is not int for value in integer_fields.values()):
            raise ValueError("match configuration values must be integers")
        if self.starting_stack_a <= 0 or self.starting_stack_b <= 0:
            raise ValueError("starting stacks must be positive")
        if self.small_blind <= 0 or self.big_blind <= 0:
            raise ValueError("blinds must be positive")
        if self.small_blind > self.big_blind:
            raise ValueError("small blind cannot exceed big blind")
        if self.max_hands <= 0:
            raise ValueError("max_hands must be positive")


@dataclass
class MatchState:
    stacks: dict[Player, int]
    hands_played: int = 0


@dataclass(frozen=True)
class MatchHandSummary:
    hand_number: int
    button_player: Player
    small_blind_player: Player
    big_blind_player: Player
    starting_stacks: dict[Player, int]
    ending_stacks: dict[Player, int]
    winner: MatchWinner
    net_chips: dict[Player, int]
    showdown: bool
    fold_ended: bool
    board: list[str]
    illegal_actions: int
    fallback_diagnostics: list[dict]
    settlement_count: int
    settlement_complete: bool
    history: HandHistory | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    seed: int
    bot_a: str
    bot_b: str
    starting_stacks: dict[Player, int]
    final_stacks: dict[Player, int]
    hands_played: int
    winner: MatchWinner
    termination_reason: TerminationReason
    bot_a_net_chips: int
    bot_b_net_chips: int
    total_showdowns: int
    total_fold_ended_hands: int
    illegal_action_count: int
    fallback_diagnostic_count: int
    per_hand_summaries: list[MatchHandSummary] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class PersistentMatchRunner:
    """Orchestrate settled HandEngine instances with stacks carried between hands."""

    def __init__(self, bot_a, bot_b, config: MatchConfig):
        self.bot_a = bot_a
        self.bot_b = bot_b
        self.config = config

    def _match_id(self) -> str:
        identity = json.dumps(
            {
                **asdict(self.config),
                "bot_a": type(self.bot_a).__name__,
                "bot_b": type(self.bot_b).__name__,
            },
            sort_keys=True,
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"poker-analyzer-match:{identity}"))

    @staticmethod
    def _winner(stacks: dict[Player, int]) -> MatchWinner:
        if stacks["a"] > stacks["b"]:
            return "Bot A"
        if stacks["b"] > stacks["a"]:
            return "Bot B"
        return "tied"

    def run(self) -> MatchResult:
        config = self.config
        initial_stacks: dict[Player, int] = {
            "a": config.starting_stack_a,
            "b": config.starting_stack_b,
        }
        initial_total = sum(initial_stacks.values())
        state = MatchState(stacks=dict(initial_stacks))
        hand_rng = random.Random(config.seed)
        summaries: list[MatchHandSummary] = []
        total_showdowns = 0
        total_fold_ended = 0
        illegal_actions = 0
        fallback_diagnostics = 0
        termination_reason: TerminationReason = "hand_limit"
        match_id = self._match_id()

        for index in range(config.max_hands):
            if 0 in state.stacks.values():
                termination_reason = "elimination"
                break

            hand_number = index + 1
            button: Player = "a" if index % 2 == 0 else "b"
            big_blind_player: Player = "b" if button == "a" else "a"
            hand_start = dict(state.stacks)
            engine = HandEngine(
                self.bot_a,
                self.bot_b,
                bb=config.big_blind,
                seed=hand_rng.randrange(2**31),
                hand_id=f"match-hand-{hand_number}",
                button=button,
                hand_number=hand_number,
                simulation_seed=config.seed,
                starting_stacks=hand_start,
                small_blind=config.small_blind,
                match_id=match_id,
            )
            result = engine.play()
            hand_end = dict(result["stacks"])
            settlement_complete = (
                engine.settlement_count == 1
                and engine.state.street == "complete"
                and engine.state.pot == 0
                and engine.state.current_bets == {"a": 0, "b": 0}
                and engine.state.pending_players == set()
            )

            assert settlement_complete
            assert all(stack >= 0 for stack in hand_end.values())
            assert sum(hand_end.values()) == initial_total

            net = {
                "a": hand_end["a"] - hand_start["a"],
                "b": hand_end["b"] - hand_start["b"],
            }
            assert net["a"] + net["b"] == 0

            winner: MatchWinner = (
                "Bot A"
                if result["winner"] == "a"
                else "Bot B"
                if result["winner"] == "b"
                else "tied"
            )
            diagnostics = [dict(item) for item in result["illegal_diagnostics"]]
            summaries.append(
                MatchHandSummary(
                    hand_number=hand_number,
                    button_player=button,
                    small_blind_player=button,
                    big_blind_player=big_blind_player,
                    starting_stacks=hand_start,
                    ending_stacks=hand_end,
                    winner=winner,
                    net_chips=net,
                    showdown=result["showdown"],
                    fold_ended=not result["showdown"],
                    board=list(engine.state.community_cards),
                    illegal_actions=result["illegal_actions"],
                    fallback_diagnostics=diagnostics,
                    settlement_count=engine.settlement_count,
                    settlement_complete=settlement_complete,
                    history=result["history"],
                )
            )

            state.stacks = hand_end
            state.hands_played += 1
            total_showdowns += int(result["showdown"])
            total_fold_ended += int(not result["showdown"])
            illegal_actions += result["illegal_actions"]
            fallback_diagnostics += len(diagnostics)

            if 0 in state.stacks.values():
                termination_reason = "elimination"
                break

        bot_a_net = state.stacks["a"] - initial_stacks["a"]
        bot_b_net = state.stacks["b"] - initial_stacks["b"]
        assert bot_a_net + bot_b_net == 0
        assert sum(state.stacks.values()) == initial_total
        assert total_showdowns + total_fold_ended == state.hands_played

        return MatchResult(
            match_id=match_id,
            seed=config.seed,
            bot_a=type(self.bot_a).__name__,
            bot_b=type(self.bot_b).__name__,
            starting_stacks=initial_stacks,
            final_stacks=dict(state.stacks),
            hands_played=state.hands_played,
            winner=self._winner(state.stacks),
            termination_reason=termination_reason,
            bot_a_net_chips=bot_a_net,
            bot_b_net_chips=bot_b_net,
            total_showdowns=total_showdowns,
            total_fold_ended_hands=total_fold_ended,
            illegal_action_count=illegal_actions,
            fallback_diagnostic_count=fallback_diagnostics,
            per_hand_summaries=summaries,
        )


def run_match(bot_a, bot_b, config: MatchConfig) -> MatchResult:
    return PersistentMatchRunner(bot_a, bot_b, config).run()
