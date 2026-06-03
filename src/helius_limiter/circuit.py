"""Consecutive-failure circuit breaker."""

from __future__ import annotations

import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 8,
        open_seconds: int = 900,
        on_event: Callable[[str], None] | None = None,
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

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.trip(self.open_seconds)
            self.failures = 0

    def record_success(self) -> None:
        should_emit = self.failures != 0 or self.open_until != 0.0
        self.failures = 0
        self.open_until = 0.0
        if should_emit:
            self._emit("reset")

    def trip(self, open_seconds: int | None = None) -> None:
        seconds = self.open_seconds if open_seconds is None else open_seconds
        self.open_until = time.monotonic() + seconds
        self._emit("tripped")

    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def _emit(self, event: str) -> None:
        if self.on_event is not None:
            self.on_event(event)
