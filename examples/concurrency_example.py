"""Limit concurrent in-flight Helius calls separately from RPS."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import requests

from helius_limiter import ConcurrencyLimiter, RateLimiter

HELIUS_URL = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
API_KEY = os.getenv("HELIUS_API_KEY", "")

rate = RateLimiter(rps=float(os.getenv("HELIUS_RPS", "10")))
concurrency = ConcurrencyLimiter(max_concurrency=int(os.getenv("HELIUS_CONCURRENCY", "4")))


def call_helius(payload: dict):
    rate.acquire()
    with concurrency:
        return requests.post(
            HELIUS_URL,
            params={"api-key": API_KEY},
            json=payload,
            timeout=20,
        )


if __name__ == "__main__":
    payloads = [{"id": i} for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        for response in pool.map(call_helius, payloads):
            print(response.status_code)
