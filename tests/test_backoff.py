from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from helius_limiter import backoff
from helius_limiter.backoff import backoff_seconds, parse_retry_after


def test_parse_retry_after_numeric():
    assert parse_retry_after({"Retry-After": "2.5"}) == 2.5


def test_parse_retry_after_http_date():
    future = datetime.now(UTC) + timedelta(seconds=30)
    parsed = parse_retry_after({"retry-after": format_datetime(future)})
    assert parsed is not None
    assert 0 <= parsed <= 31


def test_backoff_seconds_uses_retry_after_and_jitter(monkeypatch):
    monkeypatch.setattr(backoff.random, "uniform", lambda start, end: 0.25)
    assert backoff_seconds(3, retry_after=5, jitter=1) == 5.25
    assert backoff_seconds(2, max_backoff=60, jitter=1) == 4.25
