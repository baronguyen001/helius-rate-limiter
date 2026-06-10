"""Adapt the request rate to Helius pressure with AIMD instead of hard-tripping.

Wrap any limiter that exposes ``acquire()`` with :class:`AdaptiveLimiter`. On a
``429`` you call ``on_429(...)`` (honoring any ``Retry-After``); on a clean
response you call ``on_success()``. The limiter slows down multiplicatively and
recovers additively toward ``max_rate``.
"""

from __future__ import annotations

import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helius_limiter import AdaptiveLimiter, RateLimiter
from helius_limiter.backoff import parse_retry_after


def load_keys() -> list[str]:
    return [key.strip() for key in os.getenv("HELIUS_API_KEYS", "").split(",") if key.strip()]


def endpoint_with_key(api_key: str) -> str:
    base_url = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'api-key': api_key})}"


def main() -> None:
    keys = load_keys()
    if not keys:
        raise RuntimeError("set HELIUS_API_KEYS to one or more comma-separated keys")

    # Hard floor of 10 rps; AIMD shapes anything below that under pressure.
    limiter = AdaptiveLimiter(
        RateLimiter(rps=float(os.getenv("HELIUS_MAX_RPS", "10"))),
        max_rate=float(os.getenv("HELIUS_MAX_RPS", "10")),
        min_rate=0.5,
        on_event=lambda event: print(f"adaptive: {event} (rate now changing)"),
    )

    for _ in range(int(os.getenv("HELIUS_REQUESTS", "5"))):
        limiter.acquire()
        request = Request(endpoint_with_key(keys[0]), method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                print(response.status, response.read().decode("utf-8", errors="replace")[:80])
                limiter.on_success()
        except HTTPError as exc:
            if exc.code == 429:
                limiter.on_429(parse_retry_after(dict(exc.headers.items())))
            else:
                print("error", exc.code)


if __name__ == "__main__":
    main()
