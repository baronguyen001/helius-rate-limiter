import asyncio

import pytest

from helius_limiter import adaptive
from helius_limiter.adaptive import AdaptiveLimiter, AsyncAdaptiveLimiter


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


class FakeAsyncLimiter:
    def __init__(self):
        self.calls = 0

    async def acquire(self):
        self.calls += 1


def run(coro):
    return asyncio.run(coro)


# ---- AIMD math -------------------------------------------------------------


def test_429_multiplicatively_cuts_rate():
    limiter = AdaptiveLimiter(FakeLimiter(), max_rate=10, decrease_factor=0.5)
    assert limiter.rate == 10.0
    limiter.on_429()
    assert limiter.rate == 5.0
    limiter.on_429()
    assert limiter.rate == 2.5


def test_decrease_respects_min_rate_floor():
    limiter = AdaptiveLimiter(FakeLimiter(), max_rate=4, min_rate=1.0, decrease_factor=0.5)
    for _ in range(10):
        limiter.on_429()
    assert limiter.rate == 1.0


def test_additive_recovery_after_success_streak():
    limiter = AdaptiveLimiter(
        FakeLimiter(),
        max_rate=10,
        start_rate=2,
        increase_step=1.0,
        success_threshold=3,
    )
    assert limiter.rate == 2.0
    # Two successes are not enough to trip the additive increase.
    limiter.on_success()
    limiter.on_success()
    assert limiter.rate == 2.0
    # Third success completes the streak -> +increase_step.
    limiter.on_success()
    assert limiter.rate == 3.0


def test_recovery_respects_ceiling():
    limiter = AdaptiveLimiter(
        FakeLimiter(),
        max_rate=3,
        start_rate=2,
        increase_step=5.0,
        success_threshold=1,
    )
    limiter.on_success()
    assert limiter.rate == 3.0  # clamped to max_rate, not 7
    # Already at the ceiling: further successes do not exceed it.
    limiter.on_success()
    assert limiter.rate == 3.0


def test_success_streak_resets_on_429():
    limiter = AdaptiveLimiter(
        FakeLimiter(),
        max_rate=10,
        start_rate=4,
        increase_step=1.0,
        success_threshold=3,
    )
    limiter.on_success()
    limiter.on_success()
    limiter.on_429()  # rate 4 -> 2, streak cleared
    assert limiter.rate == 2.0
    limiter.on_success()
    limiter.on_success()
    assert limiter.rate == 2.0  # streak restarted, not yet at threshold
    limiter.on_success()
    assert limiter.rate == 3.0


# ---- on_event contract -----------------------------------------------------


def test_on_event_emits_backed_off_and_recovered():
    events: list[str] = []
    limiter = AdaptiveLimiter(
        FakeLimiter(),
        max_rate=10,
        start_rate=4,
        decrease_factor=0.5,
        increase_step=1.0,
        success_threshold=1,
        on_event=events.append,
    )
    limiter.on_429()
    limiter.on_success()
    assert events == ["backed_off", "recovered"]


def test_no_recovered_event_when_at_ceiling():
    events: list[str] = []
    limiter = AdaptiveLimiter(
        FakeLimiter(),
        max_rate=5,
        start_rate=5,
        success_threshold=1,
        on_event=events.append,
    )
    limiter.on_success()
    assert events == []


# ---- acquire spacing + Retry-After honoring --------------------------------


def test_acquire_runs_wrapped_limiter_then_spaces(monkeypatch):
    clock = {"now": 100.0}
    sleeps: list[float] = []

    monkeypatch.setattr(adaptive.time, "monotonic", lambda: clock["now"])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(adaptive.time, "sleep", fake_sleep)

    wrapped = FakeLimiter()
    limiter = AdaptiveLimiter(wrapped, max_rate=2)  # min_interval = 0.5s
    limiter.acquire()
    limiter.acquire()

    assert wrapped.calls == 2
    assert sleeps == [0.5]


def test_on_429_sleeps_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(adaptive.time, "sleep", sleeps.append)

    limiter = AdaptiveLimiter(FakeLimiter(), max_rate=10)
    limiter.on_429(retry_after=3.0)
    assert sleeps == [3.0]
    assert limiter.rate == 5.0


def test_invalid_config_rejected():
    with pytest.raises(ValueError, match="decrease_factor"):
        AdaptiveLimiter(FakeLimiter(), max_rate=10, decrease_factor=1.5)
    with pytest.raises(ValueError, match="min_rate"):
        AdaptiveLimiter(FakeLimiter(), max_rate=2, min_rate=5)


# ---- async mirror ----------------------------------------------------------


def test_async_mirrors_aimd_math_and_events():
    events: list[str] = []

    async def scenario():
        wrapped = FakeAsyncLimiter()
        limiter = AsyncAdaptiveLimiter(
            wrapped,
            max_rate=10,
            start_rate=4,
            decrease_factor=0.5,
            increase_step=1.0,
            success_threshold=1,
            on_event=events.append,
        )
        await limiter.on_429()
        assert limiter.rate == 2.0
        await limiter.on_success()
        assert limiter.rate == 3.0
        await limiter.acquire()
        assert wrapped.calls == 1

    run(scenario())
    assert events == ["backed_off", "recovered"]


def test_async_on_event_can_be_coroutine():
    events: list[str] = []

    async def record(event):
        events.append(event)

    async def scenario():
        limiter = AsyncAdaptiveLimiter(
            FakeAsyncLimiter(),
            max_rate=10,
            start_rate=4,
            on_event=record,
        )
        await limiter.on_429()

    run(scenario())
    assert events == ["backed_off"]
