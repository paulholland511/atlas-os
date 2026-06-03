"""HTTP requests with explicit timeouts, retries, and human error messages.

Every outbound HTTP call in Atlas OS (LM Studio / Ollama embeddings, model
probes, any OpenAI-compatible endpoint) goes through here so they all share:

* an explicit ``(connect, read)`` timeout — never an unbounded hang;
* exponential-backoff retries on transient failures and retryable status codes
  (429, 500, 502, 503, 504), via :mod:`atlas_os.retry`;
* a clear, actionable error when the endpoint can't be reached, e.g.
  *"Embeddings endpoint at localhost:5555 is not responding. Check that the
  server is running."* — instead of a raw ``ConnectionError`` traceback.

Scripts that monkeypatch ``requests`` directly (for unit tests) don't have to
use this module; it's an opt-in convenience that builds on the shared retry
policy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

import requests

from .retry import RetryPolicy, retry_call

# (connect, read) timeouts in seconds, per the hardening spec.
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 30.0
DEFAULT_TIMEOUT: tuple[float, float] = (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)

# Status codes worth retrying: rate-limiting and transient server errors.
RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# Three tries, 1s → 2s backoff. Tuned for a local model server that may still be
# loading weights on the first request.
HTTP_RETRY_POLICY = RetryPolicy(attempts=3, base_delay=1.0, backoff=2.0)


class NetworkError(RuntimeError):
    """Base class for the errors this module raises (carries the URL)."""

    def __init__(self, message: str, *, url: str) -> None:
        super().__init__(message)
        self.url = url


class EndpointUnreachable(NetworkError):
    """The endpoint could not be reached (connection refused, DNS, timeout)."""


class HTTPStatusError(NetworkError):
    """The endpoint answered, but with an error status after all retries."""

    def __init__(self, message: str, *, url: str, status_code: int) -> None:
        super().__init__(message, url=url)
        self.status_code = status_code


def endpoint_label(url: str) -> str:
    """The ``host:port`` of ``url`` for use in error messages (falls back to url)."""
    netloc = urlsplit(url).netloc
    return netloc or url


def unreachable_message(url: str, service: str | None = None) -> str:
    """Build the standard "X at host:port is not responding" message."""
    name = service or "Endpoint"
    return (
        f"{name} at {endpoint_label(url)} is not responding. "
        "Check that the server is running."
    )


class _RetryableStatus(Exception):
    """Internal: a response whose status code should trigger a retry."""

    def __init__(self, response: requests.Response) -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code}")


def request(
    method: str,
    url: str,
    *,
    service: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    policy: RetryPolicy = HTTP_RETRY_POLICY,
    on_retry: Callable[[BaseException, int, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """Perform an HTTP request with timeouts and retries; return the response.

    Retries transient connection/timeout errors and retryable status codes. On
    persistent failure raises :class:`EndpointUnreachable` (couldn't connect) or
    :class:`HTTPStatusError` (reached, but error status) — both with a clear,
    host-aware message and never a raw traceback for the caller to format.
    """
    attempt_policy = replace(policy, retry_on=(*policy.retry_on, _RetryableStatus))

    def _attempt() -> requests.Response:
        resp = requests.request(
            method, url, headers=headers, params=params, json=json, timeout=timeout
        )
        if resp.status_code in RETRY_STATUS_CODES:
            raise _RetryableStatus(resp)
        return resp

    try:
        return retry_call(_attempt, policy=attempt_policy, on_retry=on_retry, sleep=sleep)
    except _RetryableStatus as exc:
        code = exc.response.status_code
        raise HTTPStatusError(
            f"{service or 'Endpoint'} at {endpoint_label(url)} returned HTTP {code} "
            "after retries.",
            url=url,
            status_code=code,
        ) from exc
    except requests.RequestException as exc:
        raise EndpointUnreachable(unreachable_message(url, service), url=url) from exc


def get_json(
    url: str,
    *,
    service: str | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    policy: RetryPolicy = HTTP_RETRY_POLICY,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET ``url`` and return parsed JSON, raising clear errors on failure."""
    resp = request(
        "GET", url, service=service, headers=headers, params=params,
        timeout=timeout, policy=policy, sleep=sleep,
    )
    return _parse_json(resp, url, service)


def post_json(
    url: str,
    payload: Any,
    *,
    service: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    policy: RetryPolicy = HTTP_RETRY_POLICY,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """POST ``payload`` as JSON to ``url`` and return parsed JSON."""
    resp = request(
        "POST", url, service=service, headers=headers, json=payload,
        timeout=timeout, policy=policy, sleep=sleep,
    )
    return _parse_json(resp, url, service)


def _parse_json(resp: requests.Response, url: str, service: str | None) -> Any:
    if resp.status_code >= 400:
        raise HTTPStatusError(
            f"{service or 'Endpoint'} at {endpoint_label(url)} returned "
            f"HTTP {resp.status_code}.",
            url=url,
            status_code=resp.status_code,
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPStatusError(
            f"{service or 'Endpoint'} at {endpoint_label(url)} returned a non-JSON "
            "response.",
            url=url,
            status_code=resp.status_code,
        ) from exc


def is_reachable(
    url: str,
    *,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
) -> bool:
    """Best-effort single-shot reachability probe (no retries). ``True`` if the
    endpoint answers with any non-5xx status."""
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException:
        return False
    return resp.status_code < 500
