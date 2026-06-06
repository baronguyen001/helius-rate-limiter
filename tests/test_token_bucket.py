import asyncio

import pytest

from helius_limiter import token_bucket
from helius_limiter.token_bucket import AsyncTokenBucketLimiter, TokenBucketLimiter


def run(coro):
    return asyncio.run(coro)


def test_token_bucket_allows_burst_then_waits_for_refill(monkeypatch):
    clock = {"now": 100.0}
    sleeps: list[float] = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(token_bucket.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(token_bucket.time, "sleep", fake_sleep)

    limiter = TokenBucketLimiter(capacity=2, refill_rate=1)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert sleeps == [1.0]
    assert limiter.available_tokens() == 0.0


def test_token_bucket_refills_from_elapsed_time(monkeypatch):
    clock = {"now": 10.0}
    monkeypatch.setattr(token_bucket.time, "monotonic", lambda: clock["now"])

    limiter = TokenBucketLimiter(capacity=5, refill_rate=2, initial_tokens=0)
    clock["now"] = 11.5

    assert limiter.available_tokens() == 3.0


def test_token_bucket_rejects_impossible_request():
    limiter = TokenBucketLimiter(capacity=2, refill_rate=1)

    with pytest.raises(ValueError, match="capacity"):
        limiter.acquire(tokens=3)


def test_async_token_bucket_allows_burst_then_waits_for_refill(monkeypatch):
    clock = {"now": 200.0}
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(token_bucket.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(token_bucket.asyncio, "sleep", fake_sleep)

    async def scenario():
        limiter = AsyncTokenBucketLimiter(capacity=2, refill_rate=1)
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        assert sleeps == [1.0]
        assert await limiter.available_tokens() == 0.0

    run(scenario())


def test_async_token_bucket_rejects_invalid_capacity():
    with pytest.raises(ValueError, match="capacity"):
        AsyncTokenBucketLimiter(capacity=0, refill_rate=1)
