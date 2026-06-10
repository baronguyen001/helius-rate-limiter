"""Calendar-month credit tracking that survives process restarts.

The in-memory :class:`~helius_limiter.quota.QuotaLimiter` rolls on an elapsed-time
window and persists with a plain ``open(..., "w")``. Helius free tier resets on the
**calendar month**, not on a sliding 30-day window, and a long-lived bot may be
restarted mid-month -- so this tracker keys the window on ``(year, month)`` and
writes the JSON state atomically (temp file + ``os.replace``) so a crash mid-write
can never corrupt the saved count. Same ``charge``/``remaining``/``is_exhausted``
contract as ``quota.py``. stdlib only.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime


def _current_period(now: float | None = None) -> str:
    """Return the ``YYYY-MM`` calendar-month key for ``now`` (UTC)."""

    moment = datetime.now(UTC) if now is None else datetime.fromtimestamp(now, tz=UTC)
    return f"{moment.year:04d}-{moment.month:02d}"


def _atomic_write_json(path: str, payload: dict) -> None:
    """Write ``payload`` as JSON to ``path`` atomically.

    The data is written to a temp file in the same directory, flushed and
    fsync'd, then ``os.replace``'d over the target. ``os.replace`` is atomic on
    both POSIX and Windows, so a reader never sees a half-written file.
    """

    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".helius_quota_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class PersistentQuotaTracker:
    """A monthly credit counter backed by a single JSON file.

    Args:
        state_path: JSON file that stores ``{"period": "YYYY-MM", "used": int}``.
            Bring your own path (a tmp/data dir); never commit it.
        max_credits: Hard cap for the calendar month (Helius free = 100k).
        now: Optional clock override (seconds since epoch) for testing.
    """

    def __init__(
        self,
        state_path: str,
        *,
        max_credits: int = 100_000,
        now: float | None = None,
    ):
        if not state_path:
            raise ValueError("state_path is required")
        if max_credits <= 0:
            raise ValueError("max_credits must be positive")
        self.state_path = state_path
        self.max_credits = max_credits
        self.lock = threading.Lock()
        self.period = _current_period(now)
        self.used = 0
        self._load()
        self._roll_if_needed(now)

    def charge(self, credits: int = 1) -> None:
        if credits < 0:
            raise ValueError("credits must be non-negative")
        with self.lock:
            self._roll_if_needed()
            self.used += credits
            self._persist()

    def remaining(self) -> int:
        with self.lock:
            self._roll_if_needed()
            return max(0, self.max_credits - self.used)

    def is_exhausted(self) -> bool:
        with self.lock:
            self._roll_if_needed()
            return self.used >= self.max_credits

    def reset(self) -> None:
        with self.lock:
            self.period = _current_period()
            self.used = 0
            self._persist()

    def _roll_if_needed(self, now: float | None = None) -> None:
        current = _current_period(now)
        if current != self.period:
            self.period = current
            self.used = 0
            self._persist()

    def _load(self) -> None:
        if not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        self.period = str(payload.get("period", self.period))
        self.used = int(payload.get("used", 0))

    def _persist(self) -> None:
        _atomic_write_json(self.state_path, {"period": self.period, "used": self.used})


class AsyncPersistentQuotaTracker:
    """Asyncio mirror of :class:`PersistentQuotaTracker`.

    File I/O is offloaded to a worker thread so the event loop never blocks on
    the atomic write.
    """

    def __init__(
        self,
        state_path: str,
        *,
        max_credits: int = 100_000,
        now: float | None = None,
    ):
        if not state_path:
            raise ValueError("state_path is required")
        if max_credits <= 0:
            raise ValueError("max_credits must be positive")
        import asyncio

        self.state_path = state_path
        self.max_credits = max_credits
        self.lock = asyncio.Lock()
        self.period = _current_period(now)
        self.used = 0
        self._load()
        # Synchronous rollover at construction mirrors the sync class; no event
        # loop is required yet.
        current = _current_period(now)
        if current != self.period:
            self.period = current
            self.used = 0
            self._persist_sync()

    async def charge(self, credits: int = 1) -> None:
        if credits < 0:
            raise ValueError("credits must be non-negative")
        async with self.lock:
            await self._roll_if_needed()
            self.used += credits
            await self._persist()

    async def remaining(self) -> int:
        async with self.lock:
            await self._roll_if_needed()
            return max(0, self.max_credits - self.used)

    async def is_exhausted(self) -> bool:
        async with self.lock:
            await self._roll_if_needed()
            return self.used >= self.max_credits

    async def reset(self) -> None:
        async with self.lock:
            self.period = _current_period()
            self.used = 0
            await self._persist()

    async def _roll_if_needed(self, now: float | None = None) -> None:
        current = _current_period(now)
        if current != self.period:
            self.period = current
            self.used = 0
            await self._persist()

    def _load(self) -> None:
        if not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        self.period = str(payload.get("period", self.period))
        self.used = int(payload.get("used", 0))

    def _persist_sync(self) -> None:
        _atomic_write_json(self.state_path, {"period": self.period, "used": self.used})

    async def _persist(self) -> None:
        import asyncio

        payload = {"period": self.period, "used": self.used}
        await asyncio.to_thread(_atomic_write_json, self.state_path, payload)
