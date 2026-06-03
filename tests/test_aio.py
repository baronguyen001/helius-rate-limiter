import asyncio
from dataclasses import dataclass, field

from helius_limiter import aio
from helius_limiter.aio import (
    AsyncCircuitBreaker,
    AsyncGuard,
    AsyncQuotaTracker,
    AsyncRateLimiter,
)


@dataclass
class Response:
    status_code: int
    text: str = ""
    headers: dict = field(default_factory=dict)


def run(coro):
    return asyncio.run(coro)


def test_async_rate_limiter_acquire_calls_are_spaced(monkeypatch):
    clock = {"now": 100.0}
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(aio.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(aio.asyncio, "sleep", fake_sleep)

    async def scenario():
        limiter = AsyncRateLimiter(rps=10)
        await limiter.acquire()
        await limiter.acquire()
        assert sleeps
        assert sleeps[0] >= limiter.min_interval

    run(scenario())


def test_async_quota_tracks_usage_and_rolls_window(monkeypatch):
    now = {"value": 10.0}
    monkeypatch.setattr(aio.time, "time", lambda: now["value"])

    async def scenario():
        tracker = AsyncQuotaTracker(max_credits=5, window_seconds=10)
        await tracker.charge(5)
        assert await tracker.is_exhausted()
        now["value"] = 21.0
        assert not await tracker.is_exhausted()
        assert await tracker.remaining() == 5

    run(scenario())


def test_async_circuit_events_fire_on_trip_and_reset(monkeypatch):
    events: list[str] = []
    now = {"value": 50.0}
    monkeypatch.setattr(aio.time, "monotonic", lambda: now["value"])

    async def scenario():
        breaker = AsyncCircuitBreaker(failure_threshold=1, open_seconds=30, on_event=events.append)
        await breaker.record_failure()
        assert await breaker.is_open()
        await breaker.record_success()
        assert not await breaker.is_open()
        assert events == ["tripped", "reset"]

    run(scenario())


def test_async_guard_rotates_on_monthly_exhaustion_and_charges_success():
    async def scenario():
        events: list[str] = []
        calls: list[str] = []
        guard = AsyncGuard(["k1", "k2"], rps=1_000_000, on_event=events.append)

        async def noop_acquire():
            return None

        guard.rate_limiter.acquire = noop_acquire

        async def call(api_key):
            calls.append(api_key)
            if len(calls) == 1:
                return Response(429, "max usage reached")
            return Response(200, "ok")

        response = await guard.request(call, credits=2)

        assert response is not None
        assert calls == ["k1", "k2"]
        assert await guard.quota.remaining() == 99_998
        assert events == ["throttled", "rotated"]

    run(scenario())


def test_async_guard_quota_exhaustion_skips_request():
    async def scenario():
        events: list[str] = []
        guard = AsyncGuard(["k1"], monthly_credits=1, on_event=events.append)
        await guard.quota.charge(1)

        async def call(api_key):
            raise AssertionError("request should not be called")

        assert await guard.request(call) is None
        assert events == ["throttled"]

    run(scenario())


def test_async_guard_generic_429_can_trip_circuit(monkeypatch):
    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(aio.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(aio, "backoff_seconds", lambda *args, **kwargs: 0.0)

    async def scenario():
        events: list[str] = []
        guard = AsyncGuard(["k1"], failure_threshold=2, on_event=events.append)

        async def noop_acquire():
            return None

        guard.rate_limiter.acquire = noop_acquire

        response = await guard.request(lambda api_key: Response(429, "slow down"), retries=2)

        assert response is None
        assert await guard.circuit.is_open()
        assert events == ["throttled", "throttled", "tripped"]

    run(scenario())
