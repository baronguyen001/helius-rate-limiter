import asyncio
import json
from datetime import UTC, datetime

import pytest

from helius_limiter import persist
from helius_limiter.persist import (
    AsyncPersistentQuotaTracker,
    PersistentQuotaTracker,
    _atomic_write_json,
    _current_period,
)


def run(coro):
    return asyncio.run(coro)


def _ts(year, month, day=15):
    return datetime(year, month, day, 12, 0, tzinfo=UTC).timestamp()


def test_current_period_is_year_month():
    assert _current_period(_ts(2026, 6)) == "2026-06"
    assert _current_period(_ts(2026, 12)) == "2026-12"


def test_charge_remaining_and_exhaustion(tmp_path):
    path = str(tmp_path / "quota.json")
    tracker = PersistentQuotaTracker(path, max_credits=3)
    tracker.charge(2)
    assert tracker.remaining() == 1
    assert not tracker.is_exhausted()
    tracker.charge(1)
    assert tracker.is_exhausted()
    assert tracker.remaining() == 0


def test_survives_reload(tmp_path):
    path = str(tmp_path / "quota.json")
    tracker = PersistentQuotaTracker(path, max_credits=100)
    tracker.charge(40)

    reloaded = PersistentQuotaTracker(path, max_credits=100)
    assert reloaded.remaining() == 60

    reloaded.charge(10)
    again = PersistentQuotaTracker(path, max_credits=100)
    assert again.remaining() == 50


def test_monthly_rollover_resets_used(tmp_path):
    path = str(tmp_path / "quota.json")
    tracker = PersistentQuotaTracker(path, max_credits=5, now=_ts(2026, 6))
    tracker.charge(5)
    assert tracker.is_exhausted()

    # Same calendar month: still exhausted.
    tracker._roll_if_needed(_ts(2026, 6, day=28))
    assert tracker.used == 5

    # New calendar month: usage resets even though < 30 days may have passed.
    tracker._roll_if_needed(_ts(2026, 7, day=1))
    assert tracker.used == 0
    assert not tracker.is_exhausted()


def test_rollover_detected_on_reload(tmp_path):
    path = str(tmp_path / "quota.json")
    tracker = PersistentQuotaTracker(path, max_credits=10, now=_ts(2026, 6))
    tracker.charge(7)

    # Reload in a later month -> the stale period rolls over to zero on load.
    later = PersistentQuotaTracker(path, max_credits=10, now=_ts(2026, 7))
    assert later.remaining() == 10
    assert later.used == 0


def test_atomic_write_replaces_without_partial_file(tmp_path):
    path = str(tmp_path / "quota.json")
    _atomic_write_json(path, {"period": "2026-06", "used": 42})

    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload == {"period": "2026-06", "used": 42}

    # No leftover temp files in the directory.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".helius_quota_")]
    assert leftovers == []


def test_atomic_write_failure_leaves_original_intact(tmp_path, monkeypatch):
    path = str(tmp_path / "quota.json")
    _atomic_write_json(path, {"period": "2026-06", "used": 1})

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(persist.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        _atomic_write_json(path, {"period": "2026-06", "used": 999})

    # Original file is untouched and no temp file is left behind.
    with open(path, encoding="utf-8") as handle:
        assert json.load(handle) == {"period": "2026-06", "used": 1}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".helius_quota_")]
    assert leftovers == []


def test_reset_clears_usage(tmp_path):
    path = str(tmp_path / "quota.json")
    tracker = PersistentQuotaTracker(path, max_credits=2)
    tracker.charge(2)
    tracker.reset()
    assert tracker.remaining() == 2


def test_corrupt_state_file_is_ignored(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text("{ not valid json", encoding="utf-8")
    tracker = PersistentQuotaTracker(str(path), max_credits=10)
    assert tracker.remaining() == 10


def test_requires_state_path():
    with pytest.raises(ValueError, match="state_path"):
        PersistentQuotaTracker("", max_credits=10)


# ---- async mirror ----------------------------------------------------------


def test_async_survives_reload_and_rollover(tmp_path):
    path = str(tmp_path / "quota.json")

    async def scenario():
        tracker = AsyncPersistentQuotaTracker(path, max_credits=100, now=_ts(2026, 6))
        await tracker.charge(30)
        assert await tracker.remaining() == 70

        reloaded = AsyncPersistentQuotaTracker(path, max_credits=100, now=_ts(2026, 6))
        assert await reloaded.remaining() == 70

        next_month = AsyncPersistentQuotaTracker(path, max_credits=100, now=_ts(2026, 7))
        assert await next_month.remaining() == 100

    run(scenario())
