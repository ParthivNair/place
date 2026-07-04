"""Reddit fetcher — official API only, free-tier-respecting (docs/03 §1, §5).

Key-gated: constructing :class:`RedditFetcher` without REDDIT_CLIENT_ID /
REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT raises :class:`MissingCredential`.
The module stays importable without any credential.

Fetchers are dumb on purpose (docs/03 stage 1): raw listing children are
cached as JSON with fetch metadata; all intelligence lives downstream in
the extraction worker.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import httpx

from place.config import Settings, get_settings

log = logging.getLogger(__name__)

# docs/03 §1: the committed Portland corpus subreddits.
SUBREDDITS: tuple[str, ...] = ("Portland", "oregon", "PNWhiking", "OregonCoast")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"

# Free tier is 100 QPM for OAuth clients; stay well inside it.
DEFAULT_MIN_INTERVAL_S = 1.0
PAGE_SIZE = 100

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _cache_path(cache_dir: Path, subreddit: str, fullname: str) -> Path:
    safe = _SAFE_NAME_RE.sub("_", fullname)
    return cache_dir / subreddit / f"{safe}.json"


class RedditFetcher:
    """Fetch subreddit listings + comment trees via the official OAuth API."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    ) -> None:
        settings = settings or get_settings()
        # Key gate: raises MissingCredential when any REDDIT_* var is absent.
        self._client_id = settings.require("reddit_client_id")
        self._client_secret = settings.require("reddit_client_secret")
        self._user_agent = settings.require("reddit_user_agent")
        self._cache_dir = (cache_dir or settings.data_cache_dir) / "reddit"
        self._sleep = sleep
        self._clock = clock
        self._min_interval_s = min_interval_s
        self._last_request_at: float | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._client = client or httpx.Client(
            headers={"User-Agent": self._user_agent}, timeout=30.0
        )

    # -- auth ---------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and self._clock() < self._token_expires_at:
            return self._token
        resp = self._client.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
            headers={"User-Agent": self._user_agent},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        # refresh a minute early
        self._token_expires_at = self._clock() + float(payload.get("expires_in", 3600)) - 60
        return self._token

    # -- rate limiting ------------------------------------------------------

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            if elapsed < self._min_interval_s:
                self._sleep(self._min_interval_s - elapsed)
        self._last_request_at = self._clock()

    def _respect_ratelimit_headers(self, resp: httpx.Response) -> None:
        """Reddit reports X-Ratelimit-Remaining/-Reset; back off near zero."""
        try:
            remaining = float(resp.headers.get("x-ratelimit-remaining", "1"))
            reset_s = float(resp.headers.get("x-ratelimit-reset", "0"))
        except ValueError:
            return
        if remaining < 1.0 and reset_s > 0:
            log.info("reddit rate limit nearly exhausted; sleeping %.0fs", reset_s)
            self._sleep(reset_s)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        resp = self._client.get(
            f"{API_BASE}{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "User-Agent": self._user_agent,
            },
        )
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after", "10"))
            log.warning("reddit 429; retrying after %.0fs", retry_after)
            self._sleep(retry_after)
            resp = self._client.get(
                f"{API_BASE}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "User-Agent": self._user_agent,
                },
            )
        resp.raise_for_status()
        self._respect_ratelimit_headers(resp)
        return resp.json()

    # -- caching ------------------------------------------------------------

    def _write_cache(self, subreddit: str, child: dict[str, Any]) -> Path:
        data = child.get("data", {})
        fullname = f"{child.get('kind', 't3')}_{data.get('id', 'unknown')}"
        permalink = data.get("permalink") or ""
        path = _cache_path(self._cache_dir, subreddit, fullname)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "reddit",
            "url": f"https://www.reddit.com{permalink}" if permalink else None,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
            "robots_ok": True,  # official API — robots.txt does not apply
            "data": child,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
        return path

    # -- public API ----------------------------------------------------------

    def fetch_subreddit(
        self, subreddit: str, *, limit: int = 1000, listing: str = "new"
    ) -> list[Path]:
        """Fetch up to ``limit`` posts from /r/{subreddit}/{listing}, caching each."""
        written: list[Path] = []
        after: str | None = None
        while len(written) < limit:
            page = self._get(
                f"/r/{subreddit}/{listing}",
                params={"limit": min(PAGE_SIZE, limit - len(written)), "after": after},
            )
            children = page.get("data", {}).get("children", [])
            if not children:
                break
            for child in children:
                written.append(self._write_cache(subreddit, child))
            after = page.get("data", {}).get("after")
            if not after:
                break
        log.info("cached %d posts from r/%s", len(written), subreddit)
        return written

    def fetch_comments(self, subreddit: str, post_id: str, *, limit: int = 500) -> list[Path]:
        """Fetch the comment tree for one post; caches each top-level comment."""
        payload = self._get(f"/r/{subreddit}/comments/{post_id}", params={"limit": limit})
        written: list[Path] = []
        # payload is [post_listing, comment_listing]
        if isinstance(payload, list) and len(payload) > 1:
            for child in payload[1].get("data", {}).get("children", []):
                if child.get("kind") == "t1":  # comments only; 'more' stubs skipped
                    written.append(self._write_cache(subreddit, child))
        return written

    def fetch_all(
        self, subreddits: Iterable[str] = SUBREDDITS, *, limit_per_sub: int = 1000
    ) -> list[Path]:
        written: list[Path] = []
        for sub in subreddits:
            written.extend(self.fetch_subreddit(sub, limit=limit_per_sub))
        return written
