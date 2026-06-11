"""Use an httpx transport with limiter, circuit breaker, and Retry-After backoff."""

from __future__ import annotations

import os

import httpx

from helius_limiter import HttpxLimiterTransport

HELIUS_URL = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
API_KEY = os.getenv("HELIUS_API_KEY", "")


def on_event(event: str) -> None:
    print(f"limiter event: {event}")


transport = HttpxLimiterTransport(rps=float(os.getenv("HELIUS_RPS", "10")), on_event=on_event)

with httpx.Client(transport=transport, timeout=20) as client:
    response = client.get(HELIUS_URL, params={"api-key": API_KEY})
    print(response.status_code)
