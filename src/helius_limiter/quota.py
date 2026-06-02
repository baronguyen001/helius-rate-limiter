"""Monthly credit-window tracking with optional JSON persistence."""

from __future__ import annotations

import json
import os
import time


class QuotaLimiter:
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
        self._load()
        self._roll_if_needed()

    def charge(self, credits: int = 1) -> None:
        if credits < 0:
            raise ValueError("credits must be non-negative")
        self._roll_if_needed()
        self.used += credits
        self._persist()

    def remaining(self) -> int:
        self._roll_if_needed()
        return max(0, self.max_credits - self.used)

    def is_exhausted(self) -> bool:
        self._roll_if_needed()
        return self.used >= self.max_credits

    def reset(self) -> None:
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
