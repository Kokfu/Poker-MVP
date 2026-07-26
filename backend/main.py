from typing import Literal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from poker_analyzer import RANKS, SUITS, analyze
from simulation.bots import BOT_TYPES
from simulation.engine import SimulationRunner

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
