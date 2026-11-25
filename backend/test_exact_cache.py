from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event

import pytest

from solver.exact_cache import ExactCache


@pytest.mark.parametrize("fails", [False, True])
def test_same_key_shares_the_result_or_error_while_other_keys_progress(monkeypatch, fails):
    cache = ExactCache[str](2)
    entered, waiting, release = Event(), Event(), Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout)

    monkeypatch.setattr("solver.exact_cache.Future", ObservedFuture)

    def compute():
        entered.set()
        assert release.wait(10)
        if fails:
            raise ValueError("failed fill")
        return "exact"

    def duplicate():
        pytest.fail("a second caller tried to compute the same key")

    with ThreadPoolExecutor(max_workers=3) as workers:
        original = workers.submit(cache.get_or_compute, ("shared",), compute)
        try:
            assert entered.wait(10)
            joined = workers.submit(cache.get_or_compute, ("shared",), duplicate)
            assert waiting.wait(10)
            other = workers.submit(cache.get_or_compute, ("other",), lambda: "independent")
            assert other.result(timeout=10) == "independent"
        finally:
            release.set()
        if fails:
            for result in (original, joined):
                with pytest.raises(ValueError, match="failed fill"):
                    result.result(timeout=10)
            assert cache.get_or_compute(("shared",), lambda: "recovered") == "recovered"
        else:
            assert original.result(timeout=10) == joined.result(timeout=10) == "exact"
            assert cache.get_or_compute(("shared",), duplicate) == "exact"


def test_exact_cache_evicts_oldest_and_can_clear_values():
    cache = ExactCache[str](2)

    for key in ("a", "b"):
        assert cache.get_or_compute((key,), lambda: key) == key
    assert cache.get_or_compute(("a",), lambda: "recomputed") == "a"
    assert cache.get_or_compute(("c",), lambda: "c") == "c"
    assert cache.get_or_compute(("b",), lambda: "recomputed") == "recomputed"

    cache.clear()
    assert cache.get_or_compute(("b",), lambda: "new") == "new"
