"""In-flight request caps for sync and asyncio callers."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable

EventCallback = Callable[[str], object]


class ConcurrencyLimiter:
    """Thread-safe semaphore-style cap on concurrent in-flight work."""

    def __init__(self, max_concurrency: int, on_event: EventCallback | None = None):
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self.max_concurrency = max_concurrency
        self.on_event = on_event
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self._lock = threading.Lock()
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        with self._lock:
            saturated = self._in_flight >= self.max_concurrency
        if saturated:
            self._emit("saturated")

        if timeout is None:
            acquired = self._semaphore.acquire(blocking=blocking)
        else:
            acquired = self._semaphore.acquire(blocking=blocking, timeout=timeout)
        if not acquired:
            return False

        with self._lock:
            self._in_flight += 1
        self._emit("acquired")
        return True

    def release(self) -> None:
        self._semaphore.release()
        with self._lock:
            self._in_flight -= 1
        self._emit("released")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def _emit(self, event: str) -> None:
        if self.on_event is not None:
            self.on_event(event)


class AsyncConcurrencyLimiter:
    """Asyncio mirror of :class:`ConcurrencyLimiter`."""

    def __init__(self, max_concurrency: int, on_event: EventCallback | None = None):
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self.max_concurrency = max_concurrency
        self.on_event = on_event
        self._semaphore = asyncio.BoundedSemaphore(max_concurrency)
        self._lock = asyncio.Lock()
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def acquire(self, *, timeout: float | None = None) -> bool:
        if self._semaphore.locked():
            await self._emit("saturated")

        try:
            if timeout is None:
                await self._semaphore.acquire()
            else:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except TimeoutError:
            return False

        async with self._lock:
            self._in_flight += 1
        await self._emit("acquired")
        return True

    async def release(self) -> None:
        self._semaphore.release()
        async with self._lock:
            self._in_flight -= 1
        await self._emit("released")

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def _emit(self, event: str) -> None:
        if self.on_event is None:
            return
        result = self.on_event(event)
        if inspect.isawaitable(result):
            await result
