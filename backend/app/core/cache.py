"""In-process LRU for identical /check texts (SPEC §7.7): size 256, entries expire after the result TTL."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    def __init__(self, maxsize: int = 256, ttl_s: float = 24 * 3600) -> None:
        self.maxsize = maxsize
        self.ttl_s = ttl_s
        self._d: OrderedDict[str, tuple[float, V]] = OrderedDict()

    def get(self, key: str) -> V | None:
        item = self._d.get(key)
        if item is None:
            return None
        ts, value = item
        if time.monotonic() - ts > self.ttl_s:
            del self._d[key]
            return None
        self._d.move_to_end(key)
        return value

    def put(self, key: str, value: V) -> None:
        self._d[key] = (time.monotonic(), value)
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)

    def clear(self) -> None:
        self._d.clear()
