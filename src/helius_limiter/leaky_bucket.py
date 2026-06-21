"""Leaky-bucket limiters for smoothing bursty traffic to a steady drain rate.

Where the token bucket *accumulates* allowance (burst-friendly), the leaky bucket
*drains* a queue at a constant rate: requests add to a level that leaks away over
time, and the level is capped so excess is either rejected (``try_acquire``) or
waited out (``acquire``). The clock and sleep are injectable so the behaviour is
fully deterministic in tests — no real ``time.sleep`` required.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable


def _validate(rate: float, capacity: float) -> None:
    if rate <= 0:
        raise ValueError("rate must be positive")
    if capacity <= 0:
        raise ValueError("capacity must be positive")


class LeakyBucketLimiter:
    """Thread-safe leaky bucket. ``rate`` leaks/sec, ``capacity`` max queue depth."""

    def __init__(
        self,
        *,
        rate: float,
        capacity: float,
        time_func: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], None] = time.sleep,
    ):
        _validate(rate, capacity)
        self.rate = float(rate)
        self.capacity = float(capacity)
        self._time = time_func
        self._sleep = sleep_func
        self.level = 0.0
        self.updated_at = time_func()
        self.lock = threading.Lock()

    def _leak(self) -> None:
        now = self._time()
        elapsed = now - self.updated_at
        if elapsed > 0:
            self.level = max(0.0, self.level - elapsed * self.rate)
            self.updated_at = now

    def try_acquire(self, amount: float = 1.0) -> bool:
        """Add ``amount`` if it fits under capacity; return ``False`` without waiting."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self.lock:
            self._leak()
            if self.level + amount <= self.capacity:
                self.level += amount
                return True
            return False

    def acquire(self, amount: float = 1.0) -> None:
        """Block until ``amount`` fits, then add it."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > self.capacity:
            raise ValueError("amount must be <= capacity")
        with self.lock:
            while True:
                self._leak()
                if self.level + amount <= self.capacity:
                    self.level += amount
                    return
                overflow = self.level + amount - self.capacity
                self._sleep(overflow / self.rate)

    def water_level(self) -> float:
        with self.lock:
            self._leak()
            return self.level


class AsyncLeakyBucketLimiter:
    """Asyncio leaky bucket with an awaitable :meth:`acquire`."""

    def __init__(
        self,
        *,
        rate: float,
        capacity: float,
        time_func: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], asyncio.Future[None] | None] | None = None,
    ):
        _validate(rate, capacity)
        self.rate = float(rate)
        self.capacity = float(capacity)
        self._time = time_func
        self._sleep = sleep_func or asyncio.sleep
        self.level = 0.0
        self.updated_at = time_func()
        self.lock = asyncio.Lock()

    def _leak(self) -> None:
        now = self._time()
        elapsed = now - self.updated_at
        if elapsed > 0:
            self.level = max(0.0, self.level - elapsed * self.rate)
            self.updated_at = now

    async def try_acquire(self, amount: float = 1.0) -> bool:
        if amount <= 0:
            raise ValueError("amount must be positive")
        async with self.lock:
            self._leak()
            if self.level + amount <= self.capacity:
                self.level += amount
                return True
            return False

    async def acquire(self, amount: float = 1.0) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > self.capacity:
            raise ValueError("amount must be <= capacity")
        async with self.lock:
            while True:
                self._leak()
                if self.level + amount <= self.capacity:
                    self.level += amount
                    return
                overflow = self.level + amount - self.capacity
                await self._sleep(overflow / self.rate)

    async def water_level(self) -> float:
        async with self.lock:
            self._leak()
            return self.level
