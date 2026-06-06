"""Token-bucket limiters for burst-friendly request shaping."""

from __future__ import annotations

import asyncio
import threading
import time


class TokenBucketLimiter:
    """Thread-safe token bucket with blocking acquire semantics."""

    def __init__(
        self,
        *,
        capacity: float,
        refill_rate: float,
        initial_tokens: float | None = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")

        tokens = capacity if initial_tokens is None else initial_tokens
        if tokens < 0 or tokens > capacity:
            raise ValueError("initial_tokens must be between 0 and capacity")

        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(tokens)
        self.updated_at = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        if tokens > self.capacity:
            raise ValueError("tokens must be less than or equal to capacity")

        with self.lock:
            while True:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                deficit = tokens - self.tokens
                time.sleep(deficit / self.refill_rate)

    def available_tokens(self) -> float:
        with self.lock:
            self._refill()
            return self.tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.updated_at
        if elapsed <= 0:
            return

        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.updated_at = now


class AsyncTokenBucketLimiter:
    """Asyncio token bucket with awaitable acquire semantics."""

    def __init__(
        self,
        *,
        capacity: float,
        refill_rate: float,
        initial_tokens: float | None = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")

        tokens = capacity if initial_tokens is None else initial_tokens
        if tokens < 0 or tokens > capacity:
            raise ValueError("initial_tokens must be between 0 and capacity")

        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(tokens)
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        if tokens > self.capacity:
            raise ValueError("tokens must be less than or equal to capacity")

        async with self.lock:
            while True:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                deficit = tokens - self.tokens
                await asyncio.sleep(deficit / self.refill_rate)

    async def available_tokens(self) -> float:
        async with self.lock:
            self._refill()
            return self.tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.updated_at
        if elapsed <= 0:
            return

        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.updated_at = now
