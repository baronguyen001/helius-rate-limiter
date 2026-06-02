"""Wrap any sync HTTP client with HeliusGuard."""

from __future__ import annotations

import os

import requests

from helius_limiter import HeliusGuard


def load_keys() -> list[str]:
    return [key.strip() for key in os.getenv("HELIUS_API_KEYS", "").split(",") if key.strip()]


guard = HeliusGuard(load_keys(), state_path="helius_state.json")


def call(api_key: str):
    return requests.get(
        os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint"),
        params={"api-key": api_key},
        timeout=20,
    )


response = guard.request(call, credits=1)
if response is not None:
    print(response.status_code, response.text[:120])
