"""In-memory, one-human heads-up practice tables on the existing local app."""
from __future__ import annotations

from secrets import randbits, token_urlsafe
from threading import Lock
from time import monotonic
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field, StrictInt

from simulation.actions import Action, ActionType
from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine
from simulation.evaluation import _validate_history_and_conservation
from simulation.opponent_model import OpponentModel


_STARTING_STACK = 10_000
_TABLE_LIMIT = 16
_IDLE_SECONDS = 3600
_TABLES = {}
_TABLES_LOCK = Lock()

def _prevent_caching(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/practice", dependencies=[Depends(_prevent_caching)])


class _HumanTurn(Exception):
    pass


class PracticeTable:
    def __init__(self):
        self.lock = Lock()
        self.last_used = monotonic()
        self.bot = BOT_TYPES["solver_adaptive"](seed=randbits(63))
        self.profile = OpponentModel("a")
        self.hand = 1
        self.seed = randbits(63)
        self.revision = 0
        self.trace: list[tuple[str, Action]] = []
        self.state = self.advance()

    def advance(self, action: Action | None = None):
        trace = list(self.trace)
        if action is not None:
            trace.append(("a", action))
        cursor = 0
        profile = self.profile.snapshot()
        button = "a" if self.hand % 2 else "b"

        def decide(seat, observation):
            nonlocal cursor
            if cursor < len(trace):
                recorded_seat, recorded_action = trace[cursor]
                if recorded_seat != seat:
                    raise RuntimeError("practice replay diverged")
            elif seat == "a":
                raise _HumanTurn
            else:
                recorded_action = self.bot.decide_decision(observation)
                trace.append((seat, recorded_action))
            cursor += 1
            return recorded_action

        hero = SimpleNamespace(decide_decision=lambda o: decide("a", o))
        bot = SimpleNamespace(decide_decision=lambda o: decide("b", o))
        engine = HandEngine(hero, bot, seed=self.seed, button=button, hand_number=self.hand,
                            hand_id=f"practice-{self.hand}", starting_stacks={"a": _STARTING_STACK, "b": _STARTING_STACK},
                            opponent_profile_provider=lambda seat: profile if seat == "b" else None)
        try:
            settled = engine.play()
        except _HumanTurn:
            settled = None
        finally:
            self.bot.decision_trace.clear()
        if cursor != len(trace):
            raise RuntimeError("practice replay did not consume the accepted actions")
        observation = engine.observe("a")
        state = {
            "hand": self.hand, "status": "complete" if settled else "your_turn",
            "position": observation.position, "street": observation.street,
            "your_cards": observation.hole_cards, "board": observation.community_cards,
            "pot": observation.pot, "your_stack": observation.hero_stack, "bot_stack": observation.opponent_stack,
            "to_call": 0 if settled else observation.amount_to_call,
            "legal_actions": [] if settled else observation.legal_actions,
            "minimum_target": None if settled else observation.minimum_target_to,
            "maximum_target": observation.maximum_target_to,
            "actions": [entry for entry in observation.action_history if entry["type"] in
                        ("fold", "check", "call", "bet", "raise", "all_in")],
        }
        if settled:
            history = settled["history"]
            net_a = settled["stacks"]["a"] - _STARTING_STACK
            net_b = settled["stacks"]["b"] - _STARTING_STACK
            _validate_history_and_conservation(history, net_a, net_b)
            self.profile.update(history)
            self.bot.observe_completed_hand(history, "b")
            state["net_chips"] = net_a
            if settled["showdown"]:
                showdown = next(event for event in history.events if event.event_type == "showdown")
                state["shown_bot_cards"] = showdown.revealed_hole_cards["b"]
        self.trace = trace
        self.revision += 1
        state["revision"] = self.revision
        state["learned_hands"] = self.profile.hands_observed
        return state

    def apply(self, action: Action):
        state = self.state
        if action.type not in state["legal_actions"]:
            raise HTTPException(422, "action is unavailable")
        if action.type in ("bet", "raise"):
            if action.amount is None or not state["minimum_target"] <= action.amount <= state["maximum_target"]:
                raise HTTPException(422, "enter a legal street-total target")
        elif action.amount is not None:
            raise HTTPException(422, "only bets and raises take a target")
        self.state = self.advance(action)
        return self.state

    def next_hand(self):
        if self.state["status"] != "complete":
            raise HTTPException(409, "finish the current hand first")
        previous = self.hand, self.seed, self.trace
        self.hand += 1
        self.seed = randbits(63)
        self.trace = []
        try:
            self.state = self.advance()
        except Exception:
            self.hand, self.seed, self.trace = previous
            raise
        return self.state


class Revision(BaseModel):
    revision: StrictInt = Field(ge=1)


class TableAction(Revision):
    action: ActionType
    amount: StrictInt | None = None


def _lookup(authorization: str | None) -> PracticeTable:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "table key required")
    with _TABLES_LOCK:
        table = _TABLES.get(authorization[7:])
        now = monotonic()
        if table is None or now - table.last_used > _IDLE_SECONDS:
            raise HTTPException(404, "table unavailable")
        table.last_used = now
    return table


def _check_revision(table: PracticeTable, revision: int):
    if table.revision != revision:
        raise HTTPException(409, "table changed; refresh your turn")


@router.post("/table", status_code=201)
def create_table():
    with _TABLES_LOCK:
        now = monotonic()
        for key, table in list(_TABLES.items()):
            if now - table.last_used > _IDLE_SECONDS:
                del _TABLES[key]
        if len(_TABLES) >= _TABLE_LIMIT:
            raise HTTPException(503, "practice tables are full; try later")
        key = token_urlsafe(32)
        table = _TABLES[key] = PracticeTable()
    return {"key": key, "table": table.state}


TableKey = Annotated[str | None, Header()]


@router.get("/table")
def get_table(authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        return table.state


@router.post("/table/action")
def submit_action(request: TableAction, authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        _check_revision(table, request.revision)
        return table.apply(Action(request.action, request.amount))


@router.post("/table/next")
def next_hand(request: Revision, authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        _check_revision(table, request.revision)
        return table.next_hand()
