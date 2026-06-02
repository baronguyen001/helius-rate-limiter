from helius_limiter import circuit
from helius_limiter.circuit import CircuitBreaker


def test_opens_after_failure_threshold(monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr(circuit.time, "monotonic", lambda: now["value"])
    breaker = CircuitBreaker(failure_threshold=2, open_seconds=30)

    breaker.record_failure()
    assert not breaker.is_open()
    breaker.record_failure()
    assert breaker.is_open()

    now["value"] = 131.0
    assert not breaker.is_open()


def test_record_success_resets_streak_and_open_state(monkeypatch):
    monkeypatch.setattr(circuit.time, "monotonic", lambda: 50.0)
    breaker = CircuitBreaker(failure_threshold=2, open_seconds=30)
    breaker.record_failure()
    breaker.trip()
    breaker.record_success()
    assert breaker.failures == 0
    assert not breaker.is_open()


def test_trip_can_open_long_window(monkeypatch):
    monkeypatch.setattr(circuit.time, "monotonic", lambda: 10.0)
    breaker = CircuitBreaker()
    breaker.trip(86_400)
    assert breaker.open_until == 86_410.0
    assert breaker.is_open()
