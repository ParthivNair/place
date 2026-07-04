"""Auth policy: public vs session-gated vs founder-gated routes."""

from __future__ import annotations

import uuid

from place.api import security

from .conftest import FakeResult

AFF = str(uuid.uuid4())


def test_feed_is_public(client, fake_db) -> None:
    fake_db.queue(FakeResult(rows=[]))
    resp = client.get("/feed", params={"lat": 45.5, "lng": -122.6})
    assert resp.status_code == 200
    assert resp.json()["cards"] == []


def test_places_search_is_public(client, fake_db) -> None:
    fake_db.queue(FakeResult(rows=[]))
    resp = client.get("/places/search", params={"lat": 45.5, "lng": -122.6})
    assert resp.status_code == 200


def test_writes_require_session(client) -> None:
    checks = [
        ("post", "/saves", {"affordance_id": AFF, "kind": "want_to"}),
        ("post", "/trips", {"affordance_id": AFF, "planned_date": "2026-07-04"}),
        ("post", "/verdicts", {"claim_id": AFF, "verdict": "confirm"}),
        ("post", "/events", {"affordance_id": AFF, "etype": "shown"}),
        (
            "post",
            "/push/subscribe",
            {"endpoint": "https://push.example/x", "keys": {"p256dh": "k", "auth": "a"}},
        ),
    ]
    for method, url, payload in checks:
        resp = getattr(client, method)(url, json=payload)
        assert resp.status_code == 401, url
    assert client.delete(
        "/saves", params={"affordance_id": AFF, "kind": "want_to"}
    ).status_code == 401
    assert client.get("/saves").status_code == 401


def test_admin_requires_founder_not_just_session(auth_client) -> None:
    # session user exists but FOUNDER_EMAIL is not theirs
    assert auth_client.get("/admin/review-queue").status_code == 403
    assert (
        auth_client.post(
            "/admin/review-queue", json={"claim_id": AFF, "action": "approve"}
        ).status_code
        == 403
    )


def test_admin_allows_founder(auth_client, fake_db, user, monkeypatch) -> None:
    monkeypatch.setenv("FOUNDER_EMAIL", user["email"].upper())  # case-insensitive
    security.get_api_settings.cache_clear()
    fake_db.queue(FakeResult(rows=[]))
    assert auth_client.get("/admin/review-queue").status_code == 200
