"""Optional HTTP transports with limiter, circuit, and backoff built in."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import time
from collections.abc import Callable

from .aio import AsyncCircuitBreaker, AsyncRateLimiter
from .backoff import backoff_seconds, parse_retry_after
from .circuit import CircuitBreaker
from .guard import MONTHLY_EXHAUSTION_OPEN_SECONDS
from .rate_limiter import RateLimiter

EventCallback = Callable[[str], object]


class TransportUnavailableError(ImportError):
    """Raised when an optional HTTP client is not installed."""


class CircuitOpenError(RuntimeError):
    """Raised when the baked-in circuit is open and a request is skipped."""


def _load_optional(module: str, extra: str | None = None):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        install = f"helius-rate-limiter[{extra}]" if extra else module
        raise TransportUnavailableError(f"Install {install} to use this transport.") from exc


def _emit(callback: EventCallback | None, event: str) -> None:
    if callback is not None:
        callback(event)


async def _emit_async(callback: EventCallback | None, event: str) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


def _status_code(response) -> int:
    return int(getattr(response, "status_code", 0))


def _response_text(response) -> str:
    try:
        return str(getattr(response, "text", ""))
    except Exception:
        return ""


def _response_headers(response) -> dict:
    return getattr(response, "headers", {}) or {}


def _close_response(response) -> None:
    close = getattr(response, "close", None)
    if close is not None:
        close()


async def _aclose_response(response) -> None:
    close = getattr(response, "aclose", None)
    if close is not None:
        result = close()
        if inspect.isawaitable(result):
            await result
        return
    _close_response(response)


class HttpxLimiterTransport:
    """``httpx`` transport wrapper that applies rate limiting and circuit backoff."""

    def __init__(
        self,
        *,
        limiter=None,
        circuit: CircuitBreaker | None = None,
        transport=None,
        rps: float = 10.0,
        retries: int = 3,
        on_event: EventCallback | None = None,
    ):
        if retries <= 0:
            raise ValueError("retries must be positive")
        self.on_event = on_event
        self.limiter = limiter if limiter is not None else RateLimiter(rps)
        self.circuit = circuit if circuit is not None else CircuitBreaker(on_event=on_event)
        self.retries = retries
        if transport is None:
            httpx = _load_optional("httpx", "httpx")
            transport = httpx.HTTPTransport()
        self.transport = transport

    def handle_request(self, request):
        if self.circuit.is_open():
            _emit(self.on_event, "throttled")
            raise CircuitOpenError("circuit is open")

        attempts = max(1, self.retries)
        for attempt in range(attempts):
            self.limiter.acquire()
            response = self.transport.handle_request(request)
            status_code = _status_code(response)

            if status_code == 429:
                _emit(self.on_event, "throttled")
                if "max usage reached" in _response_text(response).lower():
                    self.circuit.trip(MONTHLY_EXHAUSTION_OPEN_SECONDS)
                    return response
                self.circuit.record_failure()
                if self.circuit.is_open() or attempt == attempts - 1:
                    return response
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                _close_response(response)
                time.sleep(delay)
                continue

            if status_code >= 500 and attempt < attempts - 1:
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                _close_response(response)
                time.sleep(delay)
                continue

            if status_code < 400:
                self.circuit.record_success()
            return response

        return response

    def close(self) -> None:
        close = getattr(self.transport, "close", None)
        if close is not None:
            close()


class AsyncHttpxLimiterTransport:
    """Async ``httpx`` transport wrapper for ``httpx.AsyncClient``."""

    def __init__(
        self,
        *,
        limiter=None,
        circuit: AsyncCircuitBreaker | None = None,
        transport=None,
        rps: float = 10.0,
        retries: int = 3,
        on_event: EventCallback | None = None,
    ):
        if retries <= 0:
            raise ValueError("retries must be positive")
        self.on_event = on_event
        self.limiter = limiter if limiter is not None else AsyncRateLimiter(rps)
        self.circuit = circuit if circuit is not None else AsyncCircuitBreaker(on_event=on_event)
        self.retries = retries
        if transport is None:
            httpx = _load_optional("httpx", "httpx")
            transport = httpx.AsyncHTTPTransport()
        self.transport = transport

    async def handle_async_request(self, request):
        if await self.circuit.is_open():
            await _emit_async(self.on_event, "throttled")
            raise CircuitOpenError("circuit is open")

        attempts = max(1, self.retries)
        for attempt in range(attempts):
            result = self.limiter.acquire()
            if inspect.isawaitable(result):
                await result
            response = await self.transport.handle_async_request(request)
            status_code = _status_code(response)

            if status_code == 429:
                await _emit_async(self.on_event, "throttled")
                if "max usage reached" in _response_text(response).lower():
                    await self.circuit.trip(MONTHLY_EXHAUSTION_OPEN_SECONDS)
                    return response
                await self.circuit.record_failure()
                if await self.circuit.is_open() or attempt == attempts - 1:
                    return response
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                await _aclose_response(response)
                await asyncio.sleep(delay)
                continue

            if status_code >= 500 and attempt < attempts - 1:
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                await _aclose_response(response)
                await asyncio.sleep(delay)
                continue

            if status_code < 400:
                await self.circuit.record_success()
            return response

        return response

    async def aclose(self) -> None:
        close = getattr(self.transport, "aclose", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


class RequestsLimiterAdapter:
    """``requests`` adapter wrapper with the same limiter/circuit behavior."""

    def __init__(
        self,
        *,
        limiter=None,
        circuit: CircuitBreaker | None = None,
        adapter=None,
        rps: float = 10.0,
        retries: int = 3,
        on_event: EventCallback | None = None,
    ):
        if retries <= 0:
            raise ValueError("retries must be positive")
        self.on_event = on_event
        self.limiter = limiter if limiter is not None else RateLimiter(rps)
        self.circuit = circuit if circuit is not None else CircuitBreaker(on_event=on_event)
        self.retries = retries
        if adapter is None:
            requests = _load_optional("requests")
            adapter = requests.adapters.HTTPAdapter()
        self.adapter = adapter

    def send(self, request, **kwargs):
        if self.circuit.is_open():
            _emit(self.on_event, "throttled")
            raise CircuitOpenError("circuit is open")

        attempts = max(1, self.retries)
        for attempt in range(attempts):
            self.limiter.acquire()
            response = self.adapter.send(request, **kwargs)
            status_code = _status_code(response)

            if status_code == 429:
                _emit(self.on_event, "throttled")
                if "max usage reached" in _response_text(response).lower():
                    self.circuit.trip(MONTHLY_EXHAUSTION_OPEN_SECONDS)
                    return response
                self.circuit.record_failure()
                if self.circuit.is_open() or attempt == attempts - 1:
                    return response
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                _close_response(response)
                time.sleep(delay)
                continue

            if status_code >= 500 and attempt < attempts - 1:
                delay = backoff_seconds(attempt, parse_retry_after(_response_headers(response)))
                _close_response(response)
                time.sleep(delay)
                continue

            if status_code < 400:
                self.circuit.record_success()
            return response

        return response

    def close(self) -> None:
        close = getattr(self.adapter, "close", None)
        if close is not None:
            close()
