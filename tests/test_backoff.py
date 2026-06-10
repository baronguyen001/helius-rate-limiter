from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from helius_limiter import backoff
from helius_limiter.backoff import backoff_seconds, parse_retry_after


def test_parse_retry_after_numeric():
    assert parse_retry_after({"Retry-After": "2.5"}) == 2.5


def test_parse_retry_after_is_case_insensitive():
    assert parse_retry_after({"RETRY-AFTER": "7"}) == 7.0


def test_parse_retry_after_http_date():
    future = datetime.now(UTC) + timedelta(seconds=30)
    parsed = parse_retry_after({"retry-after": format_datetime(future)})
    assert parsed is not None
    assert 0 <= parsed <= 31


def test_parse_retry_after_past_http_date_clamps_to_zero():
    past = datetime.now(UTC) - timedelta(seconds=120)
    assert parse_retry_after({"Retry-After": format_datetime(past)}) == 0.0


def test_parse_retry_after_absent_returns_none():
    assert parse_retry_after({}) is None
    assert parse_retry_after({"X-Other": "5"}) is None


def test_parse_retry_after_invalid_returns_none():
    assert parse_retry_after({"Retry-After": "not-a-date"}) is None


def test_parse_retry_after_blank_returns_none():
    assert parse_retry_after({"Retry-After": "   "}) is None


def test_parse_retry_after_rejects_non_finite():
    assert parse_retry_after({"Retry-After": "inf"}) is None
    assert parse_retry_after({"Retry-After": "nan"}) is None


def test_backoff_seconds_uses_retry_after_and_jitter(monkeypatch):
    monkeypatch.setattr(backoff.random, "uniform", lambda start, end: 0.25)
    assert backoff_seconds(3, retry_after=5, jitter=1) == 5.25
    assert backoff_seconds(2, max_backoff=60, jitter=1) == 4.25


def test_backoff_seconds_default_unchanged_without_retry_after(monkeypatch):
    # When no Retry-After is present the path stays bounded exponential.
    monkeypatch.setattr(backoff.random, "uniform", lambda start, end: 0.0)
    assert backoff_seconds(0) == 1.0
    assert backoff_seconds(4) == 16.0
    assert backoff_seconds(10, max_backoff=60) == 60.0  # capped
