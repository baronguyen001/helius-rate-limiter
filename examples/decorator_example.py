"""Compose rate, circuit, and quota decorators around a sync Helius call."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helius_limiter import CircuitBreaker, QuotaLimiter, RateLimiter
from helius_limiter.decorators import rate_limited, with_circuit, with_quota


@dataclass
class Response:
    status_code: int
    text: str
    headers: dict[str, str]


def endpoint_with_key(api_key: str) -> str:
    base_url = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'api-key': api_key})}"


limiter = RateLimiter(rps=float(os.getenv("HELIUS_RPS", "10")))
quota = QuotaLimiter(
    max_credits=int(os.getenv("HELIUS_MONTHLY_CREDITS", "100000")),
    state_path=os.getenv("HELIUS_STATE_PATH", "helius_state.json"),
)
circuit = CircuitBreaker()
credits = int(os.getenv("HELIUS_CREDITS", "1"))


@rate_limited(limiter)
@with_circuit(circuit)
@with_quota(quota, credits=credits)
def call(api_key: str) -> Response:
    request = Request(endpoint_with_key(api_key), method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return Response(response.status, body, dict(response.headers.items()))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return Response(exc.code, body, dict(exc.headers.items()))


api_key = os.environ["HELIUS_API_KEY"]
response = call(api_key)
if response is not None:
    print(response.status_code, response.text[:120])
