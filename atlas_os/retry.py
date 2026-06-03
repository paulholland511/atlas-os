"""Reusable retry logic with exponential backoff.

Atlas OS talks to a lot of flaky things — a local LLM that may still be loading a
model, an SMTP server, a git index that another process briefly locked. This
module centralises the "try again, backing off" pattern so every script retries
transient failures the same way instead of each rolling its own loop.

Two entry points cover the common cases:

* :func:`retry_call` — wrap a single call:
      result = retry_call(do_thing, arg, policy=RetryPolicy(attempts=3))
* :func:`retry` — decorate a function so every call retries:
      @retry(attempts=3, base_delay=1.0)
      def fetch(): ...

Both share a :class:`RetryPolicy` (immutable, ``frozen=True``) describing *how
many* times, *how long* to wait, and *which* exceptions count as transient. The
``sleep`` function is injectable so tests run instantly without real delays.
"""

from __future__ import annotations

import functools
import random
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeVar

import requests  # a declared core dependency of atlas-os

T = TypeVar("T")

# Network errors that are virtually always worth retrying. Callers can extend or
# replace this via ``RetryPolicy.retry_on``.
TRANSIENT_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,  # includes ConnectionRefused/Reset/Aborted
    TimeoutError,
    socket.timeout,
    socket.gaierror,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """How a retry should behave.

    ``attempts`` is the *total* number of tries (so ``attempts=3`` means one
    initial call plus up to two retries). ``base_delay`` is the wait after the
    first failure; each subsequent wait multiplies by ``backoff`` and is capped
    at ``max_delay``. ``jitter`` adds ``random.uniform(0, jitter)`` seconds to
    each wait to avoid thundering-herd alignment (0 disables it). ``retry_on``
    lists the exception types treated as transient.
    """

    attempts: int = 3
    base_delay: float = 1.0
    backoff: float = 2.0
    max_delay: float = 30.0
    jitter: float = 0.0
    retry_on: tuple[type[BaseException], ...] = TRANSIENT_NETWORK_ERRORS

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"attempts must be >= 1, got {self.attempts}")
        if self.base_delay < 0 or self.max_delay < 0:
            raise ValueError("delays must be non-negative")

    def delay_before_retry(self, completed_attempt: int) -> float:
        """Seconds to wait after ``completed_attempt`` failed (1-based)."""
        raw = self.base_delay * (self.backoff ** (completed_attempt - 1))
        capped = min(raw, self.max_delay)
        if self.jitter:
            capped += random.uniform(0, self.jitter)
        return capped


# A sensible default for HTTP-ish work: three tries, 1s → 2s backoff.
DEFAULT_POLICY = RetryPolicy()


def retry_call(
    func: Callable[..., T],
    *args: object,
    policy: RetryPolicy = DEFAULT_POLICY,
    should_retry: Callable[[BaseException], bool] | None = None,
    on_retry: Callable[[BaseException, int, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: object,
) -> T:
    """Call ``func(*args, **kwargs)``, retrying transient failures.

    Retries while the raised exception is an instance of ``policy.retry_on`` *and*
    (if given) ``should_retry(exc)`` returns ``True``. After the final attempt the
    last exception is re-raised unchanged, so callers can convert it into a
    domain-specific error. ``on_retry(exc, attempt, delay)`` is invoked before
    each wait — handy for logging "retrying in 2s…". ``sleep`` is injectable for
    tests.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            return func(*args, **kwargs)
        except policy.retry_on as exc:
            if should_retry is not None and not should_retry(exc):
                raise
            last_exc = exc
            if attempt >= policy.attempts:
                break
            delay = policy.delay_before_retry(attempt)
            if on_retry is not None:
                on_retry(exc, attempt, delay)
            sleep(delay)
    assert last_exc is not None  # only reachable after at least one failure
    raise last_exc


def retry(
    policy: RetryPolicy | None = None,
    *,
    attempts: int | None = None,
    base_delay: float | None = None,
    backoff: float | None = None,
    max_delay: float | None = None,
    jitter: float | None = None,
    retry_on: tuple[type[BaseException], ...] | None = None,
    should_retry: Callable[[BaseException], bool] | None = None,
    on_retry: Callable[[BaseException, int, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator form of :func:`retry_call`.

    Either pass a ready :class:`RetryPolicy`, or override individual fields as
    keyword arguments (which are applied on top of the given/default policy)::

        @retry(attempts=5, base_delay=0.5)
        def fetch_models() -> list[str]: ...
    """
    base = policy or RetryPolicy()
    overrides: dict[str, object] = {
        k: v
        for k, v in {
            "attempts": attempts,
            "base_delay": base_delay,
            "backoff": backoff,
            "max_delay": max_delay,
            "jitter": jitter,
            "retry_on": retry_on,
        }.items()
        if v is not None
    }
    resolved = replace(base, **overrides) if overrides else base

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> T:
            return retry_call(
                func,
                *args,
                policy=resolved,
                should_retry=should_retry,
                on_retry=on_retry,
                sleep=sleep,
                **kwargs,
            )

        return wrapper

    return decorator
