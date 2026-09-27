"""Local SQLite storage for logged Coach hands (one row per hand)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "coach.sqlite"
MAX_NAME_LENGTH = 60


def default_path() -> Path:
    return Path(os.environ.get("COACH_DB_PATH", DEFAULT_PATH))


def normalize_name(name: str) -> str:
    cleaned = " ".join(str(name).split())
    if not cleaned or len(cleaned) > MAX_NAME_LENGTH:
        raise ValueError(f"opponent name must be 1-{MAX_NAME_LENGTH} characters")
    return cleaned


class HandStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hands (id INTEGER PRIMARY KEY AUTOINCREMENT, opponent TEXT NOT NULL, "
                "created_at TEXT NOT NULL, spot TEXT NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS hands_by_opponent ON hands (opponent)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def add(self, opponent: str, spot: dict[str, Any]) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO hands (opponent, created_at, spot) VALUES (?, ?, ?)",
                (normalize_name(opponent), datetime.now(timezone.utc).isoformat(), json.dumps(spot, sort_keys=True)),
            )
            return int(cursor.lastrowid)

    def hands(self, opponent: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT spot FROM hands WHERE opponent = ? ORDER BY id", (normalize_name(opponent),)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def hands_with_meta(self, opponent: str) -> list[dict[str, Any]]:
        """Logged hands for one opponent, newest first, with id and created_at."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, spot FROM hands WHERE opponent = ? ORDER BY id DESC",
                (normalize_name(opponent),),
            ).fetchall()
        return [{"id": row_id, "created_at": created_at, "spot": json.loads(spot)} for row_id, created_at, spot in rows]

    def delete_hand(self, hand_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM hands WHERE id = ?", (hand_id,))
            return cursor.rowcount > 0

    def delete_opponent(self, opponent: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM hands WHERE opponent = ?", (normalize_name(opponent),))
            return cursor.rowcount

    def opponents(self) -> list[tuple[str, int]]:
        with self._connect() as connection:
            return [(name, count) for name, count in connection.execute("SELECT opponent, COUNT(*) FROM hands GROUP BY opponent ORDER BY opponent")]
