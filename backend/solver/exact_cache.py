"""Bounded cache for exact values that are expensive to compute concurrently."""
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from threading import Lock
from typing import Generic, TypeVar


Value = TypeVar("Value")


class ExactCache(Generic[Value]):
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._values: OrderedDict[tuple, Value] = OrderedDict()
        self._pending: dict[tuple, Future[Value]] = {}
        self._lock = Lock()

    def get_or_compute(self, key: tuple, compute: Callable[[], Value]) -> Value:
        with self._lock:
            if key in self._values:
                self._values.move_to_end(key)
                return self._values[key]
            pending = self._pending.get(key)
            is_owner = pending is None
            if is_owner:
                pending = self._pending[key] = Future()
        if not is_owner:
            return pending.result()
        try:
            value = compute()
        except BaseException as error:
            with self._lock:
                del self._pending[key]
            pending.set_exception(error)
            raise
        with self._lock:
            self._values[key] = value
            if len(self._values) > self._capacity:
                self._values.popitem(last=False)
            del self._pending[key]
        pending.set_result(value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
