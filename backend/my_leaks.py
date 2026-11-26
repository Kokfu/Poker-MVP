"""Review historical manual decisions and aggregate their estimated EV loss."""
from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
import logging
from threading import Event, Thread

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from coach.service import HERO, _replay, advise, spot_from_dict
from coach.store import HandStore, default_path
from drill_spots import LINES, classify, grade, has_three_bet, legal_options
from drills import STUDY_SOLVER_LOCK, DrillStore, app_lifespan as drills_lifespan
from poker_analyzer import EVALUATOR


ROUTER = APIRouter(prefix="/api/drills", tags=["drills"])
LOG = logging.getLogger(__name__)
REVIEW_VERSION = 2
SESSION_GAP = timedelta(minutes=30)


@dataclass(frozen=True)
class SavedHand:
    id: int
    opponent: str
    raw_spot: str


def review_saved_hand(hand: SavedHand, store: HandStore, stop: Event) -> list[dict] | None:
    try:
        full = replace(spot_from_dict(json.loads(hand.raw_spot)), villain_cards=None)
        status, _, engine = _replay(full)
        if status != "hand_complete":
            return None
    except (KeyError, TypeError, ValueError):
        return None

    decisions = []
    history = []
    events = (event for event in engine.history.events if event.event_type == "action_taken")
    for index, event in enumerate(events):
        if stop.is_set():
            return None
        if event.actor == HERO:
            prefix = replace(full, board=list(event.board), actions=full.actions[:index])
            with STUDY_SOLVER_LOCK:
                if stop.is_set():
                    return None
                result = advise(prefix, hand.opponent, store=store, through_id=hand.id - 1, include_preflop_ev=True)
            state = result["state"]
            options = legal_options(result.get("explanation") or {}, state["legal_actions"],
                                    state["minimum_target"], state["maximum_target"])
            if options:
                action = full.actions[index]
                amount = action.amount if action.action in {"bet", "raise"} else None
                bluff = (event.street == "river" and EVALUATOR.category(prefix.hero_cards, prefix.board) == "High Card"
                         and any(o["action"] in {"bet", "all_in"} and o["frequency"] >= 0.05 for o in options))
                category = classify(event.street, [(e["street"], e["actor"], e["action"]) for e in history],
                                    event.amount_to_call_before, can_bluff=bluff, can_three_bet=has_three_bet(options))
                decisions.append({
                    "category": category, "street": event.street, "position": full.hero_position,
                    "spot": {"hero_cards": full.hero_cards, "board": list(event.board), "history": list(history),
                             "pot": event.pot_before, "to_call": event.amount_to_call_before},
                    "action": action.action, "amount": amount, **grade(options, action.action, amount, full.big_blind),
                })
        history.append({"street": event.street, "actor": "hero" if event.actor == HERO else "villain",
                        "action": event.applied_action, "amount": event.target_total})
    return decisions


