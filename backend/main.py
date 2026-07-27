from typing import Literal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator
from poker_analyzer import RANKS, SUITS, analyze
from simulation.bots import BOT_TYPES
from simulation.engine import SimulationRunner
from simulation.history_service import (
    run_builtin_hand_history,
    run_builtin_match_history,
)
from simulation.match_service import (
    DEFAULT_BIG_BLIND,
    DEFAULT_EQUITY_ITERATIONS,
    DEFAULT_MATCH_SEED,
    DEFAULT_MAX_HANDS,
    DEFAULT_SMALL_BLIND,
    DEFAULT_STARTING_STACK,
    MAX_MATCH_HANDS,
    run_builtin_match,
)

app = FastAPI(title="Poker Analyzer MVP", openapi_url="/api/openapi.json", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

class AnalyzeRequest(BaseModel):
    hero_cards: list[str]
    board_cards: list[str] = Field(default_factory=list)
    opponents: int = 1
    pot: float = Field(ge=0)
    amount_to_call: float = Field(ge=0)
    hero_stack: float = Field(ge=0)
    position: Literal["UTG", "MP", "CO", "BTN", "SB", "BB"] | None = None
    action_history: str | None = Field(default=None, max_length=2000)
    iterations: Literal[10000, 50000, 100000] = 50000
    @field_validator("hero_cards", "board_cards")
    @classmethod
    def valid_cards(cls, cards):
        for card in cards:
            if not isinstance(card, str) or len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
                raise ValueError("Cards must use notation such as As, Kh, Td, or 7c.")
        return cards
    @model_validator(mode="after")
    def valid_game(self):
        if len(self.hero_cards) != 2: raise ValueError("Hero cards must contain exactly 2 cards.")
        if len(self.board_cards) not in (0, 3, 4, 5): raise ValueError("Board cards must contain 0, 3, 4, or 5 cards.")
        if self.opponents != 1: raise ValueError("MVP supports exactly 1 opponent.")
        if len(set(self.hero_cards + self.board_cards)) != len(self.hero_cards + self.board_cards): raise ValueError("Duplicate cards are not allowed.")
        if self.amount_to_call >= self.hero_stack: raise ValueError("All-in call scenarios are outside the MVP scope.")
        return self

@app.get("/api/health")
def health(): return {"status":"OK"}
@app.post("/api/analyze")
def analyze_hand(request: AnalyzeRequest): return analyze(request.hero_cards, request.board_cards, request.pot, request.amount_to_call, request.iterations)

class SimulationRequest(BaseModel):
    bot_a: Literal["random", "tight", "aggressive", "equity"]
    bot_b: Literal["random", "tight", "aggressive", "equity"]
    hands: int = Field(default=100, ge=1, le=10000)
    seed: int | None = None
    starting_stack_bb: int = Field(default=100, ge=10, le=500)
    equity_iterations: Literal[500, 1000, 2000] = 1000

@app.post("/api/simulations/run")
def run_simulation(request: SimulationRequest):
    a=BOT_TYPES[request.bot_a](seed=request.seed, equity_iterations=request.equity_iterations)
    b=BOT_TYPES[request.bot_b](seed=None if request.seed is None else request.seed+1, equity_iterations=request.equity_iterations)
    return SimulationRunner(a,b,request.hands,request.starting_stack_bb,request.seed,request.equity_iterations).run()


class MatchSimulationRequest(BaseModel):
    bot_a: Literal["random", "tight", "aggressive", "equity"] = "random"
    bot_b: Literal["random", "tight", "aggressive", "equity"] = "random"
    starting_stack: StrictInt = Field(default=DEFAULT_STARTING_STACK, gt=0)
    small_blind: StrictInt = Field(default=DEFAULT_SMALL_BLIND, gt=0)
    big_blind: StrictInt = Field(default=DEFAULT_BIG_BLIND, gt=0)
    max_hands: StrictInt = Field(
        default=DEFAULT_MAX_HANDS,
        ge=1,
        le=MAX_MATCH_HANDS,
    )
    seed: StrictInt = DEFAULT_MATCH_SEED
    equity_iterations: StrictInt = DEFAULT_EQUITY_ITERATIONS

    @field_validator("bot_a", "bot_b", mode="before")
    @classmethod
    def normalize_bot_names(cls, value):
        return value.lower() if isinstance(value, str) else value

    @field_validator("equity_iterations")
    @classmethod
    def supported_equity_iterations(cls, value):
        if value not in (500, 1000, 2000):
            raise ValueError("Equity iterations must be 500, 1000, or 2000.")
        return value

    @model_validator(mode="after")
    def valid_blind_relationship(self):
        if self.small_blind > self.big_blind:
            raise ValueError("Small blind cannot exceed big blind.")
        return self


class MatchHandSummaryResponse(BaseModel):
    hand_number: int
    button_player: Literal["a", "b"]
    small_blind_player: Literal["a", "b"]
    big_blind_player: Literal["a", "b"]
    starting_stack_a: int
    starting_stack_b: int
    ending_stack_a: int
    ending_stack_b: int
    winner: Literal["Bot A", "Bot B", "tied"]
    net_chips_a: int
    net_chips_b: int
    showdown: bool
    fold_ended: bool
    board: list[str]
    illegal_actions: int
    fallback_diagnostics: list[dict]
    settlement_complete: bool


class MatchSimulationResponse(BaseModel):
    match_id: str
    seed: int
    bot_a: str
    bot_b: str
    starting_stack: int
    small_blind: int
    big_blind: int
    max_hands: int
    hands_played: int
    final_stack_a: int
    final_stack_b: int
    winner: Literal["Bot A", "Bot B", "tied"]
    termination_reason: Literal["elimination", "hand_limit"]
    bot_a_net_chips: int
    bot_b_net_chips: int
    showdowns: int
    fold_ended_hands: int
    illegal_actions: int
    fallback_diagnostics: int
    hand_summaries: list[MatchHandSummaryResponse]


@app.post("/api/matches/simulate", response_model=MatchSimulationResponse)
def simulate_match(request: MatchSimulationRequest):
    return run_builtin_match(**request.model_dump())


class HandHistoryRequest(BaseModel):
    bot_a: Literal["random", "tight", "aggressive", "equity"] = "random"
    bot_b: Literal["random", "tight", "aggressive", "equity"] = "random"
    starting_stack_a: StrictInt = Field(default=DEFAULT_STARTING_STACK, gt=0)
    starting_stack_b: StrictInt = Field(default=DEFAULT_STARTING_STACK, gt=0)
    small_blind: StrictInt = Field(default=DEFAULT_SMALL_BLIND, gt=0)
    big_blind: StrictInt = Field(default=DEFAULT_BIG_BLIND, gt=0)
    button_player: Literal["a", "b"] = "a"
    seed: StrictInt = DEFAULT_MATCH_SEED
    equity_iterations: StrictInt = DEFAULT_EQUITY_ITERATIONS

    @field_validator("bot_a", "bot_b", mode="before")
    @classmethod
    def normalize_bot_names(cls, value):
        return value.lower() if isinstance(value, str) else value

    @field_validator("equity_iterations")
    @classmethod
    def supported_equity_iterations(cls, value):
        if value not in (500, 1000, 2000):
            raise ValueError("Equity iterations must be 500, 1000, or 2000.")
        return value

    @model_validator(mode="after")
    def valid_blind_relationship(self):
        if self.small_blind > self.big_blind:
            raise ValueError("Small blind cannot exceed big blind.")
        return self


@app.post("/api/histories/hand")
def simulate_hand_history(request: HandHistoryRequest):
    return run_builtin_hand_history(**request.model_dump())


@app.post("/api/histories/match")
def simulate_match_history(request: MatchSimulationRequest):
    return run_builtin_match_history(**request.model_dump())
