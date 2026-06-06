"""Optional Prometheus metrics adapter for limiter event callbacks."""

from __future__ import annotations

import importlib
import time
from typing import Any

INSTALL_MESSAGE = (
    "prometheus_client is required for PrometheusExporter. "
    "Install it with `pip install helius-rate-limiter[prometheus]`."
)


class PrometheusUnavailableError(RuntimeError):
    """Raised when PrometheusExporter is used without prometheus_client installed."""


def _load_prometheus_client() -> Any:
    try:
        return importlib.import_module("prometheus_client")
    except ImportError as exc:
        raise PrometheusUnavailableError(INSTALL_MESSAGE) from exc


class PrometheusExporter:
    """Prometheus callback sink for HeliusGuard and CircuitBreaker events."""

    def __init__(self, *, namespace: str = "helius_limiter", registry: Any | None = None):
        if not namespace:
            raise ValueError("namespace must not be empty")

        self._client = _load_prometheus_client()
        self._registry = registry
        kwargs = {"registry": registry} if registry is not None else {}

        self.events_total = self._client.Counter(
            f"{namespace}_events_total",
            "Helius limiter events observed.",
            ["event"],
            **kwargs,
        )
        self.circuit_open = self._client.Gauge(
            f"{namespace}_circuit_open",
            "Whether the Helius limiter circuit is currently open.",
            **kwargs,
        )
        self.last_event_timestamp = self._client.Gauge(
            f"{namespace}_last_event_timestamp_seconds",
            "Unix timestamp of the most recent Helius limiter event.",
            ["event"],
            **kwargs,
        )

    def on_event(self, event: str) -> None:
        self.events_total.labels(event=event).inc()
        self.last_event_timestamp.labels(event=event).set(time.time())

        if event == "tripped":
            self.circuit_open.set(1)
        elif event == "reset":
            self.circuit_open.set(0)

    def start_http_server(self, port: int = 8000, *, addr: str = "") -> None:
        kwargs = {"registry": self._registry} if self._registry is not None else {}
        self._client.start_http_server(port, addr=addr, **kwargs)
