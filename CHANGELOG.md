# Changelog

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
