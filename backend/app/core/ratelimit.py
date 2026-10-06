"""Rate limiting.

`WindowLimiter`: async sliding-window limiter for outbound calls to free-tier providers (DECISIONS D-15).
`acquire(n)` waits until `n` more units fit into the last `window_s` seconds. A capacity of 0 disables it.
The per-IP / per-user limits for the public API (SPEC §9) are added in B16 on the same primitive.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable


class WindowLimiter:
    def __init__(
        self,
        capacity: int,
        window_s: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.capacity = capacity
        self.window_s = window_s
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, int]] = deque()  # (timestamp, units)
        self._used = 0
        self._lock = asyncio.Lock()

    def _expire(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= self.window_s:
            _, n = self._events.popleft()
            self._used -= n

    async def acquire(self, n: int = 1) -> float:
        """Reserve `n` units, sleeping as needed. Returns the seconds waited."""
        if self.capacity <= 0 or n <= 0:
            return 0.0
        n = min(n, self.capacity)  # a single oversized request still goes through, alone in its window
        waited = 0.0
        async with self._lock:
            while True:
                now = self._clock()
                self._expire(now)
                if self._used + n <= self.capacity:
                    self._events.append((now, n))
                    self._used += n
                    return waited
                wait = self.window_s - (now - self._events[0][0]) + 0.01
                await self._sleep(wait)
                waited += wait


class KeyedLimiter:
    """Non-blocking per-key limit (e.g. 20 requests / minute per IP). `hit(key)` -> seconds to wait, 0 if allowed."""

    def __init__(self, capacity: int, window_s: float = 60.0, *, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 50_000) -> None:
        self.capacity = capacity
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._max_keys = max_keys

    def hit(self, key: str) -> float:
        if self.capacity <= 0:
            return 0.0
        now = self._clock()
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self._max_keys:  # bound memory: drop the oldest keys
                for k in list(self._hits)[: self._max_keys // 10]:
                    del self._hits[k]
            q = self._hits[key] = deque()
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.capacity:
            return max(0.0, self.window_s - (now - q[0]))
        q.append(now)
        return 0.0
