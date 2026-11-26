"""Buffered, server-timed drills. Answers never trigger a solver call."""
from __future__ import annotations

from contextlib import asynccontextmanager, closing, contextmanager
from datetime import datetime, timezone
import json
import logging
from secrets import randbits, token_urlsafe
import sqlite3
from threading import Event, Lock, Thread
from time import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from coach.store import default_path
from coach.warmup import coach_lifespan
from drill_spots import LINES, grade, make_spot


Category = Literal[tuple(LINES)]
Action = Literal["fold", "check", "call", "bet", "raise", "all_in", "timeout"]
router = APIRouter(prefix="/api/drills", tags=["drills"])
LOG = logging.getLogger(__name__)
BUFFER_SIZE = 3
STUDY_SOLVER_LOCK = Lock()


class Start(BaseModel):
    category: Category | None = None
    seconds: StrictInt = Field(default=15, ge=3, le=120)


class Answer(BaseModel):
    action: Action
    amount: StrictInt | None = None


class DrillStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS drill_spots (
                    id TEXT PRIMARY KEY, category TEXT NOT NULL, spot TEXT NOT NULL,
                    advice TEXT NOT NULL, started REAL, seconds INTEGER
                );
                CREATE INDEX IF NOT EXISTS drill_ready ON drill_spots(category) WHERE started IS NULL;
                CREATE TABLE IF NOT EXISTS drill_attempts (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, category TEXT NOT NULL,
                    spot TEXT NOT NULL, outcome TEXT NOT NULL, elapsed_ms INTEGER NOT NULL,
                    correct INTEGER NOT NULL, cost_bb REAL
                );
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            yield db

    def ready(self) -> dict[str, int]:
        with self.connect() as db:
            return dict(db.execute("SELECT category, count(*) FROM drill_spots WHERE started IS NULL GROUP BY category"))

    def add(self, spot: dict, advice: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO drill_spots(id, category, spot, advice) VALUES (?, ?, ?, ?)",
                       (token_urlsafe(18), spot["category"], json.dumps(spot), json.dumps(advice)))

    def start(self, settings: Start) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time()
            # Grace period for recovering expired turns after a temporary disconnect.
            db.execute("DELETE FROM drill_spots WHERE started + seconds < ?", (now - 86400,))
            query = "SELECT id, spot FROM drill_spots WHERE started IS NULL"
            params = ()
            if settings.category:
                query += " AND category = ?"
                params = (settings.category,)
            row = db.execute(query + " ORDER BY rowid LIMIT 1", params).fetchone()
            if row is None:
                return None
            spot_id, spot = row
            issued = time()
            db.execute("UPDATE drill_spots SET started = ?, seconds = ? WHERE id = ?",
                       (issued, settings.seconds, spot_id))
        return {**json.loads(spot), "id": spot_id,
                "remaining_ms": max(0, round((issued + settings.seconds - time()) * 1000))}

    def answer(self, spot_id: str, answer: Answer) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT outcome FROM drill_attempts WHERE id = ?", (spot_id,)).fetchone()
            if previous:
                return json.loads(previous[0])
            row = db.execute("SELECT spot, advice, started, seconds FROM drill_spots WHERE id = ?",
                             (spot_id,)).fetchone()
            if row is None or row[2] is None:
                raise HTTPException(404, "Drill is unavailable. Start another spot.")
            raw_spot, raw_advice, started, seconds = row
            spot, advice = json.loads(raw_spot), json.loads(raw_advice)
            action, amount = answer.action, answer.amount
            elapsed = max(0, round((time() - started) * 1000))
            if elapsed >= seconds * 1000:
                action, amount = "timeout", None
            elif action == "timeout":
                amount = None
            elif action not in spot["legal_actions"]:
                raise HTTPException(422, "Choose a legal action for this spot.")
            elif action in {"bet", "raise"}:
                if amount is None or not spot["minimum_target"] <= amount <= spot["maximum_target"]:
                    raise HTTPException(422, "Enter a legal total for this street.")
            elif amount is not None:
                raise HTTPException(422, "Only bets and raises take an amount.")
            result = {
                **advice, **grade(advice["options"], action, amount, spot["big_blind"]),
                "action": action, "amount": amount, "elapsed_ms": min(elapsed, seconds * 1000),
            }
            db.execute("INSERT INTO drill_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (spot_id, datetime.now(timezone.utc).isoformat(), spot["category"], raw_spot, json.dumps(result),
                        result["elapsed_ms"], result["correct"], result["cost_bb"]))
            db.execute("DELETE FROM drill_spots WHERE id = ?", (spot_id,))
            return result

    def stats(self) -> list[dict]:
        with self.connect() as db:
            return [
                {"category": row[0], "attempts": row[1], "correct": row[2], "average_ms": row[3],
                 "average_cost_bb": row[4], "costed": row[5]}
                for row in db.execute("SELECT category, count(*), sum(correct), avg(elapsed_ms), avg(cost_bb), "
                                      "count(cost_bb) FROM drill_attempts GROUP BY category")
            ]


class DrillBuffer:
    def __init__(self):
        self.wake = Event()
        self.stop = Event()
        self.worker = Thread(target=self.fill, name="drill-buffer", daemon=True)

    def fill(self):
        # Wait until the first visit to Drills, so other tabs pay no solve cost.
        self.wake.wait()
        while not self.stop.is_set():
            try:
                self.wake.clear()
                store = DrillStore(default_path())
                counts = store.ready()
                needed = [category for category in LINES if counts.get(category, 0) < BUFFER_SIZE]
                for category in needed:
                    if self.stop.is_set():
                        return
                    with STUDY_SOLVER_LOCK:
                        if self.stop.is_set():
                            return
                        candidate = make_spot(category, randbits(63))
                    if candidate is not None:
                        store.add(*candidate)
                if not needed:
                    self.wake.wait()
            except Exception:
                LOG.exception("Drill preparation failed")
                self.stop.wait(5)


@asynccontextmanager
async def app_lifespan(app):
    async with coach_lifespan(app):
        buffer = DrillBuffer()
        app.state.drill_buffer = buffer
        buffer.worker.start()
        try:
            yield
        finally:
            buffer.stop.set()
            buffer.wake.set()
            await run_in_threadpool(buffer.worker.join)


def get_store(request: Request) -> DrillStore:
    buffer = getattr(request.app.state, "drill_buffer", None)
    if buffer is not None:
        buffer.wake.set()
    return DrillStore(default_path())


@router.get("/stats")
def stats(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    store = get_store(request)
    return {"categories": store.stats(), "ready": store.ready()}


@router.post("/start")
def start(settings: Start, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    spot = get_store(request).start(settings)
    # Signal after the transaction too. Before it, the producer may see a full buffer.
    buffer = getattr(request.app.state, "drill_buffer", None)
    if buffer is not None:
        buffer.wake.set()
    return spot


@router.post("/{spot_id}/answer")
def answer(spot_id: str, submission: Answer, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return get_store(request).answer(spot_id, submission)
