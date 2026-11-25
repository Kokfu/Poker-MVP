"""Preload the public charts and prepare exact policies for common Coach starts."""
from contextlib import asynccontextmanager
from logging import getLogger
from os import getenv
from threading import Event, Thread

from starlette.concurrency import run_in_threadpool

from .service import Spot, SpotAction, advise
from .store import HandStore, default_path


_LOG = getLogger(__name__)


def _warm_common_spots(stop: Event) -> None:
    path = default_path()
    if not path.is_file():
        return
    try:
        store = HandStore(path)
        # The Coach opens at 100bb. Precompute each seat's locked policy for
        # the most-used profiles, using the same replay and cache as requests.
        for opponent, _ in store.opponents()[:2]:
            for spot in (
                Spot(["As", "Kd"]),
                Spot(["As", "Kd"], hero_position="big_blind",
                     actions=[SpotAction("villain", "raise", 250)]),
            ):
                if stop.is_set():
                    return
                advise(spot, opponent=opponent, store=store)
    except Exception:
        _LOG.exception("Coach profile warmup failed")


@asynccontextmanager
async def coach_lifespan(app):
    app.state.coach_warmup = None
    if getenv("POKER_COACH_WARMUP") == "0":
        yield
        return
    from solver.preflop import load_charts, load_class_equity

    try:
        load_charts()
        load_class_equity()
    except (OSError, ValueError):
        _LOG.exception("Coach chart warmup failed")
        yield
        return

    stop = Event()
    worker = Thread(target=_warm_common_spots, args=(stop,), name="coach-warmup", daemon=True)
    worker.start()
    app.state.coach_warmup = worker
    try:
        yield
    finally:
        stop.set()
        await run_in_threadpool(worker.join)
