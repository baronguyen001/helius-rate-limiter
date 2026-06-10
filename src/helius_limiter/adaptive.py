"""AIMD adaptive rate control around any existing limiter.

Helius free tier is credit-capped, so a single hard 429 should *slow you down*,
not trip the whole circuit. :class:`AdaptiveLimiter` wraps any limiter that
exposes ``acquire()`` and applies AIMD (additive-increase / multiplicative-
decrease) on top of it:

* on a ``429`` / ``"max usage reached"`` signal it multiplicatively cuts the
  allowed rate (``rate *= decrease_factor``) and, if the server sent a
  ``Retry-After``, sleeps that long before the next request;
* on sustained success it additively recovers (``rate += increase_step``) up to
  a configured ceiling.

It emits ``on_event`` callbacks: ``"backed_off"`` when the rate is cut and
``"recovered"`` when it is increased. The wrapped limiter still runs as a hard
floor, so the adaptive layer can only ever make you *slower*, never faster than
the primitive you trust. stdlib only.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Callable

EventCallback = Callable[[str], object]


def _next_rate_after_decrease(rate: float, factor: float, min_rate: float) -> float:
    return max(min_rate, rate * factor)


def _next_rate_after_increase(rate: float, step: float, max_rate: float) -> float:
    return min(max_rate, rate + step)


class _AIMDState:
    """Shared AIMD math so the sync and async limiters stay identical."""

    def __init__(
        self,
        *,
        max_rate: float,
        min_rate: float,
        start_rate: float | None,
        decrease_factor: float,
        increase_step: float,
        success_threshold: int,
    ):
        if max_rate <= 0:
            raise ValueError("max_rate must be positive")
        if min_rate <= 0:
            raise ValueError("min_rate must be positive")
        if min_rate > max_rate:
            raise ValueError("min_rate must be <= max_rate")
        if not 0.0 < decrease_factor < 1.0:
            raise ValueError("decrease_factor must be in (0, 1)")
        if increase_step <= 0:
            raise ValueError("increase_step must be positive")
        if success_threshold <= 0:
            raise ValueError("success_threshold must be positive")

        self.max_rate = float(max_rate)
        self.min_rate = float(min_rate)
        self.decrease_factor = float(decrease_factor)
        self.increase_step = float(increase_step)
        self.success_threshold = int(success_threshold)

        initial = self.max_rate if start_rate is None else float(start_rate)
        self.rate = min(self.max_rate, max(self.min_rate, initial))
        self.successes = 0

    @property
    def min_interval(self) -> float:
        return 1.0 / self.rate

    def register_429(self) -> bool:
        """Multiplicatively cut the rate. Returns True if the rate changed."""

        self.successes = 0
        new_rate = _next_rate_after_decrease(self.rate, self.decrease_factor, self.min_rate)
        changed = new_rate != self.rate
        self.rate = new_rate
        return changed

    def register_success(self) -> bool:
        """Count a success; additively increase once the streak is reached.

        Returns True when the rate was actually increased this call.
        """

        if self.rate >= self.max_rate:
            self.successes = 0
            return False
        self.successes += 1
        if self.successes < self.success_threshold:
            return False
        self.successes = 0
        new_rate = _next_rate_after_increase(self.rate, self.increase_step, self.max_rate)
        changed = new_rate != self.rate
        self.rate = new_rate
        return changed


class AdaptiveLimiter:
    """Thread-safe AIMD wrapper around a sync limiter exposing ``acquire()``."""

    def __init__(
        self,
        limiter,
        *,
        max_rate: float,
        min_rate: float = 0.5,
        start_rate: float | None = None,
        decrease_factor: float = 0.5,
        increase_step: float = 1.0,
        success_threshold: int = 5,
        on_event: EventCallback | None = None,
    ):
        self.limiter = limiter
        self.on_event = on_event
        self._state = _AIMDState(
            max_rate=max_rate,
            min_rate=min_rate,
            start_rate=start_rate,
            decrease_factor=decrease_factor,
            increase_step=increase_step,
            success_threshold=success_threshold,
        )
        self._lock = threading.Lock()
        self._last = 0.0

    @property
    def rate(self) -> float:
        with self._lock:
            return self._state.rate

    def acquire(self) -> None:
        """Run the wrapped limiter, then space to the current adaptive rate."""

        self.limiter.acquire()
        with self._lock:
            wait = self._state.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def on_429(self, retry_after: float | None = None) -> None:
        with self._lock:
            changed = self._state.register_429()
        if changed:
            self._emit("backed_off")
        if retry_after is not None and retry_after > 0:
            time.sleep(retry_after)

    def on_success(self) -> None:
        with self._lock:
            changed = self._state.register_success()
        if changed:
            self._emit("recovered")

    def _emit(self, event: str) -> None:
        if self.on_event is not None:
            self.on_event(event)


class AsyncAdaptiveLimiter:
    """Asyncio mirror of :class:`AdaptiveLimiter`."""

    def __init__(
        self,
        limiter,
        *,
        max_rate: float,
        min_rate: float = 0.5,
        start_rate: float | None = None,
        decrease_factor: float = 0.5,
        increase_step: float = 1.0,
        success_threshold: int = 5,
        on_event: EventCallback | None = None,
    ):
        self.limiter = limiter
        self.on_event = on_event
        self._state = _AIMDState(
            max_rate=max_rate,
            min_rate=min_rate,
            start_rate=start_rate,
            decrease_factor=decrease_factor,
            increase_step=increase_step,
            success_threshold=success_threshold,
        )
        self._lock = asyncio.Lock()
        self._last = 0.0

    @property
    def rate(self) -> float:
        return self._state.rate

    async def acquire(self) -> None:
        result = self.limiter.acquire()
        if inspect.isawaitable(result):
            await result
        async with self._lock:
            wait = self._state.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def on_429(self, retry_after: float | None = None) -> None:
        async with self._lock:
            changed = self._state.register_429()
        if changed:
            await self._emit("backed_off")
        if retry_after is not None and retry_after > 0:
            await asyncio.sleep(retry_after)

    async def on_success(self) -> None:
        async with self._lock:
            changed = self._state.register_success()
        if changed:
            await self._emit("recovered")

    async def _emit(self, event: str) -> None:
        if self.on_event is None:
            return
        result = self.on_event(event)
        if inspect.isawaitable(result):
            await result
