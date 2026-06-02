"""Thread-safe sync RPS spacing."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, rps: float):
        if rps <= 0:
            raise ValueError("rps must be positive")
        self.min_interval = 1.0 / rps
        self.last = 0.0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            wait = self.min_interval - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
