"""Convenience wrapper that wires the primitives around a user-supplied request function."""

from __future__ import annotations

import time

from .backoff import backoff_seconds, parse_retry_after
from .circuit import CircuitBreaker
from .quota import QuotaLimiter
from .rate_limiter import RateLimiter
from .rotation import KeyRotator

MONTHLY_EXHAUSTION_OPEN_SECONDS = 86_400


class HeliusGuard:
    def __init__(
        self,
        api_keys: list[str],
        *,
        rps: float = 10.0,
        monthly_credits: int = 100_000,
        state_path: str | None = None,
        failure_threshold: int = 8,
        circuit_open_seconds: int = 900,
    ):
        self.rate_limiter = RateLimiter(rps)
        self.quota = QuotaLimiter(max_credits=monthly_credits, state_path=state_path)
        self.circuit = CircuitBreaker(
            failure_threshold=failure_threshold,
            open_seconds=circuit_open_seconds,
        )
        self.rotator = KeyRotator(api_keys)

    def request(self, fn, *, credits: int = 1, retries: int = 3):
        """Call fn(api_key), returning its successful response or None when guarded off."""

        if self.circuit.is_open() or self.quota.is_exhausted():
            return None

        attempts = max(1, retries)
        attempt = 0
        while attempt < attempts:
            self.rate_limiter.acquire()
            try:
                response = fn(self.rotator.current())
            except Exception:
                if attempt == attempts - 1:
                    return None
                time.sleep(backoff_seconds(attempt))
                attempt += 1
                continue

            status_code = int(getattr(response, "status_code", 0))
            text = str(getattr(response, "text", ""))
            headers = getattr(response, "headers", {}) or {}

            if status_code == 429:
                if "max usage reached" in text.lower():
                    if self.rotator.rotate():
                        continue
                    self.circuit.trip(MONTHLY_EXHAUSTION_OPEN_SECONDS)
                    return None
                self.circuit.record_failure()
                if self.circuit.is_open() or attempt == attempts - 1:
                    return None
                time.sleep(backoff_seconds(attempt, parse_retry_after(headers)))
                attempt += 1
                continue

            if status_code >= 500:
                if attempt == attempts - 1:
                    return None
                time.sleep(backoff_seconds(attempt, parse_retry_after(headers)))
                attempt += 1
                continue

            if status_code >= 400:
                return None

            self.circuit.record_success()
            self.quota.charge(credits)
            return response

        return None
