"""Magic-link routes: dev-mode logging, verify, session cookie, /auth/me."""

from __future__ import annotations

import logging
import uuid

from place.api import security
from place.config import Settings

from .conftest import FakeResult


def test_magic_link_dev_mode_logs_link(client, caplog, monkeypatch) -> None:
    # Hermetic dev mode: a real RESEND_API_KEY in the developer's .env would
    # otherwise route this through Resend (env var overrides env_file; empty
    # string is falsy on the resend_api_key branch).
    monkeypatch.setenv("RESEND_API_KEY", "")
    security.get_api_settings.cache_clear()
    with caplog.at_level(logging.INFO, logger="place.api.auth"):
        resp = client.post("/auth/magic-link", json={"email": "new@example.com"})
    assert resp.status_code == 202
    assert resp.json() == {"sent": True}
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "magic-link (dev" in logged
    token = logged.rsplit("token=", 1)[1].strip()
    assert security.verify_magic_token(token, Settings()) == "new@example.com"


def test_magic_link_rejects_non_email(client) -> None:
    assert client.post("/auth/magic-link", json={"email": "nope"}).status_code == 422


def test_verify_sets_httponly_session_cookie(client, fake_db) -> None:
    uid = uuid.uuid4()
    fake_db.queue(
        FakeResult(
            rows=[
                {
                    "id": uid,
                    "email": "new@example.com",
                    "display_name": None,
                    "power_verifier": False,
                }
            ]
        )
    )
    token = security.create_magic_token("new@example.com", Settings())
    resp = client.post("/auth/verify", json={"token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "new@example.com"
    assert body["is_founder"] is False
    cookie = resp.headers["set-cookie"]
    assert security.SESSION_COOKIE in cookie
    assert "HttpOnly" in cookie
    session_value = resp.cookies[security.SESSION_COOKIE]
    assert security.verify_session_token(session_value, Settings()) == uid


def test_verify_rejects_bad_token(client) -> None:
    resp = client.post("/auth/verify", json={"token": "garbage"})
    assert resp.status_code == 400


def test_me_requires_session(client) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_reads_session_cookie_via_db(client, fake_db, user) -> None:
    token = security.create_session_token(user["id"], Settings())
    client.cookies.set(security.SESSION_COOKIE, token)
    fake_db.queue(FakeResult(rows=[user]))
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == user["email"]


def test_me_founder_flag(client, fake_db, user, monkeypatch) -> None:
    monkeypatch.setenv("FOUNDER_EMAIL", user["email"])
    security.get_api_settings.cache_clear()
    token = security.create_session_token(user["id"], Settings())
    client.cookies.set(security.SESSION_COOKIE, token)
    fake_db.queue(FakeResult(rows=[user]))
    assert client.get("/auth/me").json()["is_founder"] is True
