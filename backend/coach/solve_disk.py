"""Bounded local storage of the Coach's exact postflop policies and EV inputs."""

from contextlib import closing
from dataclasses import asdict
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from os import getenv
from pathlib import Path
import platform
import sqlite3
from zipfile import BadZipFile

import numpy as np

from solver.bot import StreetSolve
from solver.cfr import RangeSolver
from solver.tree import StreetTree


_LIMIT = 160 * 1024 * 1024
_THREAD_ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


@lru_cache(maxsize=1)
def _solver_revision():
    from solver import cfr

    digest = sha256(b"coach-exact-cache-1")
    source = Path(cfr.__file__).parent
    for file in sorted(source.glob("*.py")):
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def _json_part(value):
    if isinstance(value, bytes):
        return {"bytes_sha256": sha256(value).hexdigest()}
    if isinstance(value, np.generic):
        return value.item()
    return asdict(value)


def _key_digest(exact_key):
    namespace = (_solver_revision(), np.__version__, platform.system(), platform.machine(),
                 tuple(getenv(name) for name in _THREAD_ENV))
    payload = json.dumps((namespace, exact_key), default=_json_part, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


def _pack(solve):
    data = BytesIO()
    arrays = {f"policy_{node}": policy for node, policy in solve.average.items()}
    np.savez(data, combo_0=solve.combos[0], combo_1=solve.combos[1],
             win=solve.solver.win[0], compat=solve.solver.compat[0].astype(bool), **arrays)
    return data.getvalue()


def _unpack(row, root_state, menu, ranges):
    payload, locked, candidates, seconds = row
    tree = StreetTree(root_state, menu)
    with np.load(BytesIO(payload), allow_pickle=False) as data:
        combos = (data["combo_0"], data["combo_1"])
        working_ranges = (ranges[0][combos[0]], ranges[1][combos[1]])
        solver = RangeSolver(tree, working_ranges, data["win"], data["compat"], combo_ids=combos)
        policies = {node.index: data[f"policy_{node.index}"] for node in solver.decisions}
        if any(policies[node.index].shape != (len(node.actions), len(combos[node.player])) for node in solver.decisions):
            raise ValueError("cached strategy shape differs from the current tree")
    return StreetSolve(tree, combos, policies, None, seconds, locked, solver, candidates)


def _read(path, key, root_state, menu, ranges):
    try:
        if not path.is_file():
            return None
        with closing(sqlite3.connect(path, timeout=0.05)) as connection:
            row = connection.execute(
                "SELECT payload, locked, candidates, seconds FROM exact_solves WHERE cache_key = ?", (key,)
            ).fetchone()
        return _unpack(row, root_state, menu, ranges) if row else None
    except (OSError, sqlite3.Error, BadZipFile, ValueError, TypeError, IndexError, KeyError):
        return None  # The cache is disposable and may be in use by another process.


def _write(path, key, solve):
    if solve.solver is None or solve.unlocked_average is not None or solve.sized_info is not None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _pack(solve)
        with closing(sqlite3.connect(path, timeout=0.05)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS exact_solves (ordinal INTEGER PRIMARY KEY, cache_key TEXT UNIQUE, "
                "payload BLOB NOT NULL, locked INTEGER, candidates INTEGER, seconds REAL)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO exact_solves (cache_key, payload, locked, candidates, seconds) VALUES (?, ?, ?, ?, ?)",
                (key, payload, solve.locked_nodes, solve.candidate_locks, solve.seconds),
            )
            connection.execute(
                "DELETE FROM exact_solves WHERE ordinal IN (SELECT ordinal FROM "
                "(SELECT ordinal, sum(length(payload)) OVER (ORDER BY ordinal DESC) AS total FROM exact_solves) "
                "WHERE total > ?)", (_LIMIT,),
            )
    except (OSError, sqlite3.Error):
        return  # A failed write must not interfere with advice.


def load_or_compute(path, exact_key, root_state, menu, ranges, compute):
    try:
        key = _key_digest(exact_key)
    except OSError:
        return compute()
    cached = _read(path, key, root_state, menu, ranges)
    if cached is not None:
        return cached
    solve = compute()
    _write(path, key, solve)
    return solve
