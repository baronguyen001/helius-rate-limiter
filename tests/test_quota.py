from helius_limiter import quota
from helius_limiter.quota import QuotaLimiter


def test_charge_remaining_and_exhaustion():
    limiter = QuotaLimiter(max_credits=3, window_seconds=60)
    limiter.charge(2)
    assert limiter.remaining() == 1
    assert not limiter.is_exhausted()
    limiter.charge(1)
    assert limiter.is_exhausted()


def test_window_roll_resets_usage(monkeypatch):
    now = {"value": 10.0}
    monkeypatch.setattr(quota.time, "time", lambda: now["value"])
    limiter = QuotaLimiter(max_credits=5, window_seconds=10)
    limiter.charge(5)
    now["value"] = 21.0
    assert not limiter.is_exhausted()
    assert limiter.remaining() == 5


def test_state_path_round_trips(tmp_path):
    state_path = tmp_path / "helius_state.json"
    limiter = QuotaLimiter(max_credits=10, state_path=str(state_path))
    limiter.charge(4)

    fresh = QuotaLimiter(max_credits=10, state_path=str(state_path))
    assert fresh.remaining() == 6


def test_reset_clears_usage():
    limiter = QuotaLimiter(max_credits=2)
    limiter.charge(2)
    limiter.reset()
    assert limiter.remaining() == 2
