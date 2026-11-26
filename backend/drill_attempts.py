"""Recent completed drill decisions for review after practice."""
import json

from fastapi import APIRouter, Query, Request, Response

from drills import Category, get_store


router = APIRouter(prefix="/api/drills", tags=["drills"])


@router.get("/attempts")
def recent_attempts(request: Request, response: Response, category: Category | None = None,
                    limit: int = Query(default=12, ge=1, le=25)):
    response.headers["Cache-Control"] = "no-store"
    store = get_store(request)
    query = "SELECT id, created_at, spot, outcome FROM drill_attempts"
    params = (limit,)
    if category is not None:
        query += " WHERE category = ?"
        params = (category, limit)
    with store.connect() as db:
        rows = db.execute(query + " ORDER BY created_at DESC, rowid DESC LIMIT ?", params).fetchall()
    return [{"id": attempt_id, "created_at": created_at, "spot": json.loads(spot), "feedback": json.loads(outcome)}
            for attempt_id, created_at, spot, outcome in rows]
