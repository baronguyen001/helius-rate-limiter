import asyncio

from helius_limiter.aio import AsyncQuotaTracker
from helius_limiter.persist import PersistentQuotaTracker
from helius_limiter.quota import QuotaLimiter
from helius_limiter.weighted import AsyncWeightedCostLimiter, WeightedCostLimiter


def run(coro):
    return asyncio.run(coro)


def test_weighted_charge_uses_default_method_weight():
    quota = QuotaLimiter(max_credits=20)
    limiter = WeightedCostLimiter(quota)

    charged = limiter.charge("getProgramAccounts")

    assert charged == 10
    assert quota.remaining() == 10


def test_weighted_charge_allows_overrides_and_multiplier():
    quota = QuotaLimiter(max_credits=20)
    limiter = WeightedCostLimiter(
        quota,
        weights={"getBalance": 3, "customEndpoint": 4},
        default_weight=2,
    )

    assert limiter.charge("getBalance") == 3
    assert limiter.charge("customEndpoint", multiplier=2) == 8
    assert limiter.charge("unknownMethod") == 2
    assert quota.remaining() == 7


def test_weighted_limiter_persists_through_existing_quota_contract(tmp_path):
    state_path = tmp_path / "quota.json"
    quota = PersistentQuotaTracker(str(state_path), max_credits=20)
    limiter = WeightedCostLimiter(quota)

    limiter.charge("getTransaction")

    fresh = PersistentQuotaTracker(str(state_path), max_credits=20)
    assert fresh.remaining() == 15


def test_async_weighted_limiter_charges_async_quota():
    async def scenario():
        quota = AsyncQuotaTracker(max_credits=20)
        limiter = AsyncWeightedCostLimiter(quota, weights={"getBalance": 2})

        charged = await limiter.charge("getBalance", multiplier=3)

        assert charged == 6
        assert await limiter.remaining() == 14
        assert not await limiter.is_exhausted()

    run(scenario())
