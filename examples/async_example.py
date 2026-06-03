"""Wrap an async Helius workflow with AsyncGuard."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helius_limiter.aio import AsyncGuard


@dataclass
class Response:
    status_code: int
    text: str
    headers: dict[str, str]


def load_keys() -> list[str]:
    return [key.strip() for key in os.getenv("HELIUS_API_KEYS", "").split(",") if key.strip()]


def endpoint_with_key(api_key: str) -> str:
    base_url = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'api-key': api_key})}"


def fetch(api_key: str) -> Response:
    request = Request(endpoint_with_key(api_key), method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return Response(response.status, body, dict(response.headers.items()))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return Response(exc.code, body, dict(exc.headers.items()))


async def call(api_key: str) -> Response:
    return await asyncio.to_thread(fetch, api_key)


async def main() -> None:
    keys = load_keys()
    if not keys:
        raise RuntimeError("set HELIUS_API_KEYS to one or more comma-separated keys")

    guard = AsyncGuard(keys, state_path=os.getenv("HELIUS_STATE_PATH", "helius_state.json"))
    response = await guard.request(call, credits=int(os.getenv("HELIUS_CREDITS", "1")))
    if response is not None:
        print(response.status_code, response.text[:120])


if __name__ == "__main__":
    asyncio.run(main())
