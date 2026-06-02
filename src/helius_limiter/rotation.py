"""In-memory Helius API key rotation."""

from __future__ import annotations


class KeyRotator:
    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("keys must not be empty")
        self.keys = list(keys)
        self.index = 0
        self._exhausted: set[int] = set()

    def current(self) -> str:
        return self.keys[self.index]

    def rotate(self) -> bool:
        self._exhausted.add(self.index)
        for offset in range(1, len(self.keys) + 1):
            candidate = (self.index + offset) % len(self.keys)
            if candidate not in self._exhausted:
                self.index = candidate
                return True
        return False

    @property
    def live_count(self) -> int:
        return len(self.keys) - len(self._exhausted)
