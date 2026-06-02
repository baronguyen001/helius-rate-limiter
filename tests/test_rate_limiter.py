from helius_limiter import rate_limiter
from helius_limiter.rate_limiter import RateLimiter


def test_two_acquire_calls_are_spaced(monkeypatch):
    clock = {"now": 100.0}
    sleeps: list[float] = []

    def fake_monotonic():
        return clock["now"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(rate_limiter.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(rate_limiter.time, "sleep", fake_sleep)

    limiter = RateLimiter(rps=10)
    limiter.acquire()
    limiter.acquire()

    assert sleeps
    assert sleeps[0] >= limiter.min_interval
