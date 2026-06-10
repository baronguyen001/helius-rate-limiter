"""Track Helius monthly credits across restarts with a JSON-backed counter.

``PersistentQuotaTracker`` keys its window on the calendar month and writes the
count atomically, so a bot that restarts mid-month resumes from the credits it
has already spent instead of starting over. Point ``HELIUS_QUOTA_PATH`` at a
writable data/tmp file -- never commit the state file.
"""

from __future__ import annotations

import os
import tempfile

from helius_limiter import PersistentQuotaTracker


def main() -> None:
    # BYO path: default to an OS tmp file so the example is safe to run anywhere.
    state_path = os.getenv(
        "HELIUS_QUOTA_PATH",
        os.path.join(tempfile.gettempdir(), "helius_monthly_quota.json"),
    )
    tracker = PersistentQuotaTracker(
        state_path,
        max_credits=int(os.getenv("HELIUS_MONTHLY_CREDITS", "100000")),
    )

    if tracker.is_exhausted():
        print("monthly credits exhausted; backing off until next calendar month")
        return

    # ... make your Helius call here, then charge what it cost ...
    tracker.charge(int(os.getenv("HELIUS_CREDITS", "1")))
    print(f"remaining this month: {tracker.remaining()} (state at {state_path})")


if __name__ == "__main__":
    main()
