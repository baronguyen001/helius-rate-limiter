"""Weighted credit charging for Helius endpoints and RPC methods."""

from __future__ import annotations

import inspect
from collections.abc import Mapping

DEFAULT_WEIGHTS: dict[str, int] = {
    "getbalance": 1,
    "getaccountinfo": 1,
    "getasset": 1,
    "getassetsbyowner": 2,
    "getsignaturesforaddress": 5,
    "gettransaction": 5,
    "getprogramaccounts": 10,
    "searchassets": 10,
}


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _normalize_weights(weights: Mapping[str, int]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for key, value in weights.items():
        if value <= 0:
            raise ValueError("weights must be positive")
        normalized[_normalize_key(key)] = int(value)
    return normalized


class WeightedCostLimiter:
    """Charge a quota tracker by endpoint-specific credit weights.

    The wrapped quota object only needs the existing ``charge(credits=...)``
    contract used by ``QuotaLimiter`` and ``PersistentQuotaTracker``.
    """

    def __init__(
        self,
        quota,
        *,
        weights: Mapping[str, int] | None = None,
        default_weight: int = 1,
    ):
        if default_weight <= 0:
            raise ValueError("default_weight must be positive")
        self.quota = quota
        self.default_weight = int(default_weight)
        merged = DEFAULT_WEIGHTS | dict(weights or {})
        self.weights = _normalize_weights(merged)

    def weight_for(self, method: str) -> int:
        return self.weights.get(_normalize_key(method), self.default_weight)

    def charge(self, method: str, *, multiplier: int = 1) -> int:
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        credits = self.weight_for(method) * int(multiplier)
        self.quota.charge(credits)
        return credits

    def remaining(self) -> int:
        return self.quota.remaining()

    def is_exhausted(self) -> bool:
        return self.quota.is_exhausted()


class AsyncWeightedCostLimiter:
    """Asyncio mirror for async quota trackers."""

    def __init__(
        self,
        quota,
        *,
        weights: Mapping[str, int] | None = None,
        default_weight: int = 1,
    ):
        if default_weight <= 0:
            raise ValueError("default_weight must be positive")
        self.quota = quota
        self.default_weight = int(default_weight)
        merged = DEFAULT_WEIGHTS | dict(weights or {})
        self.weights = _normalize_weights(merged)

    def weight_for(self, method: str) -> int:
        return self.weights.get(_normalize_key(method), self.default_weight)

    async def charge(self, method: str, *, multiplier: int = 1) -> int:
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        credits = self.weight_for(method) * int(multiplier)
        result = self.quota.charge(credits)
        if inspect.isawaitable(result):
            await result
        return credits

    async def remaining(self) -> int:
        result = self.quota.remaining()
        if inspect.isawaitable(result):
            return await result
        return result

    async def is_exhausted(self) -> bool:
        result = self.quota.is_exhausted()
        if inspect.isawaitable(result):
            return await result
        return result
