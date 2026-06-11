import asyncio
import threading
import time

from helius_limiter.concurrency import AsyncConcurrencyLimiter, ConcurrencyLimiter


def run(coro):
    return asyncio.run(coro)


def test_sync_concurrency_cap_blocks_until_release():
    events: list[str] = []
    limiter = ConcurrencyLimiter(1, on_event=events.append)
    first_entered = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()

    def first_worker():
        with limiter:
            first_entered.set()
            release_first.wait(timeout=2)

    def second_worker():
        with limiter:
            second_acquired.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    assert first_entered.wait(timeout=2)

    second.start()
    time.sleep(0.05)
    assert not second_acquired.is_set()
    assert "saturated" in events
    assert limiter.in_flight == 1

    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert second_acquired.is_set()
    assert limiter.in_flight == 0
    assert events.count("acquired") == 2
    assert events.count("released") == 2


def test_sync_nonblocking_acquire_reports_saturation():
    events: list[str] = []
    limiter = ConcurrencyLimiter(1, on_event=events.append)

    assert limiter.acquire()
    assert not limiter.acquire(blocking=False)
    limiter.release()

    assert events == ["acquired", "saturated", "released"]


def test_async_concurrency_cap_respected():
    async def scenario():
        events: list[str] = []
        limiter = AsyncConcurrencyLimiter(1, on_event=events.append)
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_acquired = asyncio.Event()

        async def first_worker():
            async with limiter:
                first_entered.set()
                await release_first.wait()

        async def second_worker():
            async with limiter:
                second_acquired.set()

        first = asyncio.create_task(first_worker())
        await first_entered.wait()
        second = asyncio.create_task(second_worker())
        await asyncio.sleep(0.01)

        assert not second_acquired.is_set()
        assert "saturated" in events
        assert limiter.in_flight == 1

        release_first.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2)

        assert second_acquired.is_set()
        assert limiter.in_flight == 0
        assert events.count("acquired") == 2
        assert events.count("released") == 2

    run(scenario())


def test_async_timeout_returns_false():
    async def scenario():
        events: list[str] = []
        limiter = AsyncConcurrencyLimiter(1, on_event=events.append)
        assert await limiter.acquire()
        assert not await limiter.acquire(timeout=0.01)
        await limiter.release()
        assert events == ["acquired", "saturated", "released"]

    run(scenario())
