"""Use TokenBucketLimiter when short bursts are acceptable."""

from __future__ import annotations

import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helius_limiter import TokenBucketLimiter


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

    limiter = TokenBucketLimiter(
        capacity=float(os.getenv("HELIUS_BUCKET_CAPACITY", "20")),
        refill_rate=float(os.getenv("HELIUS_BUCKET_REFILL_RATE", "10")),
    )

    limiter.acquire()
    request = Request(endpoint_with_key(keys[0]), method="GET")
    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        print(response.status, body[:120])


if __name__ == "__main__":
    main()
