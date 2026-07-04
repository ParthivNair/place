"""Auth primitives: magic-link tokens and session cookies (itsdangerous).

Docs/04 section 7: POST /auth/magic-link creates a signed 15-minute token,
POST /auth/verify exchanges it for a long-lived httpOnly session cookie.
Delta noted in the build summary: tokens are expiry-enforced but not
single-use (single-use needs a server-side nonce store the schema lacks).
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from place.config import Settings

MAGIC_SALT = "place.magic-link"
SESSION_SALT = "place.session"
SESSION_COOKIE = "place_session"


class ApiSettings(Settings):
    """Foundation Settings plus API-only knobs.

    `founder_email` lives on place.config.Settings (integration applied) —
    the users table has no is_founder column, so founder identity is an env
    allowlist (FOUNDER_EMAIL) until a column exists.
    """

    magic_link_from: str = "Place <onboarding@resend.dev>"
    session_cookie_secure: bool = False  # flip on behind TLS (Caddy) in prod


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()


def _serializer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=salt)


def create_magic_token(email: str, settings: Settings) -> str:
    return _serializer(settings, MAGIC_SALT).dumps(email.strip().lower())


def verify_magic_token(token: str, settings: Settings) -> str | None:
    """Return the normalized email, or None if invalid/expired."""
    try:
        email = _serializer(settings, MAGIC_SALT).loads(
            token, max_age=settings.magic_link_max_age_s
        )
    except (SignatureExpired, BadSignature):
        return None
    return str(email)


def create_session_token(user_id: uuid.UUID | str, settings: Settings) -> str:
    return _serializer(settings, SESSION_SALT).dumps(str(user_id))


def verify_session_token(token: str, settings: Settings) -> uuid.UUID | None:
    try:
        raw = _serializer(settings, SESSION_SALT).loads(
            token, max_age=settings.session_max_age_s
        )
        return uuid.UUID(str(raw))
    except (SignatureExpired, BadSignature, ValueError):
        return None


def is_founder(email: str, settings: ApiSettings) -> bool:
    if not settings.founder_email:
        return False
    return email.strip().lower() == settings.founder_email.strip().lower()
