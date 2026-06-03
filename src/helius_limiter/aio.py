"""Asyncio primitives for protecting Helius API usage."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from collections.abc import Callable

from .backoff import backoff_seconds, parse_retry_after
from .guard import MONTHLY_EXHAUSTION_OPEN_SECONDS
from .rotation import KeyRotator

EventCallback = Callable[[str], object]


async def _emit(callback: EventCallback | None, event: str) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


class AsyncRateLimiter:
    def __init__(self, rps: float):
        if rps <= 0:
            raise ValueError("rps must be positive")
        self.min_interval = 1.0 / rps
        self.last = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            wait = self.min_interval - (time.monotonic() - self.last)
            if wait > 0:
                await asyncio.sleep(wait)
            self.last = time.monotonic()


class AsyncQuotaTracker:
    def __init__(
        self,
        max_credits: int = 100_000,
        window_seconds: int = 30 * 86_400,
        state_path: str | None = None,
    ):
        if max_credits <= 0:
            raise ValueError("max_credits must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_credits = max_credits
        self.window_seconds = window_seconds
        self.state_path = state_path
        self.window_start = time.time()
        self.used = 0
        self.lock = asyncio.Lock()
        self._load()
        self._roll_if_needed()

    async def charge(self, credits: int = 1) -> None:
        if credits < 0:
            raise ValueError("credits must be non-negative")
        async with self.lock:
            self._roll_if_needed()
            self.used += credits
            self._persist()

    async def remaining(self) -> int:
        async with self.lock:
            self._roll_if_needed()
            return max(0, self.max_credits - self.used)

    async def is_exhausted(self) -> bool:
        async with self.lock:
            self._roll_if_needed()
            return self.used >= self.max_credits

    async def reset(self) -> None:
        async with self.lock:
            self.window_start = time.time()
            self.used = 0
            self._persist()

    def _roll_if_needed(self) -> None:
        if time.time() - self.window_start >= self.window_seconds:
            self.window_start = time.time()
            self.used = 0
            self._persist()

    def _load(self) -> None:
        if not self.state_path or not os.path.exists(self.state_path):
            return
        with open(self.state_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.window_start = float(payload.get("window_start", self.window_start))
        self.used = int(payload.get("used", 0))

    def _persist(self) -> None:
        if not self.state_path:
            return
        payload = {"window_start": self.window_start, "used": self.used}
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)


class AsyncCircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 8,
        open_seconds: int = 900,
        on_event: EventCallback | None = None,
    ):
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if open_seconds <= 0:
            raise ValueError("open_seconds must be positive")
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.on_event = on_event
        self.failures = 0
        self.open_until = 0.0
        self.lock = asyncio.Lock()

    async def record_failure(self) -> None:
        should_emit = False
        async with self.lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.open_until = time.monotonic() + self.open_seconds
                self.failures = 0
                should_emit = True
        if should_emit:
            await _emit(self.on_event, "tripped")

    async def record_success(self) -> None:
        should_emit = False
        async with self.lock:
            should_emit = self.failures != 0 or self.open_until != 0.0
            self.failures = 0
            self.open_until = 0.0
        if should_emit:
            await _emit(self.on_event, "reset")

    async def trip(self, open_seconds: int | None = None) -> None:
        seconds = self.open_seconds if open_seconds is None else open_seconds
        async with self.lock:
            self.open_until = time.monotonic() + seconds
        await _emit(self.on_event, "tripped")

    async def is_open(self) -> bool:
        async with self.lock:
            return time.monotonic() < self.open_until


class AsyncGuard:
    def __init__(
        self,
        api_keys: list[str],
        *,
        rps: float = 10.0,
        monthly_credits: int = 100_000,
        state_path: str | None = None,
        failure_threshold: int = 8,
        circuit_open_seconds: int = 900,
        on_event: EventCallback | None = None,
    ):
        self.on_event = on_event
        self.rate_limiter = AsyncRateLimiter(rps)
        self.quota = AsyncQuotaTracker(max_credits=monthly_credits, state_path=state_path)
        self.circuit = AsyncCircuitBreaker(
            failure_threshold=failure_threshold,
            open_seconds=circuit_open_seconds,
            on_event=on_event,
        )
        self.rotator = KeyRotator(api_keys)

    async def request(self, fn, *, credits: int = 1, retries: int = 3):
        """Await fn(api_key), returning its successful response or None when guarded off."""

        if await self.circuit.is_open() or await self.quota.is_exhausted():
            await _emit(self.on_event, "throttled")
            return None

        attempts = max(1, retries)
        attempt = 0
        while attempt < attempts:
            await self.rate_limiter.acquire()
            try:
                response = fn(self.rotator.current())
                if inspect.isawaitable(response):
                    response = await response
            except Exception:
                if attempt == attempts - 1:
                    return None
                await asyncio.sleep(backoff_seconds(attempt))
                attempt += 1
                continue

            status_code = int(getattr(response, "status_code", 0))
            text = str(getattr(response, "text", ""))
            headers = getattr(response, "headers", {}) or {}

            if status_code == 429:
                await _emit(self.on_event, "throttled")
                if "max usage reached" in text.lower():
                    if self.rotator.rotate():
                        await _emit(self.on_event, "rotated")
                        continue
                    await self.circuit.trip(MONTHLY_EXHAUSTION_OPEN_SECONDS)
                    return None
                await self.circuit.record_failure()
                if await self.circuit.is_open() or attempt == attempts - 1:
                    return None
                await asyncio.sleep(backoff_seconds(attempt, parse_retry_after(headers)))
                attempt += 1
                continue

            if status_code >= 500:
                if attempt == attempts - 1:
                    return None
                await asyncio.sleep(backoff_seconds(attempt, parse_retry_after(headers)))
                attempt += 1
                continue

            if status_code >= 400:
                return None

            await self.circuit.record_success()
            await self.quota.charge(credits)
            return response

        return None
