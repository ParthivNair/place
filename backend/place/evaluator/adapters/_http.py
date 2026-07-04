"""Shared HTTP plumbing for the concrete feed adapters (feed-adapters component).

Every adapter goes through `get_json`: async httpx with a tenacity retry policy
(3 attempts, exponential backoff with jitter) that retries transport errors and
5xx responses but not 4xx — a 400/404 from a feed is a configuration bug, not
a transient failure, and retrying it would only delay the feed_health alert.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from place.config import get_settings

DEFAULT_TIMEOUT_S = 30.0


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


def _retrying() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_S,
        headers={"User-Agent": get_settings().http_user_agent},
        follow_redirects=True,
    )


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """GET `url` and return the parsed JSON body, retrying transient failures.

    If `client` is None an ephemeral client is created for the call; the
    evaluator registry is expected to pass one shared client per sweep.
    """

    async def _once(c: httpx.AsyncClient) -> Any:
        resp = await c.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _run(c: httpx.AsyncClient) -> Any:
        async for attempt in _retrying():
            with attempt:
                return await _once(c)
        raise AssertionError("unreachable")  # pragma: no cover

    if client is not None:
        return await _run(client)
    async with make_client() as ephemeral:
        return await _run(ephemeral)


def point_ref(lat: float, lng: float) -> str:
    """Canonical station_ref for a point feed: '45.45,-121.65' (2 decimals, docs/01 §3)."""
    return f"{lat:.2f},{lng:.2f}"


def slug(name: str) -> str:
    """'Mt Hood' -> 'mt_hood' — station_ref-safe zone/area aliases (no colons)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
