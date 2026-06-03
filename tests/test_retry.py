"""Tests for atlas_os.retry — backoff policy, retry_call, and the decorator."""

from __future__ import annotations

import pytest

from atlas_os import retry


class TestRetryPolicy:
    def test_exponential_backoff_with_cap(self) -> None:
        policy = retry.RetryPolicy(base_delay=1.0, backoff=2.0, max_delay=5.0)
        assert policy.delay_before_retry(1) == 1.0
        assert policy.delay_before_retry(2) == 2.0
        assert policy.delay_before_retry(3) == 4.0
        assert policy.delay_before_retry(4) == 5.0  # capped

    def test_rejects_zero_attempts(self) -> None:
        with pytest.raises(ValueError):
            retry.RetryPolicy(attempts=0)

    def test_rejects_negative_delay(self) -> None:
        with pytest.raises(ValueError):
            retry.RetryPolicy(base_delay=-1.0)


class TestRetryCall:
    def test_returns_on_first_success(self) -> None:
        calls = []

        def ok() -> str:
            calls.append(1)
            return "done"

        assert retry.retry_call(ok, sleep=lambda _: None) == "done"
        assert len(calls) == 1

    def test_retries_then_succeeds(self) -> None:
        attempts = {"n": 0}
        slept: list[float] = []

        def flaky() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        policy = retry.RetryPolicy(attempts=5, base_delay=1.0)
        result = retry.retry_call(flaky, policy=policy, sleep=slept.append)
        assert result == "ok"
        assert attempts["n"] == 3
        assert slept == [1.0, 2.0]  # two waits before the third (successful) try

    def test_exhausts_and_reraises_last(self) -> None:
        def always_fails() -> None:
            raise TimeoutError("nope")

        policy = retry.RetryPolicy(attempts=3)
        with pytest.raises(TimeoutError, match="nope"):
            retry.retry_call(always_fails, policy=policy, sleep=lambda _: None)

    def test_non_retryable_exception_propagates_immediately(self) -> None:
        calls = []

        def boom() -> None:
            calls.append(1)
            raise ValueError("not transient")

        policy = retry.RetryPolicy(attempts=3, retry_on=(ConnectionError,))
        with pytest.raises(ValueError):
            retry.retry_call(boom, policy=policy, sleep=lambda _: None)
        assert len(calls) == 1  # never retried

    def test_should_retry_predicate_can_veto(self) -> None:
        calls = []

        def boom() -> None:
            calls.append(1)
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            retry.retry_call(
                boom,
                policy=retry.RetryPolicy(attempts=5),
                should_retry=lambda exc: False,
                sleep=lambda _: None,
            )
        assert len(calls) == 1

    def test_on_retry_callback_is_invoked(self) -> None:
        events: list[tuple[int, float]] = []
        attempts = {"n": 0}

        def flaky() -> str:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ConnectionError("x")
            return "ok"

        retry.retry_call(
            flaky,
            policy=retry.RetryPolicy(attempts=3, base_delay=1.0),
            on_retry=lambda exc, attempt, delay: events.append((attempt, delay)),
            sleep=lambda _: None,
        )
        assert events == [(1, 1.0)]

    def test_passes_through_args_and_kwargs(self) -> None:
        def add(a: int, b: int, *, c: int) -> int:
            return a + b + c

        assert retry.retry_call(add, 1, 2, c=3, sleep=lambda _: None) == 6


class TestRetryDecorator:
    def test_decorates_and_retries(self) -> None:
        attempts = {"n": 0}

        @retry.retry(attempts=3, base_delay=1.0, sleep=lambda _: None)
        def flaky() -> str:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ConnectionError("x")
            return "ok"

        assert flaky() == "ok"
        assert attempts["n"] == 2

    def test_overrides_apply_on_top_of_policy(self) -> None:
        base = retry.RetryPolicy(attempts=1)

        @retry.retry(base, attempts=3, sleep=lambda _: None)
        def flaky(counter: list[int]) -> str:
            counter.append(1)
            if len(counter) < 3:
                raise ConnectionError("x")
            return "ok"

        counter: list[int] = []
        assert flaky(counter) == "ok"
        assert len(counter) == 3
