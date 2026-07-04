"""Oregon Hikers fetcher — polite, robots.txt-compliant (docs/03 §1, §5).

Targets the two corpora docs/03 names:
- the Field Guide (community wiki: dense per-place facts), and
- the forum (two decades of dated trip reports — the region's richest
  ``observed_date`` corpus).

Politeness contract, non-negotiable:
- robots.txt is fetched once and checked before EVERY page request;
  disallowed URLs are skipped (never fetched), recorded nowhere.
- minimum 2 seconds between requests (docs/03: "throttled").
- every fetched document cached raw and permanently with fetch metadata.

No credential is involved. This module is implemented and fixture-tested;
a real crawl is a deliberate, later act (docs/03 stage 1) — nothing here
runs at import time.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
import urllib.robotparser
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from place.config import Settings, get_settings

log = logging.getLogger(__name__)

BASE_URL = "https://www.oregonhikers.org"
FIELD_GUIDE_PREFIX = f"{BASE_URL}/field_guide"
FORUM_PREFIX = f"{BASE_URL}/forum"

MIN_INTERVAL_S = 2.0  # hard floor between requests


def field_guide_url(page_title: str) -> str:
    """'Tamanawas Falls Hike' -> the wiki page URL."""
    return f"{FIELD_GUIDE_PREFIX}/{quote(page_title.replace(' ', '_'))}"


def forum_topic_url(topic_id: int) -> str:
    return f"{FORUM_PREFIX}/viewtopic.php?t={topic_id}"


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


class OregonHikersFetcher:
    """robots.txt-checking, throttled fetcher for oregonhikers.org."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        settings = settings or get_settings()
        self._user_agent = settings.http_user_agent
        self._cache_dir = (cache_dir or settings.data_cache_dir) / "oregonhikers"
        self._sleep = sleep
        self._clock = clock
        # Never allow callers to configure below the 2s floor.
        self._min_interval_s = max(min_interval_s, MIN_INTERVAL_S)
        self._last_request_at: float | None = None
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._client = client or httpx.Client(
            headers={"User-Agent": self._user_agent}, timeout=30.0, follow_redirects=True
        )

    # -- robots ---------------------------------------------------------------

    def _load_robots(self) -> urllib.robotparser.RobotFileParser:
        if self._robots is None:
            parser = urllib.robotparser.RobotFileParser()
            try:
                resp = self._request(f"{BASE_URL}/robots.txt")
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                elif resp.status_code >= 500:
                    # Server trouble: treat as full disallow until it recovers.
                    parser.disallow_all = True
                else:
                    # 4xx (no robots.txt): everything is fetchable.
                    parser.allow_all = True
            except httpx.HTTPError:
                parser.disallow_all = True
            self._robots = parser
        return self._robots

    def allowed(self, url: str) -> bool:
        """True when robots.txt permits fetching ``url`` for our user agent."""
        if urlparse(url).netloc not in ("www.oregonhikers.org", "oregonhikers.org"):
            return False  # this fetcher only speaks to oregonhikers.org
        return self._load_robots().can_fetch(self._user_agent, url)

    # -- throttled transport ----------------------------------------------------

    def _request(self, url: str) -> httpx.Response:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            if elapsed < self._min_interval_s:
                self._sleep(self._min_interval_s - elapsed)
        self._last_request_at = self._clock()
        return self._client.get(url, headers={"User-Agent": self._user_agent})

    # -- fetch + cache ------------------------------------------------------------

    def fetch_page(self, url: str, *, kind: str = "page") -> Path | None:
        """Fetch one URL if robots.txt allows; cache raw body with metadata.

        Returns the cache path, or None when robots disallow the URL or the
        server declines (the URL is skipped with a log line, never retried
        in a tight loop).
        """
        if not self.allowed(url):
            log.warning("robots.txt disallows %s — skipping", url)
            return None
        resp = self._request(url)
        if resp.status_code != 200:
            log.warning("oregonhikers %s -> HTTP %d — skipping", url, resp.status_code)
            return None
        path = self._cache_dir / kind / f"{cache_key(url)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "source": "oregonhikers",
            "url": url,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
            "robots_ok": True,
            "kind": kind,
            "content_type": resp.headers.get("content-type", ""),
            "body": resp.text,
        }
        path.write_text(json.dumps(record, ensure_ascii=False))
        return path

    def fetch_field_guide(self, page_titles: Iterable[str]) -> list[Path]:
        """Fetch named Field Guide pages (implemented; NOT run as a crawl now)."""
        written = []
        for title in page_titles:
            if (path := self.fetch_page(field_guide_url(title), kind="field_guide")) is not None:
                written.append(path)
        return written

    def fetch_forum_topics(self, topic_ids: Iterable[int]) -> list[Path]:
        """Fetch forum trip-report topics (implemented; NOT run as a crawl now)."""
        written = []
        for topic_id in topic_ids:
            if (path := self.fetch_page(forum_topic_url(topic_id), kind="forum")) is not None:
                written.append(path)
        return written
