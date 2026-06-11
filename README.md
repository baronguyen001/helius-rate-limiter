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

Prometheus metrics are optional:

```bash
pip install "helius-rate-limiter[prometheus]"
```

The `httpx` transport is optional:

```bash
pip install "helius-rate-limiter[httpx]"
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

## Async quickstart

```python
import os

from helius_limiter.aio import AsyncGuard

keys = [k.strip() for k in os.getenv("HELIUS_API_KEYS", "").split(",") if k.strip()]
guard = AsyncGuard(keys, state_path="helius_state.json")

async def call(api_key: str):
    return await your_async_http_client.get(
        os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint"),
        params={"api-key": api_key},
    )

response = await guard.request(call, credits=1)
```

## Decorator quickstart

```python
from helius_limiter import CircuitBreaker, QuotaLimiter, RateLimiter
from helius_limiter.decorators import rate_limited, with_circuit, with_quota

limiter = RateLimiter(rps=10)
quota = QuotaLimiter(max_credits=100_000, state_path="helius_state.json")
circuit = CircuitBreaker()

@rate_limited(limiter)
@with_circuit(circuit)
@with_quota(quota, credits=1)
def call_helius(api_key: str):
    return your_sync_http_client.get(
        "https://api.helius.xyz/v0/example-endpoint",
        params={"api-key": api_key},
    )
```

The same decorators work on `async def` functions when you pass the async primitives from
`helius_limiter.aio`.

## Token-bucket quickstart

Use the sliding-window `RateLimiter` when you want steady request spacing. Use
`TokenBucketLimiter` when you want to allow a short burst and then refill at a fixed rate.

```python
from helius_limiter import TokenBucketLimiter

limiter = TokenBucketLimiter(capacity=20, refill_rate=10)

for payload in payloads:
    limiter.acquire()
    send_to_helius(payload)
```

Async code can use the same model:

```python
from helius_limiter import AsyncTokenBucketLimiter

limiter = AsyncTokenBucketLimiter(capacity=20, refill_rate=10)

for payload in payloads:
    await limiter.acquire()
    await send_to_helius(payload)
```

## Adaptive (AIMD) quickstart

A single `429` on the credit-capped free tier should *slow you down*, not trip
the whole circuit. `AdaptiveLimiter` wraps any limiter and applies AIMD
(additive-increase / multiplicative-decrease): cut the rate on a `429` (honoring
`Retry-After`), then recover toward `max_rate` on sustained success.

```python
from helius_limiter import AdaptiveLimiter, RateLimiter
from helius_limiter.backoff import parse_retry_after

limiter = AdaptiveLimiter(RateLimiter(rps=10), max_rate=10, min_rate=0.5)

for payload in payloads:
    limiter.acquire()
    response = send_to_helius(payload)
    if response.status_code == 429:
        limiter.on_429(parse_retry_after(response.headers))  # cut + optional sleep
    else:
        limiter.on_success()                                 # recover toward 10 rps
```

It emits `backed_off` and `recovered` `on_event` callbacks. The async mirror is
`AsyncAdaptiveLimiter` in `helius_limiter` / `helius_limiter.aio`.

## Persistent monthly quota quickstart

Helius free is **credits per calendar MONTH**, so a bot that restarts mid-month
must resume from what it already spent. `PersistentQuotaTracker` keys the window
on `(year, month)` and writes its JSON state atomically (temp file + `os.replace`),
so a crash mid-write can never corrupt the count.

```python
from helius_limiter import PersistentQuotaTracker

quota = PersistentQuotaTracker("/var/data/helius_quota.json", max_credits=100_000)

if not quota.is_exhausted():
    response = call_helius()
    quota.charge(1)          # survives restarts; rolls over on the 1st of the month
```

Bring your own writable path; never commit the state file. The async mirror is
`AsyncPersistentQuotaTracker`.

## Concurrency quickstart

Use `RateLimiter` for request spacing and `ConcurrencyLimiter` for the number of
requests allowed to be in flight at the same time.

```python
from helius_limiter import ConcurrencyLimiter, RateLimiter

rate = RateLimiter(rps=10)
concurrency = ConcurrencyLimiter(max_concurrency=4)

for payload in payloads:
    rate.acquire()
    with concurrency:
        send_to_helius(payload)
```

The async mirror is `AsyncConcurrencyLimiter`.

## Weighted-cost quickstart

Some Helius methods cost more than one credit. `WeightedCostLimiter` wraps any
quota object that exposes the existing `charge(credits)` contract.

```python
from helius_limiter import PersistentQuotaTracker, WeightedCostLimiter

quota = PersistentQuotaTracker("helius_quota.json", max_credits=100_000)
costs = WeightedCostLimiter(quota, weights={"getProgramAccounts": 10})

response = call_helius("getProgramAccounts")
costs.charge("getProgramAccounts")  # charges 10 credits by default
```

The default map includes common RPC methods such as `getBalance`,
`getTransaction`, `getProgramAccounts`, and `searchAssets`. The async mirror is
`AsyncWeightedCostLimiter`.

## httpx transport quickstart

Install the optional extra, then pass the transport to `httpx.Client`. The
transport applies the limiter, circuit breaker, transient retry backoff, and
`Retry-After` handling inside the HTTP client layer.

```python
import os
import httpx

from helius_limiter import HttpxLimiterTransport

transport = HttpxLimiterTransport(rps=10)

with httpx.Client(transport=transport, timeout=20) as client:
    response = client.get(
        os.getenv("HELIUS_URL", "https://api.helius.xyz/v0/example-endpoint"),
        params={"api-key": os.getenv("HELIUS_API_KEY", "")},
    )
```

For `requests`, mount `RequestsLimiterAdapter` on a `requests.Session`.

## Metrics hook

```python
def on_event(event: str) -> None:
    print(event)

guard = HeliusGuard(keys, on_event=on_event)
```

The callback receives `throttled`, `tripped`, `reset`, and `rotated` events when those guard
or circuit transitions happen, `backed_off` / `recovered` from `AdaptiveLimiter`, and
`acquired` / `released` / `saturated` from `ConcurrencyLimiter`. It defaults to `None`.

## Prometheus wiring

```python
import os

from helius_limiter import HeliusGuard, PrometheusExporter

exporter = PrometheusExporter()
exporter.start_http_server(port=int(os.getenv("PROMETHEUS_PORT", "8000")))

guard = HeliusGuard(keys, on_event=exporter.on_event)
```

`PrometheusExporter` increments `helius_limiter_events_total{event="..."}` and updates gauges
for circuit state and last event timestamp. If `prometheus_client` is not installed, creating
the exporter raises a clear error telling you to install `helius-rate-limiter[prometheus]`.

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

Powers the on-chain client in **[wallet-cluster-detector](https://github.com/baronguyen001/wallet-cluster-detector)**.

Built by [baronguyen001](https://github.com/baronguyen001). Want the full **scrape -> AI -> alert** bot, not just this piece? **Trawlkit**: https://github.com/baronguyen001
