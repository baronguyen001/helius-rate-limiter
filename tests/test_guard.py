from dataclasses import dataclass, field

from helius_limiter import guard
from helius_limiter.guard import HeliusGuard


@dataclass
class Response:
    status_code: int
    text: str = ""
    headers: dict = field(default_factory=dict)


def quiet_guard(api_keys=None, **kwargs) -> HeliusGuard:
    instance = HeliusGuard(api_keys or ["k1", "k2"], rps=1_000_000, **kwargs)
    instance.rate_limiter.acquire = lambda: None
    return instance


def test_max_usage_reached_rotates_then_succeeds(monkeypatch):
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: None)
    calls: list[str] = []
    events: list[str] = []
    limiter = quiet_guard(on_event=events.append)

    def fn(api_key):
        calls.append(api_key)
        if len(calls) == 1:
            return Response(429, "max usage reached")
        return Response(200, "ok")

    response = limiter.request(fn)

    assert response is not None
    assert calls == ["k1", "k2"]
    assert limiter.quota.remaining() == 99_999
    assert events == ["throttled", "rotated"]


def test_eight_generic_429s_open_circuit(monkeypatch):
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(guard, "backoff_seconds", lambda *args, **kwargs: 0.0)
    limiter = quiet_guard(api_keys=["k1"], failure_threshold=8)

    response = limiter.request(lambda api_key: Response(429, "slow down"), retries=8)

    assert response is None
    assert limiter.circuit.is_open()
    assert limiter.request(lambda api_key: Response(200, "ok")) is None


def test_success_path_charges_requested_credits():
    limiter = quiet_guard(monthly_credits=10)

    response = limiter.request(lambda api_key: Response(200, "ok"), credits=3)

    assert response is not None
    assert limiter.quota.remaining() == 7


def test_quota_exhaustion_skips_request():
    events: list[str] = []
    limiter = quiet_guard(monthly_credits=1, on_event=events.append)
    limiter.quota.charge(1)
    assert limiter.request(lambda api_key: Response(200, "ok")) is None
    assert events == ["throttled"]
