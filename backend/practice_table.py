"""In-memory, one-human heads-up practice tables on the existing local app."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from logging import getLogger
from math import ceil
import re
from secrets import randbits, token_urlsafe
from sqlite3 import Error as SQLiteError
from threading import Lock, Timer
from time import monotonic
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from coach.service import Spot, SpotAction, advise, spot_to_dict
from coach.store import HandStore, MAX_NAME_LENGTH, normalize_name
from simulation.actions import Action, ActionType
from simulation.bots import BOT_TYPES
from simulation.engine import HandEngine
from simulation.evaluation import _validate_history_and_conservation
from simulation.opponent_model import OpponentModel


_STARTING_STACK = 10_000
_TABLE_LIMIT = 16
_IDLE_SECONDS = 3600
_DEFAULT_TURN_SECONDS = 20
_MAX_TURN_SECONDS = 120
_DEFAULT_OPPONENT = "Solver bot"
_REVISION_LIMIT = 2_147_483_647
_RATE_WINDOW = 60
_CREATE_LIMIT = 8
_READ_LIMIT = 60
_WRITE_LIMIT = 30
_REVIEW_LIMIT = 20
_CREATE_CLIENT_LIMIT = 256
_MAX_BODY_BYTES = 2048
_KEY = re.compile(r"[A-Za-z0-9_-]{43}")
_TABLES = {}
_TABLES_LOCK = Lock()
_CREATING = 0
_CREATES: dict[str, deque[float]] = {}
_LOG = getLogger(__name__)

def _prevent_caching(response: Response):
    response.headers["Cache-Control"] = "no-store"


class PracticeRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def bounded_request(request):
            if request.method == "POST":
                length = request.headers.get("content-length")
                if request.headers.get("transfer-encoding") is not None:
                    raise HTTPException(411, "Send practice requests with Content-Length.")
                if length is not None and (not length.isascii() or not length.isdecimal() or len(length) > 10):
                    raise HTTPException(400, "Invalid practice request length.")
                if length is not None and int(length) > _MAX_BODY_BYTES:
                    raise HTTPException(413, "Practice request is too large.")
            return await handle(request)

        return bounded_request


router = APIRouter(prefix="/api/practice", dependencies=[Depends(_prevent_caching)], route_class=PracticeRoute)


def _rate_limit(timestamps: deque[float], count: int, now: float):
    while timestamps and now - timestamps[0] >= _RATE_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= count:
        wait = max(1, ceil(_RATE_WINDOW - (now - timestamps[0])))
        raise HTTPException(429, "Too many practice requests. Try again shortly.", headers={"Retry-After": str(wait)})
    timestamps.append(now)


class _HumanTurn(Exception):
    pass


@dataclass(frozen=True)
class ReviewHand:
    hand: int
    through_id: int
    decisions: tuple[tuple[str, Spot, Action, bool], ...]


def _estimated_loss(action, result):
    options = (result["explain"] or {}).get("options", [])
    values = {option["label"]: option["ev"] for option in options if "ev" in option}
    label = action.type if action.amount is None else f"{action.type}_{action.amount}"
    advice_label = (result["explain"] or {}).get("chosen")
    if label in values and advice_label in values:
        return round(max(0.0, values[advice_label] - values[label]), 1)
    return None


class PracticeTable:
    def __init__(self, turn_seconds: int = _DEFAULT_TURN_SECONDS, opponent: str = _DEFAULT_OPPONENT):
        self.lock = Lock()
        self.review_lock = Lock()
        self.requests = {"read": deque(), "write": deque(), "review": deque()}
        self.closed = False
        self.last_used = monotonic()
        self.turn_seconds = turn_seconds
        self.opponent = opponent
        self.source = token_urlsafe(24)
        self.store = HandStore()
        self.through_id = self.store.latest_hand_id()
        self.deadline: float | None = None
        self.timer: Timer | None = None
        self.bot = BOT_TYPES["solver_adaptive"](seed=randbits(63))
        self.profile = OpponentModel("a")
        self.hand = 1
        self.seed = randbits(63)
        self.revision = 0
        self.trace: list[tuple[str, Action]] = []
        self.decisions: list[tuple[str, Spot, Action, bool]] = []
        self.completed: dict[int, ReviewHand] = {}
        self.reviewed: dict[int, list[dict]] = {}
        self.state = self.advance()
        self._arm_timer()

    def _arm_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        self.deadline = None
        if self.state["status"] == "your_turn":
            self.deadline = monotonic() + self.turn_seconds
            self.timer = Timer(self.turn_seconds, self._on_timeout, args=(self.revision,))
            self.timer.daemon = True
            self.timer.start()

    def _on_timeout(self, revision):
        with self.lock:
            if self.revision != revision or self.deadline is None:
                return
            remaining = self.deadline - monotonic()
            if remaining > 0:
                self.timer = Timer(remaining, self._on_timeout, args=(revision,))
                self.timer.daemon = True
                self.timer.start()
                return
            try:
                self.expire_turn()
            except Exception:
                _LOG.exception("Practice table timeout action failed")

    def expire_turn(self):
        if self.deadline is not None and monotonic() >= self.deadline:
            action = "check" if "check" in self.state["legal_actions"] else "fold"
            self.apply(Action(action), timed_out=True)

    def snapshot(self):
        remaining = None if self.deadline is None else max(0, round(1000 * (self.deadline - monotonic())))
        return {**self.state, "turn_seconds": self.turn_seconds, "remaining_ms": remaining,
                "opponent": self.opponent, "completed_hands": len(self.completed)}

    def check_rate(self, operation, limit):
        if self.closed:
            raise HTTPException(404, "table unavailable")
        _rate_limit(self.requests[operation], limit, monotonic())

    def advance(self, action: Action | None = None, *, timed_out: bool = False):
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
        decisions = list(self.decisions)
        if action is not None:
            decisions.append((self.state["street"], self.spot, action, timed_out))
        if settled:
            history = settled["history"]
            net_a = settled["stacks"]["a"] - _STARTING_STACK
            net_b = settled["stacks"]["b"] - _STARTING_STACK
            _validate_history_and_conservation(history, net_a, net_b)
            state["net_chips"] = net_a
            if settled["showdown"]:
                showdown = next(event for event in history.events if event.event_type == "showdown")
                state["shown_bot_cards"] = showdown.revealed_hole_cards["b"]
        spot = Spot(
            list(state["your_cards"]), list(state["board"]),
            "button" if self.hand % 2 else "big_blind",
            hero_stack=_STARTING_STACK, villain_stack=_STARTING_STACK,
            actions=[
                SpotAction("hero" if event.actor == "a" else "villain", event.applied_action,
                           event.target_total if event.applied_action in ("bet", "raise") else None)
                for event in engine.history.events if event.event_type == "action_taken"
            ],
            villain_cards=state.get("shown_bot_cards"),
        )
        if settled:
            try:
                self.store.add(self.opponent, spot_to_dict(spot), practice_source=f"{self.source}:{self.hand}")
            except SQLiteError as error:
                raise HTTPException(503, "Coach could not save this hand. Try again.") from error
            self.profile.update(history)
            self.bot.observe_completed_hand(history, "b")
            # Completed-hand learning lives in the public profiles. The next
            # hand starts fresh and has no use for these large street solves.
            self.bot.memory = None
            self.completed[self.revision + 1] = ReviewHand(self.hand, self.through_id, tuple(decisions))
        self.spot = spot
        self.trace = trace
        self.decisions = decisions
        self.revision += 1
        state["revision"] = self.revision
        state["learned_hands"] = self.profile.hands_observed
        return state

    def apply(self, action: Action, *, timed_out: bool = False):
        state = self.state
        if action.type not in state["legal_actions"]:
            raise HTTPException(422, "action is unavailable")
        if action.type in ("bet", "raise"):
            if action.amount is None or not state["minimum_target"] <= action.amount <= state["maximum_target"]:
                raise HTTPException(422, "enter a legal street-total target")
        elif action.amount is not None:
            raise HTTPException(422, "only bets and raises take a target")
        self.state = self.advance(action, timed_out=timed_out)
        self.state["last_action_timed_out"] = timed_out
        self._arm_timer()
        return self.snapshot()

    def next_hand(self):
        if self.state["status"] != "complete":
            raise HTTPException(409, "finish the current hand first")
        through_id = self.store.latest_hand_id()
        previous = self.hand, self.seed, self.trace, self.decisions, self.through_id
        self.hand += 1
        self.seed = randbits(63)
        self.trace = []
        self.decisions = []
        self.through_id = through_id
        try:
            self.state = self.advance()
        except Exception:
            self.hand, self.seed, self.trace, self.decisions, self.through_id = previous
            raise
        self._arm_timer()
        return self.snapshot()

    def review(self, revision):
        with self.review_lock:
            with self.lock:
                self.check_rate("review", _REVIEW_LIMIT)
                _check_revision(self, revision)
                if self.state["status"] != "complete":
                    raise HTTPException(409, "finish the current hand first")
                hand = self.completed[revision]
            return self._review_hand(revision, hand)

    def _review_hand(self, revision: int, hand: ReviewHand):
        # The review lock serializes lazy computation. The table lock is free
        # during the solve so a player can continue from the next hand.
        if revision not in self.reviewed:
            rows = []
            for street, spot, action, timed_out in hand.decisions:
                result = advise(spot, self.opponent, store=self.store, through_id=hand.through_id,
                                include_preflop_ev=True)
                play = {"action": action.type, "amount": action.amount}
                rows.append({"street": street, "action": play, "timed_out": timed_out,
                             "advice": result["advice"], "explain": result["explain"],
                             "estimated_cost": _estimated_loss(action, result)})
            self.reviewed[revision] = rows
        return self.reviewed[revision]

    def session_review(self):
        with self.review_lock:
            with self.lock:
                self.check_rate("review", _REVIEW_LIMIT)
                completed = tuple(self.completed.items())
            hands = []
            for revision, hand in completed:
                differences = [row for row in self._review_hand(revision, hand) if row["action"] != row["advice"]]
                if differences:
                    costs = [row["estimated_cost"] for row in differences]
                    cost = None if None in costs else round(sum(costs), 1)
                    hands.append({"hand": hand.hand, "decisions": differences, "estimated_cost": cost})
            return {"completed_hands": len(completed), "hands": hands}


class TableSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_seconds: StrictInt = Field(default=_DEFAULT_TURN_SECONDS, ge=1, le=_MAX_TURN_SECONDS)
    opponent: str = Field(default=_DEFAULT_OPPONENT, min_length=1, max_length=MAX_NAME_LENGTH)

    @field_validator("opponent")
    @classmethod
    def valid_opponent(cls, value):
        return normalize_name(value)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: StrictInt = Field(ge=1, le=_REVISION_LIMIT)


class TableAction(Revision):
    action: ActionType
    amount: StrictInt | None = Field(default=None, ge=1, le=2 * _STARTING_STACK)


def _lookup(authorization: str | None) -> PracticeTable:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "table key required")
    key = authorization[7:]
    if _KEY.fullmatch(key) is None:
        raise HTTPException(404, "table unavailable")
    with _TABLES_LOCK:
        table = _TABLES.get(key)
        now = monotonic()
        if table is None or now - table.last_used > _IDLE_SECONDS:
            raise HTTPException(404, "table unavailable")
        table.last_used = now
    return table


def _check_revision(table: PracticeTable, revision: int):
    if table.revision != revision:
        raise HTTPException(409, "table changed; refresh your turn")


@router.post("/table", status_code=201)
def create_table(request: Request, settings: TableSettings | None = None):
    global _CREATING
    settings = settings or TableSettings()
    with _TABLES_LOCK:
        now = monotonic()
        host = request.client.host if request.client is not None else ""
        # Use the app server's client address, never a header supplied by the
        # caller. If a local proxy groups clients they share the creation cap.
        if host not in _CREATES:
            for address, timestamps in list(_CREATES.items()):
                if now - timestamps[-1] >= _RATE_WINDOW:
                    del _CREATES[address]
            if len(_CREATES) >= _CREATE_CLIENT_LIMIT:
                raise HTTPException(429, "Too many practice clients. Try again shortly.")
        _rate_limit(_CREATES.setdefault(host, deque()), _CREATE_LIMIT, now)
        for key, table in list(_TABLES.items()):
            if now - table.last_used > _IDLE_SECONDS:
                del _TABLES[key]
        if len(_TABLES) + _CREATING >= _TABLE_LIMIT:
            raise HTTPException(503, "practice tables are full; try later")
        key = token_urlsafe(32)
        _CREATING += 1
    table = None
    try:
        table = PracticeTable(settings.turn_seconds, settings.opponent)
    finally:
        with _TABLES_LOCK:
            _CREATING -= 1
            if table is not None:
                _TABLES[key] = table
    with table.lock:
        return {"key": key, "table": table.snapshot()}


TableKey = Annotated[str | None, Header()]


@router.get("/table")
def get_table(authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        table.check_rate("read", _READ_LIMIT)
        table.expire_turn()
        return table.snapshot()


@router.post("/table/action")
def submit_action(request: TableAction, authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        table.check_rate("write", _WRITE_LIMIT)
        table.expire_turn()
        _check_revision(table, request.revision)
        return table.apply(Action(request.action, request.amount))


@router.post("/table/next")
def next_hand(request: Revision, authorization: TableKey = None):
    table = _lookup(authorization)
    with table.lock:
        table.check_rate("write", _WRITE_LIMIT)
        table.expire_turn()
        _check_revision(table, request.revision)
        return table.next_hand()


@router.get("/table/review")
def review_hand(revision: Annotated[int, Query(ge=1, le=_REVISION_LIMIT)], authorization: TableKey = None):
    return _lookup(authorization).review(revision)


@router.get("/table/session")
def review_session(authorization: TableKey = None):
    return _lookup(authorization).session_review()


@router.delete("/table", status_code=204)
def close_table(authorization: TableKey = None):
    table = _lookup(authorization)
    key = authorization[7:]
    with table.lock, _TABLES_LOCK:
        if _TABLES.get(key) is table:
            del _TABLES[key]
            table.closed = True
            if table.timer is not None:
                table.timer.cancel()
            table.deadline = None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
