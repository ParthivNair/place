"""Magic-link/session token primitives, secret-key hardening, founder gating."""

from __future__ import annotations

import uuid

import pytest

from place.api import security
from place.config import Settings


def _settings(**overrides) -> security.ApiSettings:
    return security.ApiSettings(**overrides)


def test_magic_token_roundtrip_normalizes_email() -> None:
    s = Settings()
    token = security.create_magic_token("  Person@Example.COM ", s)
    assert security.verify_magic_token(token, s) == "person@example.com"


def test_magic_token_tampered_is_rejected() -> None:
    s = Settings()
    token = security.create_magic_token("a@b.co", s)
    assert security.verify_magic_token(token + "x", s) is None


def test_magic_token_wrong_secret_is_rejected() -> None:
    key_a = "a" * 32
    key_b = "b" * 32
    token = security.create_magic_token("a@b.co", Settings(secret_key=key_a))
    assert security.verify_magic_token(token, Settings(secret_key=key_b)) is None


def test_dev_default_secret_never_signs() -> None:
    # The old public literal must not be usable for signing: it is silently
    # replaced by a per-process random key, so a token forged with the
    # literal (the founder-takeover attack) never verifies.
    s = Settings(secret_key="dev-secret-change-me")
    assert s.secret_key != "dev-secret-change-me"
    forged = security.create_magic_token(
        "founder@place.test", Settings.model_construct(secret_key="dev-secret-change-me")
    )
    assert security.verify_magic_token(forged, s) is None
    # unset key falls back to the same per-process ephemeral (dev roundtrip works)
    assert Settings(secret_key="").secret_key == s.secret_key


def test_short_explicit_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(secret_key="tooshort")


def test_magic_token_expired(monkeypatch) -> None:
    s = Settings()
    token = security.create_magic_token("a@b.co", s)
    expired = Settings(magic_link_max_age_s=-1)
    assert security.verify_magic_token(token, expired) is None


def test_session_token_roundtrip() -> None:
    s = Settings()
    uid = uuid.uuid4()
    token = security.create_session_token(uid, s)
    assert security.verify_session_token(token, s) == uid


def test_session_token_garbage_is_none() -> None:
    assert security.verify_session_token("not-a-token", Settings()) is None


def test_is_founder_requires_configured_email() -> None:
    assert not security.is_founder("me@x.co", _settings(founder_email=None))
    assert security.is_founder("Me@X.co", _settings(founder_email="me@x.co"))
    assert not security.is_founder("you@x.co", _settings(founder_email="me@x.co"))