class LeakStore(DrillStore):
    def __init__(self, path):
        self.hands = HandStore(path)
        super().__init__(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS drill_leak_reviews (
                hand_id INTEGER PRIMARY KEY REFERENCES hands(id) ON DELETE CASCADE,
                version INTEGER NOT NULL, decisions TEXT
            )""")

    def next_hand(self) -> SavedHand | None:
        with self.connect() as db:
            row = db.execute("""
                SELECT h.id, h.opponent, h.spot FROM hands h
                LEFT JOIN drill_leak_reviews r ON r.hand_id = h.id AND r.version = ?
                WHERE r.hand_id IS NULL ORDER BY h.id DESC LIMIT 1
            """, (REVIEW_VERSION,)).fetchone()
        return SavedHand(*row) if row else None

    def save_review(self, hand_id: int, decisions: list[dict] | None):
        with self.connect() as db:
            db.execute("""
                INSERT INTO drill_leak_reviews(hand_id, version, decisions)
                SELECT id, ?, ? FROM hands WHERE id = ?
                ON CONFLICT(hand_id) DO UPDATE SET version = excluded.version, decisions = excluded.decisions
            """, (REVIEW_VERSION, json.dumps(decisions) if decisions is not None else None, hand_id))

    def report(self) -> dict:
        with self.connect() as db:
            db.execute("BEGIN")
            hands = db.execute("""
                SELECT h.created_at, p.source, r.hand_id, r.decisions FROM hands h
                LEFT JOIN practice_hands p ON p.hand_id = h.id
                LEFT JOIN drill_leak_reviews r ON r.hand_id = h.id AND r.version = ?
                ORDER BY h.id
            """, (REVIEW_VERSION,)).fetchall()
            attempts = db.execute("SELECT created_at, spot, outcome FROM drill_attempts ORDER BY created_at").fetchall()

        records = []
        coverage = {name: {"pending": 0, "reviewed": 0, "skipped": 0} for name in ("coach", "practice")}
        for created_at, practice_key, reviewed, decisions in hands:
            source = "practice" if practice_key is not None else "coach"
            if reviewed is None:
                coverage[source]["pending"] += 1
            elif decisions is None or not (rows := json.loads(decisions)):
                coverage[source]["skipped"] += 1
            else:
                coverage[source]["reviewed"] += 1
                session = practice_key.rpartition(":")[0] if practice_key is not None else None
                records.append((created_at, source, session, rows))

        timed_out = 0
        for created_at, raw_spot, raw_outcome in attempts:
            spot, outcome = json.loads(raw_spot), json.loads(raw_outcome)
            if outcome["action"] == "timeout":
                timed_out += 1
            else:
                decision = {
                    "spot": spot, "category": spot["category"], "street": spot["street"], "position": spot["position"],
                    **{key: outcome[key] for key in ("action", "amount", "correct", "cost_bb", "best", "reference")},
                }
                records.append((created_at, "drills", None, [decision]))
        return {**summarize(records), "coverage": coverage, "drill_attempts": len(attempts), "drill_timeouts": timed_out}


def metrics(rows: list[dict]) -> dict:
    count = len(rows)
    different = sum(not row["correct"] for row in rows)
    costs = [row["cost_bb"] for row in rows if row["cost_bb"] is not None]
    return {"decisions": count, "different": different, "costed": len(costs),
            "deviation_rate": round(different / count, 4) if count else None,
            "total_cost_bb": round(sum(costs), 3) if costs else None,
            "average_cost_bb": round(sum(costs) / len(costs), 3) if costs else None}


def by_dimension(rows: list[dict], key: str) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        name = row[key] or f"other_{row['street']}"
        groups[name].append(row)
    return [{"label": name, **metrics(items)} for name, items in groups.items()]


def rank_leaks(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        if row["category"] in LINES and not row["correct"] and (row["cost_bb"] or 0) > 0:
            groups[row["category"]].append(row)
    ranked = sorted(groups.items(), key=lambda group: (-sum(row["cost_bb"] for row in group[1]), group[0]))
    return [{"category": category, **metrics(items), "example": max(items, key=lambda r: r["cost_bb"])}
            for category, items in ranked[:3]]


def summarize(records: list[tuple[str, str, str | None, list[dict]]]) -> dict:
    rows = []
    sessions = []
    active = {}
    for created_at, source, explicit_id, decisions in sorted(records, key=lambda record: record[0]):
        instant = datetime.fromisoformat(created_at)
        key = (source, explicit_id)
        session = active.get(key)
        if session is None or (explicit_id is None and instant - session["end"] >= SESSION_GAP):
            session = {"source": source, "start": instant, "end": instant, "decisions": []}
            active[key] = session
            sessions.append(session)
        session["end"] = instant
        enriched = [{**decision, "source": source, "created_at": created_at} for decision in decisions]
        rows.extend(enriched)
        session["decisions"].extend(enriched)

    recent = sorted(sessions, key=lambda session: session["end"])[-6:]
    return {
        "all": metrics(rows),
        "by_source": by_dimension(rows, "source"),
        "by_street": by_dimension(rows, "street"),
        "by_position": by_dimension(rows, "position"),
        "by_category": by_dimension(rows, "category"),
        "sessions": [{"source": session["source"], "start": session["start"].isoformat(),
                      "end": session["end"].isoformat(), **metrics(session["decisions"])} for session in recent],
        "top": rank_leaks(rows),
    }


class ReviewBuffer:
    def __init__(self):
        self.wake = Event()
        self.stop = Event()
        self.worker = Thread(target=self.review, name="drill-leak-review", daemon=True)

    def review(self):
        self.wake.wait()
        while not self.stop.is_set():
            try:
                self.wake.clear()
                store = LeakStore(default_path())
                hand = store.next_hand()
                if hand is None:
                    self.wake.wait()
                    continue
                decisions = review_saved_hand(hand, store.hands, self.stop)
                if not self.stop.is_set():
                    store.save_review(hand.id, decisions)
            except Exception:
                LOG.exception("Saved hand review failed")
                self.stop.wait(5)


@asynccontextmanager
async def study_lifespan(app):
    async with drills_lifespan(app):
        buffer = ReviewBuffer()
        app.state.leak_review = buffer
        buffer.worker.start()
        try:
            yield
        finally:
            buffer.stop.set()
            buffer.wake.set()
            await run_in_threadpool(buffer.worker.join)


@ROUTER.get("/leaks")
def report(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    buffer = getattr(request.app.state, "leak_review", None)
    if buffer is not None:
        buffer.wake.set()
    return LeakStore(default_path()).report()
