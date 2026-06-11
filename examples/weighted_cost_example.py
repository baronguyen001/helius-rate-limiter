"""Charge monthly quota by Helius method cost instead of by request count."""

from __future__ import annotations

import os

import requests

from helius_limiter import PersistentQuotaTracker, WeightedCostLimiter

HELIUS_RPC_URL = os.getenv("HELIUS_RPC_URL", "https://mainnet.helius-rpc.com/")
API_KEY = os.getenv("HELIUS_API_KEY", "")

quota = PersistentQuotaTracker(
    os.getenv("HELIUS_QUOTA_STATE", "helius_quota.json"),
    max_credits=int(os.getenv("HELIUS_MONTHLY_CREDITS", "100000")),
)
costs = WeightedCostLimiter(
    quota,
    weights={
        "getProgramAccounts": int(os.getenv("GET_PROGRAM_ACCOUNTS_WEIGHT", "10")),
    },
)


def rpc(method: str, params: list):
    if costs.is_exhausted():
        raise RuntimeError("monthly Helius quota is exhausted")

    response = requests.post(
        HELIUS_RPC_URL,
        params={"api-key": API_KEY},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20,
    )
    response.raise_for_status()
    costs.charge(method)
    return response.json()


if __name__ == "__main__":
    result = rpc("getBalance", [os.getenv("SOLANA_ADDRESS", "")])
    print(result)
