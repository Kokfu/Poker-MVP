from threading import Event
from time import sleep

import anyio
import pytest

from coach.advisor import CoachAdvisor
from coach.speculation import StaleSpeculation, speculate


def test_speculation_drops_concurrent_work_and_observes_disconnect(monkeypatch):
    monkeypatch.delenv("POKER_COACH_SOLVE_CACHE", raising=False)
    started = Event()
    disconnected = Event()

    class Request:
        async def is_disconnected(self):
            return disconnected.is_set()

    def solve(cancelled):
        started.set()
        for _ in range(200):
            if cancelled():
                raise StaleSpeculation
            sleep(0.01)
        pytest.fail("disconnection never reached the solver")

    def should_not_run(_):
        pytest.fail("a second speculative solve occupied the slot")

    async def run():
        result = []

        async def first():
            result.append((await speculate(Request(), solve)).status_code)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(first)
            try:
                assert await anyio.to_thread.run_sync(started.wait, 2)
                assert (await speculate(Request(), should_not_run)).status_code == 204
            finally:
                disconnected.set()
        assert result == [204]

    anyio.run(run)


def test_stale_speculation_stops_before_joining_the_preflop_cache():
    advisor = CoachAdvisor(seed=0, exploit=False, cache_solves=True, cancelled=lambda: True)
    with pytest.raises(StaleSpeculation):
        advisor._preflop_policy(100, 0, {})
