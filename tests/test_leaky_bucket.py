"""Tests for the leaky-bucket limiters (v0.6). Deterministic injected clock."""

from __future__ import annotations

import asyncio

import pytest

from helius_limiter import AsyncLeakyBucketLimiter, LeakyBucketLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    async def asleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def test_validation() -> None:
    with pytest.raises(ValueError):
        LeakyBucketLimiter(rate=0, capacity=5)
    with pytest.raises(ValueError):
        LeakyBucketLimiter(rate=1, capacity=0)
    bucket = LeakyBucketLimiter(rate=1, capacity=5)
    with pytest.raises(ValueError):
        bucket.try_acquire(0)
    with pytest.raises(ValueError):
        bucket.acquire(99)  # > capacity


def test_try_acquire_fills_then_rejects() -> None:
    clock = FakeClock()
    bucket = LeakyBucketLimiter(rate=1, capacity=3, time_func=clock.time, sleep_func=clock.sleep)
    assert bucket.try_acquire() and bucket.try_acquire() and bucket.try_acquire()
    assert not bucket.try_acquire()  # full at level 3
    assert bucket.water_level() == pytest.approx(3.0)


def test_leak_over_time_frees_capacity() -> None:
    clock = FakeClock()
    bucket = LeakyBucketLimiter(rate=2, capacity=4, time_func=clock.time, sleep_func=clock.sleep)
    for _ in range(4):
        assert bucket.try_acquire()
    assert not bucket.try_acquire()
    clock.t += 1.0  # 1s at rate 2 -> 2 units leak out
    assert bucket.water_level() == pytest.approx(2.0)
    assert bucket.try_acquire() and bucket.try_acquire()
    assert not bucket.try_acquire()


def test_acquire_blocks_until_room() -> None:
    clock = FakeClock()
    bucket = LeakyBucketLimiter(rate=2, capacity=2, time_func=clock.time, sleep_func=clock.sleep)
    bucket.acquire()
    bucket.acquire()  # full
    bucket.acquire()  # must wait for 1 unit to leak: overflow 1 / rate 2 = 0.5s
    assert clock.sleeps == [pytest.approx(0.5)]


def test_async_leaky_bucket() -> None:
    clock = FakeClock()
    bucket = AsyncLeakyBucketLimiter(
        rate=2, capacity=2, time_func=clock.time, sleep_func=clock.asleep
    )

    async def scenario() -> None:
        assert await bucket.try_acquire()
        assert await bucket.try_acquire()
        assert not await bucket.try_acquire()
        await bucket.acquire()  # waits 0.5s
        assert await bucket.water_level() == pytest.approx(2.0)

    asyncio.run(scenario())
    assert clock.sleeps == [pytest.approx(0.5)]


def test_async_validation() -> None:
    with pytest.raises(ValueError):
        AsyncLeakyBucketLimiter(rate=-1, capacity=5)
