"""Shared HTTP behaviour for the ATS clients. See specs/04-sources.md.

20s timeout, a concurrency cap of 10 concurrent requests process-wide, and a
3-attempt exponential-backoff retry on 5xx/timeouts only, never on 404, so a
dead slug fails fast instead of being retried into a false "flaky" signal.
"""

import asyncio

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

USER_AGENT = "job-engine/0.1 (personal job search tool; contact: somecrazy8@gmail.com)"

REQUEST_SEMAPHORE = asyncio.Semaphore(10)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def retryable():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
    )


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=20.0,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    )
