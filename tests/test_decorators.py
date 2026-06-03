import asyncio

import pytest

from helius_limiter.aio import AsyncCircuitBreaker, AsyncQuotaTracker
from helius_limiter.circuit import CircuitBreaker
from helius_limiter.decorators import rate_limited, with_circuit, with_quota
from helius_limiter.quota import QuotaLimiter


def run(coro):
    return asyncio.run(coro)


def test_rate_limited_wraps_sync_function():
    calls: list[str] = []

    class Limiter:
        def acquire(self):
            calls.append("acquire")

    @rate_limited(Limiter())
    def call():
        calls.append("call")
        return "ok"

    assert call() == "ok"
    assert calls == ["acquire", "call"]


def test_rate_limited_wraps_async_function():
    async def scenario():
        calls: list[str] = []

        class Limiter:
            async def acquire(self):
                calls.append("acquire")

        @rate_limited(Limiter())
        async def call():
            calls.append("call")
            return "ok"

        assert await call() == "ok"
        assert calls == ["acquire", "call"]

    run(scenario())


def test_with_quota_charges_sync_success_and_skips_when_exhausted():
    tracker = QuotaLimiter(max_credits=2)
    calls: list[str] = []

    @with_quota(tracker, credits=2)
    def call():
        calls.append("call")
        return "ok"

    assert call() == "ok"
    assert tracker.is_exhausted()
    assert call() is None
    assert calls == ["call"]


def test_with_quota_charges_async_success_and_skips_when_exhausted():
    async def scenario():
        tracker = AsyncQuotaTracker(max_credits=1)
        calls: list[str] = []

        @with_quota(tracker)
        async def call():
            calls.append("call")
            return "ok"

        assert await call() == "ok"
        assert await call() is None
        assert calls == ["call"]

    run(scenario())


def test_with_circuit_records_sync_failures_and_skips_when_open():
    breaker = CircuitBreaker(failure_threshold=1, open_seconds=60)
    calls: list[str] = []

    @with_circuit(breaker)
    def call(*, fail=False):
        calls.append("call")
        if fail:
            raise RuntimeError("boom")
        return "ok"

    with pytest.raises(RuntimeError, match="boom"):
        call(fail=True)

    assert breaker.is_open()
    assert call() is None
    assert calls == ["call"]


def test_with_circuit_records_async_failures_and_skips_when_open():
    async def scenario():
        breaker = AsyncCircuitBreaker(failure_threshold=1, open_seconds=60)
        calls: list[str] = []

        @with_circuit(breaker)
        async def call(*, fail=False):
            calls.append("call")
            if fail:
                raise RuntimeError("boom")
            return "ok"

        with pytest.raises(RuntimeError, match="boom"):
            await call(fail=True)

        assert await breaker.is_open()
        assert await call() is None
        assert calls == ["call"]

    run(scenario())
