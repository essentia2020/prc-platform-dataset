"""Polite HTTP client used by every extraction module.

* identifies itself with ``User-Agent: <label>/1.4.0 (mailto:<address>)``;
* keeps at least ``min_interval_seconds`` between requests to one host and
  tightens that interval when a response carries ``X-Rate-Limit-Limit`` /
  ``X-Rate-Limit-Interval`` headers;
* retries HTTP 429, 5xx and transport errors with the configured backoff
  schedule, honouring ``Retry-After`` when present;
* never retries 4xx other than 429 (those are reported as failed attempts);
* returns *every* attempt so the caller can store rejected responses too.

The transport is injectable (``transport(url, headers, timeout) ->
(status, headers, body)``) so tests run entirely offline.  The default
transport uses the standard library only.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

Transport = Callable[[str, dict[str, str], float], tuple[int, dict[str, str], bytes]]

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    """Raised when a page cannot be retrieved within the attempt budget."""


@dataclass
class Attempt:
    number: int
    url: str
    sent_at_utc: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    error: str = ""
    accepted: bool = False
    rejection_reason: str = ""
    stored_response_rel: str = ""
    stored_sha256: str = ""

    @property
    def request_record(self) -> dict:
        return {"url": self.url, "attempt": self.number, "sent_at_utc": self.sent_at_utc}


@dataclass
class PageResult:
    url: str
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def accepted(self) -> Attempt | None:
        for attempt in self.attempts:
            if attempt.accepted:
                return attempt
        return None


def default_transport(url: str, headers: dict[str, str], timeout: float):
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        return float(value)
    try:
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(value)
        return max(0.0, (when.timestamp() - time.time()))
    except (TypeError, ValueError):
        return None


def _parse_rate_limit(headers: dict[str, str]) -> float | None:
    """Minimum interval implied by ``X-Rate-Limit-Limit``/``-Interval``."""
    limit = headers.get("x-rate-limit-limit")
    interval = headers.get("x-rate-limit-interval")
    if not limit or not interval:
        return None
    try:
        n = float(limit)
        seconds = float(re.sub(r"[^\d.]", "", interval) or 0)
    except ValueError:
        return None
    if n <= 0 or seconds <= 0:
        return None
    return seconds / n


class PoliteClient:
    def __init__(self, *, user_agent: str, timeout_seconds: float = 60,
                 max_attempts_per_page: int = 5, backoff_seconds: list[float] | None = None,
                 min_interval_seconds: float = 1.0, accept: str = "application/json",
                 transport: Transport = default_transport, sleeper: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, now_utc: Callable[[], str] | None = None,
                 logger=None) -> None:
        self.user_agent = user_agent
        self.timeout = timeout_seconds
        self.max_attempts = max_attempts_per_page
        self.backoff = list(backoff_seconds or [2, 5, 15, 45, 120])
        self.min_interval = float(min_interval_seconds)
        self.accept = accept
        self._transport = transport
        self._sleep = sleeper
        self._clock = clock
        self._now_utc = now_utc or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._last_request_at: float | None = None
        self._logger = logger

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept": self.accept}

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)

    def _backoff_for(self, attempt_number: int, headers: dict[str, str]) -> float:
        retry_after = _parse_retry_after(headers.get("retry-after"))
        scheduled = self.backoff[min(attempt_number - 1, len(self.backoff) - 1)]
        return max(scheduled, retry_after or 0.0)

    def get_page(self, url: str, validator: Callable[[bytes], str | None] | None = None,
                 on_attempt: Callable[[Attempt], None] | None = None) -> PageResult:
        """Fetch ``url`` with retries.

        ``validator(body)`` returns ``None`` when the body is acceptable or a
        rejection reason (for example "not JSON") that triggers a retry.
        ``on_attempt`` is called after every attempt, accepted or not, so the
        caller can persist the response before the next attempt is made.
        """
        result = PageResult(url=url)
        for number in range(1, self.max_attempts + 1):
            self._throttle()
            sent_at = self._now_utc()
            self._last_request_at = self._clock()
            try:
                status, headers, body = self._transport(url, self.headers, self.timeout)
                attempt = Attempt(number, url, sent_at, status, dict(headers), body)
            except Exception as exc:  # transport-level failure
                attempt = Attempt(number, url, sent_at, None, {}, b"", error=f"{type(exc).__name__}: {exc}")
            implied = _parse_rate_limit(attempt.headers)
            if implied and implied > self.min_interval:
                self.min_interval = implied
            if attempt.status == 200:
                reason = validator(attempt.body) if validator else None
                if reason is None:
                    attempt.accepted = True
                else:
                    attempt.rejection_reason = reason
            elif attempt.status is None:
                attempt.rejection_reason = attempt.error
            else:
                attempt.rejection_reason = f"http {attempt.status}"
            result.attempts.append(attempt)
            if on_attempt:
                on_attempt(attempt)
            if self._logger is not None:
                self._logger.event("http_attempt", url=url, attempt=number, status=attempt.status,
                                   accepted=attempt.accepted, reason=attempt.rejection_reason)
            if attempt.accepted:
                return result
            retryable = attempt.status is None or attempt.status in RETRYABLE_STATUSES \
                or (attempt.status == 200 and attempt.rejection_reason)
            if not retryable:
                break
            if number < self.max_attempts:
                self._sleep(self._backoff_for(number, attempt.headers))
        return result
