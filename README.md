# helius-rate-limiter

Do not burn through Helius quota by accident.

![Guard flow](screenshots/guard_flow.svg)

**Helius free is 100k credits per MONTH, not per day.** A `429` body containing
`max usage reached` means monthly exhaustion. The safe default is to rotate to another key
or open a long 24h circuit, while ordinary transient `429`s use short backoff.

## Install

```bash
pip install helius-rate-limiter
```

## 30-second usage

```python
import os
import requests
from helius_limiter import HeliusGuard

keys = [k.strip() for k in os.getenv("HELIUS_API_KEYS", "").split(",") if k.strip()]
guard = HeliusGuard(keys, state_path="helius_state.json")

def call(api_key: str):
    return requests.get(
        os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint"),
        params={"api-key": api_key},
        timeout=20,
    )

response = guard.request(call, credits=1)
```

## Knobs

| Knob | Default |
|---|---:|
| `rps` | `10.0` |
| `monthly_credits` | `100_000` |
| `failure_threshold` | `8` |
| `circuit_open_seconds` | `900` |
| `state_path` | `None` |

Works with `requests`, `httpx`, `aiohttp`, or any object exposing `.status_code`, `.text`,
and `.headers`. You bring the HTTP client.

Powers the on-chain client in **[wallet-cluster-detector](https://github.com/barobaonguyen/wallet-cluster-detector)**.

Built by [barobaonguyen](https://github.com/barobaonguyen). Want the full **scrape -> AI -> alert** bot, not just this piece? -> **[Trawlkit](https://github.com/barobaonguyen)** (one-time kit).
