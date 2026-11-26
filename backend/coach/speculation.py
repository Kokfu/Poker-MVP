"""Limit speculative Coach work and stop stale replay at solve boundaries."""

from os import getenv
from threading import Event, Lock

from anyio import create_task_group, sleep
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response


_PREFETCH = Lock()


class StaleSpeculation(Exception):
    pass


async def speculate(request, solve):
    if getenv("POKER_COACH_SOLVE_CACHE") == "0" or not _PREFETCH.acquire(blocking=False):
        return Response(status_code=204)
    disconnected = Event()

    async def watch_disconnect():
        while not await request.is_disconnected():
            await sleep(0.05)
        disconnected.set()

    try:
        async with create_task_group() as tasks:
            tasks.start_soon(watch_disconnect)
            try:
                await run_in_threadpool(solve, disconnected.is_set)
            except (StaleSpeculation, HTTPException):
                pass
            finally:
                tasks.cancel_scope.cancel()
        return Response(status_code=204)
    finally:
        _PREFETCH.release()
