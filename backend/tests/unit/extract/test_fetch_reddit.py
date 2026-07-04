"""Reddit fetcher: key gating, caching, and rate-limit behavior (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from place.config import MissingCredential, Settings
from place.extract.fetch_reddit import SUBREDDITS, RedditFetcher


def keyless_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def keyed_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        reddit_client_id="cid",
        reddit_client_secret="secret",
        reddit_user_agent="place-test/0.1",
        data_cache_dir=tmp_path,
    )


def test_subreddits_match_docs() -> None:
    assert SUBREDDITS == ("Portland", "oregon", "PNWhiking", "OregonCoast")


def test_missing_credentials_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(MissingCredential):
        RedditFetcher(keyless_settings())


def _listing(children: list[dict], after: str | None) -> dict:
    return {"kind": "Listing", "data": {"children": children, "after": after}}


def _post(post_id: str, title: str) -> dict:
    return {
        "kind": "t3",
        "data": {
            "id": post_id,
            "title": title,
            "selftext": f"body of {post_id}",
            "permalink": f"/r/Portland/comments/{post_id}/x/",
            "created_utc": 1720000000,
        },
    }


def make_fetcher(tmp_path: Path, handler, *, sleeps: list[float], clock_value=None):
    """Fetcher wired to a MockTransport, a recording sleep, and a fake clock."""
    state = {"t": 0.0}

    def clock() -> float:
        if clock_value is not None:
            return clock_value
        state["t"] += 0.001  # nearly-frozen clock: every gap under min_interval
        return state["t"]

    transport = httpx.MockTransport(handler)
    return RedditFetcher(
        keyed_settings(tmp_path),
        client=httpx.Client(transport=transport),
        sleep=sleeps.append,
        clock=clock,
    )


def test_fetch_subreddit_caches_raw_json_with_metadata(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.url.host == "oauth.reddit.com"
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["User-Agent"] == "place-test/0.1"
        return httpx.Response(
            200, json=_listing([_post("aa1", "High Rocks in July"), _post("aa2", "Swim?")], None)
        )

    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, handler, sleeps=sleeps)
    written = fetcher.fetch_subreddit("Portland", limit=10)

    assert len(written) == 2
    record = json.loads(written[0].read_text())
    assert record["source"] == "reddit"
    assert record["robots_ok"] is True
    assert record["url"].startswith("https://www.reddit.com/r/Portland/comments/aa1")
    assert record["fetched_at"]
    assert record["data"]["data"]["title"] == "High Rocks in July"
    assert written[0].parent == tmp_path / "reddit" / "Portland"


def test_pagination_follows_after_cursor(tmp_path: Path) -> None:
    pages = [
        _listing([_post("p1", "one")], "t3_p1"),
        _listing([_post("p2", "two")], None),
    ]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        page = pages[calls["n"]]
        calls["n"] += 1
        return httpx.Response(200, json=page)

    fetcher = make_fetcher(tmp_path, handler, sleeps=[])
    written = fetcher.fetch_subreddit("oregon", limit=10)
    assert len(written) == 2
    assert calls["n"] == 2


def test_min_interval_throttle_sleeps_between_requests(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(200, json=_listing([_post("q1", "x")], None))

    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, handler, sleeps=sleeps)
    fetcher.fetch_subreddit("Portland", limit=1)
    fetcher.fetch_subreddit("oregon", limit=1)
    # second API request must have been preceded by a near-full-interval sleep
    assert sleeps and max(sleeps) > 0.9


def test_ratelimit_headers_trigger_backoff(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            200,
            json=_listing([_post("r1", "x")], None),
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "42"},
        )

    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, handler, sleeps=sleeps)
    fetcher.fetch_subreddit("Portland", limit=1)
    assert 42.0 in sleeps


def test_429_is_retried_after_retry_after(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json=_listing([_post("s1", "x")], None))

    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, handler, sleeps=sleeps)
    written = fetcher.fetch_subreddit("Portland", limit=1)
    assert len(written) == 1
    assert 7.0 in sleeps


def test_fetch_comments_caches_only_comments(tmp_path: Path) -> None:
    comment = {
        "kind": "t1",
        "data": {
            "id": "c1",
            "body": "went last weekend, water was perfect",
            "permalink": "/r/Portland/comments/aa1/x/c1/",
            "created_utc": 1720050000,
        },
    }
    more = {"kind": "more", "data": {"id": "m1"}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            200,
            json=[_listing([_post("aa1", "t")], None), _listing([comment, more], None)],
        )

    fetcher = make_fetcher(tmp_path, handler, sleeps=[])
    written = fetcher.fetch_comments("Portland", "aa1")
    assert len(written) == 1
    record = json.loads(written[0].read_text())
    assert record["data"]["kind"] == "t1"
