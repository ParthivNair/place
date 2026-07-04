"""Oregon Hikers fetcher: robots.txt respect, throttling, caching (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from place.config import Settings
from place.extract.fetch_oregonhikers import (
    MIN_INTERVAL_S,
    OregonHikersFetcher,
    cache_key,
    field_guide_url,
    forum_topic_url,
)

ROBOTS = """\
User-agent: *
Disallow: /forum/private/
Disallow: /admin/
"""


def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_cache_dir=tmp_path)


def make_fetcher(tmp_path: Path, handler, *, sleeps: list[float] | None = None):
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.001
        return state["t"]

    return OregonHikersFetcher(
        settings(tmp_path),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps if sleeps is not None else []).append,
        clock=clock,
    )


def default_handler(requests: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(
            200,
            text="<html><head><script>var x;</script></head>"
            "<body><h1>Tamanawas Falls</h1><p>Roaring after the storm.</p></body></html>",
            headers={"content-type": "text/html"},
        )

    return handler


def test_url_builders() -> None:
    assert (
        field_guide_url("Tamanawas Falls Hike")
        == "https://www.oregonhikers.org/field_guide/Tamanawas_Falls_Hike"
    )
    assert forum_topic_url(123) == "https://www.oregonhikers.org/forum/viewtopic.php?t=123"


def test_disallowed_url_is_never_fetched(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    fetcher = make_fetcher(tmp_path, default_handler(requests))
    result = fetcher.fetch_page("https://www.oregonhikers.org/forum/private/topic1")
    assert result is None
    # only robots.txt itself was requested — the disallowed page never was
    assert [r.url.path for r in requests] == ["/robots.txt"]


def test_allowed_url_is_fetched_and_cached_with_metadata(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    fetcher = make_fetcher(tmp_path, default_handler(requests))
    url = field_guide_url("Tamanawas Falls Hike")
    path = fetcher.fetch_page(url, kind="field_guide")
    assert path is not None
    record = json.loads(path.read_text())
    assert record["source"] == "oregonhikers"
    assert record["url"] == url
    assert record["robots_ok"] is True
    assert "Tamanawas Falls" in record["body"]
    assert path == tmp_path / "oregonhikers" / "field_guide" / f"{cache_key(url)}.json"


def test_foreign_domains_are_refused(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    fetcher = make_fetcher(tmp_path, default_handler(requests))
    assert fetcher.allowed("https://www.alltrails.com/anything") is False
    assert fetcher.fetch_page("https://www.alltrails.com/anything") is None
    assert requests == []  # not even robots.txt — we never talk to other hosts


def test_min_two_seconds_between_requests(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, default_handler(requests), sleeps=sleeps)
    fetcher.fetch_page(field_guide_url("A"))
    fetcher.fetch_page(field_guide_url("B"))
    # robots.txt + page A + page B = 3 requests, 2 enforced gaps of ~2s
    assert len(sleeps) >= 2
    assert all(s > 1.9 for s in sleeps)


def test_min_interval_cannot_be_configured_below_floor(tmp_path: Path) -> None:
    fetcher = OregonHikersFetcher(
        settings(tmp_path),
        client=httpx.Client(transport=httpx.MockTransport(default_handler([]))),
        min_interval_s=0.01,
    )
    assert fetcher._min_interval_s == MIN_INTERVAL_S


def test_robots_server_error_disallows_everything(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        raise AssertionError("page must not be fetched when robots.txt is unavailable")

    fetcher = make_fetcher(tmp_path, handler)
    assert fetcher.fetch_page(field_guide_url("Anything")) is None


def test_missing_robots_allows_fetching(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})

    fetcher = make_fetcher(tmp_path, handler)
    assert fetcher.fetch_page(field_guide_url("Anything")) is not None


def test_non_200_page_is_skipped_not_cached(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(404)

    fetcher = make_fetcher(tmp_path, handler)
    assert fetcher.fetch_page(field_guide_url("Gone")) is None
    assert not list((tmp_path / "oregonhikers").rglob("*.json"))


def test_fetch_helpers_batch_urls(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    fetcher = make_fetcher(tmp_path, default_handler(requests))
    guide = fetcher.fetch_field_guide(["Elowah Falls Hike"])
    forum = fetcher.fetch_forum_topics([42])
    assert len(guide) == 1 and len(forum) == 1
    assert json.loads(forum[0].read_text())["kind"] == "forum"
