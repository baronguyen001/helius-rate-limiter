"""Retry-After parsing and bounded exponential backoff."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_retry_after(headers: dict) -> float | None:
    raw = None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        parsed = parsedate_to_datetime(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def backoff_seconds(
    attempt: int,
    retry_after: float | None = None,
    max_backoff: float = 60.0,
    jitter: float = 1.0,
) -> float:
    base = retry_after if retry_after is not None else min(max_backoff, float(2**attempt))
    return base + random.uniform(0.0, jitter)
