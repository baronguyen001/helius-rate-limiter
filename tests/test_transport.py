from types import SimpleNamespace

import pytest

from helius_limiter import transport
from helius_limiter.transport import (
    CircuitOpenError,
    HttpxLimiterTransport,
    RequestsLimiterAdapter,
    TransportUnavailableError,
)


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.closed = False

    def close(self):
        self.closed = True


class FakeHttpxTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = False

    def handle_request(self, request):
        self.requests.append(request)
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def test_httpx_transport_retries_429_with_retry_after(monkeypatch):
    first = FakeResponse(429, "slow down", {"Retry-After": "2"})
    second = FakeResponse(200, "ok")
    fake_transport = FakeHttpxTransport([first, second])

    class FakeHTTPTransport:
        def __new__(cls):
            return fake_transport

    fake_httpx = SimpleNamespace(HTTPTransport=FakeHTTPTransport)
    monkeypatch.setattr(transport.importlib, "import_module", lambda name: fake_httpx)
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(transport, "backoff_seconds", lambda attempt, retry_after: retry_after)

    events: list[str] = []
    limiter = FakeLimiter()
    wrapper = HttpxLimiterTransport(limiter=limiter, retries=2, on_event=events.append)

    response = wrapper.handle_request(object())

    assert response is second
    assert first.closed
    assert len(fake_transport.requests) == 2
    assert limiter.calls == 2
    assert events == ["throttled", "reset"]


def test_httpx_transport_has_clear_error_without_httpx(monkeypatch):
    def missing(name):
        raise ImportError(name)

    monkeypatch.setattr(transport.importlib, "import_module", missing)

    with pytest.raises(TransportUnavailableError, match="helius-rate-limiter\\[httpx\\]"):
        HttpxLimiterTransport()


def test_httpx_transport_open_circuit_skips_request():
    fake_transport = FakeHttpxTransport([FakeResponse(200)])
    wrapper = HttpxLimiterTransport(transport=fake_transport)
    wrapper.circuit.trip(60)

    with pytest.raises(CircuitOpenError):
        wrapper.handle_request(object())

    assert fake_transport.requests == []


def test_requests_adapter_fallback_wraps_existing_adapter():
    class FakeAdapter:
        def __init__(self):
            self.requests = []

        def send(self, request, **kwargs):
            self.requests.append((request, kwargs))
            return FakeResponse(200)

    limiter = FakeLimiter()
    adapter = FakeAdapter()
    wrapper = RequestsLimiterAdapter(limiter=limiter, adapter=adapter)

    response = wrapper.send("request", timeout=20)

    assert response.status_code == 200
    assert adapter.requests == [("request", {"timeout": 20})]
    assert limiter.calls == 1
