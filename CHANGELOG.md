# Changelog

## 0.5.0 - 2026-06-11

- Added sync and async `ConcurrencyLimiter`: a semaphore-style cap for in-flight
  requests, with context-manager support and `acquired` / `released` /
  `saturated` events.
- Added `WeightedCostLimiter` and `AsyncWeightedCostLimiter` to charge existing
  quota trackers by Helius endpoint or RPC method weight instead of by request
  count.
- Added optional `httpx` transport wrappers and a `requests` adapter fallback
  that apply limiter, circuit, and backoff behavior inside the HTTP client layer.
- Added concurrency, weighted-cost, and transport examples plus focused tests for
  sync/async caps, weighted quota math, and mocked HTTP transport behavior.

## 0.4.0 - 2026-06-10

- Added sync and async `AdaptiveLimiter` (AIMD): multiplicatively cut the rate on a 429 /
  "max usage reached" signal (honoring `Retry-After`) and additively recover toward a ceiling,
  emitting `backed_off` / `recovered` events.
- Added `PersistentQuotaTracker` (and async mirror): a calendar-month credit counter backed by a
  single JSON file with atomic writes, so the monthly count survives process restarts.
- Hardened `parse_retry_after` to trim blank headers and reject non-finite numeric values; default
  bounded-exponential backoff behavior is unchanged when the header is absent.
- Added adaptive and persistent-quota examples plus AIMD, rollover/atomic-write, and Retry-After
  parse tests.

## 0.3.0 - 2026-06-06

- Added sync and async token-bucket limiters for burst-friendly request shaping.
- Added an optional Prometheus exporter for existing guard and circuit event callbacks.
- Added token-bucket and Prometheus examples plus test coverage for the new optional paths.

## 0.2.0 - 2026-06-03

- Added asyncio-native rate limiter, quota tracker, circuit breaker, and guard.
- Added sync/async decorators for rate limiting, circuit breaking, and quota charging.
- Added optional metrics events for throttling, circuit trips/resets, and key rotation.
- Added async and decorator examples.

## 0.1.0 - 2026-06-02

- Initial release with sync rate limiting, quota tracking, circuit breaking, key rotation, and a BYO-client guard.
