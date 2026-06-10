"""Retry-After parsing and bounded exponential backoff."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_retry_after(headers: dict) -> float | None:
    """Parse an RFC 7231 ``Retry-After`` header into seconds.

    Accepts either a numeric delay (``"120"``) or an HTTP-date
    (``"Wed, 21 Oct 2026 07:28:00 GMT"``). Returns the non-negative number of
    seconds to wait, or ``None`` when the header is absent, blank, or
    unparseable -- in which case callers fall back to bounded exponential
    backoff, so the default behavior is unchanged.
    """

    raw = None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        pass
    else:
        if math.isfinite(seconds):
            return max(0.0, seconds)
        return None
    try:
        parsed = parsedate_to_datetime(text)
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
