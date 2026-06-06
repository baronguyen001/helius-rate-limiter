"""Expose HeliusGuard event metrics for Prometheus scraping."""

from __future__ import annotations

import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helius_limiter import HeliusGuard, PrometheusExporter


class Response:
    def __init__(self, status_code: int, text: str, headers: dict[str, str]):
        self.status_code = status_code
        self.text = text
        self.headers = headers


def load_keys() -> list[str]:
    return [key.strip() for key in os.getenv("HELIUS_API_KEYS", "").split(",") if key.strip()]


def endpoint_with_key(api_key: str) -> str:
    base_url = os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'api-key': api_key})}"


def call(api_key: str) -> Response:
    request = Request(endpoint_with_key(api_key), method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return Response(response.status, body, dict(response.headers.items()))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return Response(exc.code, body, dict(exc.headers.items()))


def main() -> None:
    keys = load_keys()
    if not keys:
        raise RuntimeError("set HELIUS_API_KEYS to one or more comma-separated keys")

    exporter = PrometheusExporter()
    exporter.start_http_server(port=int(os.getenv("PROMETHEUS_PORT", "8000")))

    guard = HeliusGuard(
        keys,
        state_path=os.getenv("HELIUS_STATE_PATH", "helius_state.json"),
        on_event=exporter.on_event,
    )
    response = guard.request(call, credits=int(os.getenv("HELIUS_CREDITS", "1")))
    if response is not None:
        print(response.status_code, response.text[:120])


if __name__ == "__main__":
    main()
