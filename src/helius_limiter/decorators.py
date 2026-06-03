"""Decorators that apply the limiter primitives to sync or async callables."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _ensure_sync(value, action: str):
    if inspect.isawaitable(value):
        raise TypeError(f"{action} returned an awaitable; use it with an async function")
    return value


def rate_limited(limiter) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
                await _maybe_await(limiter.acquire())
                return await func(*args, **kwargs)

            return cast(Callable[P, R], async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
            _ensure_sync(limiter.acquire(), "limiter.acquire")
            return func(*args, **kwargs)

        return cast(Callable[P, R], sync_wrapper)

    return decorate


def with_circuit(breaker) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
                if await _maybe_await(breaker.is_open()):
                    return None
                try:
                    result = await func(*args, **kwargs)
                except Exception:
                    await _maybe_await(breaker.record_failure())
                    raise
                await _maybe_await(breaker.record_success())
                return result

            return cast(Callable[P, R], async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
            if _ensure_sync(breaker.is_open(), "breaker.is_open"):
                return None
            try:
                result = func(*args, **kwargs)
            except Exception:
                _ensure_sync(breaker.record_failure(), "breaker.record_failure")
                raise
            _ensure_sync(breaker.record_success(), "breaker.record_success")
            return result

        return cast(Callable[P, R], sync_wrapper)

    return decorate


def with_quota(tracker, *, credits: int = 1) -> Callable[[Callable[P, R]], Callable[P, R]]:
    if credits < 0:
        raise ValueError("credits must be non-negative")

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
                if await _maybe_await(tracker.is_exhausted()):
                    return None
                result = await func(*args, **kwargs)
                await _maybe_await(tracker.charge(credits))
                return result

            return cast(Callable[P, R], async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):
            if _ensure_sync(tracker.is_exhausted(), "tracker.is_exhausted"):
                return None
            result = func(*args, **kwargs)
            _ensure_sync(tracker.charge(credits), "tracker.charge")
            return result

        return cast(Callable[P, R], sync_wrapper)

    return decorate
