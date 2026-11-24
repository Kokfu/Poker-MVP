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
            # Proposal B (bet-size-conditioned reads): a derived cache of the opponent's responses to our
            # bets by size bucket.  Created if missing; the hands table is untouched, and the cache can
            # always be rebuilt by replaying the stored hands.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sized_reads (opponent TEXT NOT NULL, street_class TEXT NOT NULL, bucket TEXT NOT NULL, "
                "opportunities INTEGER NOT NULL, folds INTEGER NOT NULL, calls INTEGER NOT NULL, raises INTEGER NOT NULL, "
                "PRIMARY KEY (opponent, street_class, bucket))"
            )

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

    def all_hands(self, opponent: str | None = None) -> list[dict[str, Any]]:
        """Every logged hand (optionally one opponent's), oldest first, with its opponent name."""
        query, args = "SELECT id, opponent, created_at, spot FROM hands", ()
        if opponent is not None:
            query, args = query + " WHERE opponent = ?", (normalize_name(opponent),)
        with self._connect() as connection:
            rows = connection.execute(query + " ORDER BY id", args).fetchall()
        return [{"id": row_id, "opponent": name, "created_at": created_at, "spot": json.loads(spot)} for row_id, name, created_at, spot in rows]

    def delete_hand(self, hand_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT opponent FROM hands WHERE id = ?", (hand_id,)).fetchone()
            cursor = connection.execute("DELETE FROM hands WHERE id = ?", (hand_id,))
            if row is not None:  # the cached sized reads of that opponent are now stale; they are rebuilt on the next log
                connection.execute("DELETE FROM sized_reads WHERE opponent = ?", (row[0],))
            return cursor.rowcount > 0

    def delete_opponent(self, opponent: str) -> int:
        name = normalize_name(opponent)
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM hands WHERE opponent = ?", (name,))
            connection.execute("DELETE FROM sized_reads WHERE opponent = ?", (name,))
            return cursor.rowcount

    def save_sized_reads(self, opponent: str, cells: dict[str, tuple[int, int, int, int]], street_class: str = "postflop") -> None:
        """Replace the cached cells (bucket -> (opportunities, folds, calls, raises)) of one opponent."""
        name = normalize_name(opponent)
        with self._connect() as connection:
            connection.execute("DELETE FROM sized_reads WHERE opponent = ? AND street_class = ?", (name, street_class))
            connection.executemany(
                "INSERT INTO sized_reads (opponent, street_class, bucket, opportunities, folds, calls, raises) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(name, street_class, bucket, *map(int, values)) for bucket, values in sorted(cells.items())],
            )

    def sized_reads(self, opponent: str, street_class: str = "postflop") -> dict[str, tuple[int, int, int, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT bucket, opportunities, folds, calls, raises FROM sized_reads WHERE opponent = ? AND street_class = ? ORDER BY bucket",
                (normalize_name(opponent), street_class),
            ).fetchall()
        return {bucket: (n, folds, calls, raises) for bucket, n, folds, calls, raises in rows}

    def delete_all(self) -> int:
        """Remove every logged hand and every cached read; returns the number of hands removed."""
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM hands")
            connection.execute("DELETE FROM sized_reads")
            removed = cursor.rowcount
        # Rewrite the file so deleted hands do not linger in SQLite's free pages.
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            connection.execute("VACUUM")
        finally:
            connection.close()
        return removed

    def summary(self) -> dict[str, Any]:
        """Where the Coach keeps its data and how much is there."""
        with self._connect() as connection:
            hands, opponents, first, last = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT opponent), MIN(created_at), MAX(created_at) FROM hands"
            ).fetchone()
        return {
            "path": str(self.path.resolve()),
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "hands": hands, "opponents": opponents, "first_logged": first, "last_logged": last,
        }

    def opponents(self) -> list[tuple[str, int]]:
        with self._connect() as connection:
            return [(name, count) for name, count in connection.execute("SELECT opponent, COUNT(*) FROM hands GROUP BY opponent ORDER BY opponent")]
