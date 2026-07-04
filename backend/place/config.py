"""Application settings.

Single Settings object, loaded from the environment and the repo-root `.env`.
Key-gated integrations (RIDB, Anthropic, Reddit, AirNow, Resend, Sentry, VAPID)
default to None — adapters/workers must raise a clear MissingCredential and
skip-with-log when the key is absent, never fake a response.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# repo root = parent of backend/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Known-weak secrets that must NEVER sign anything: forging a magic-link
# token for FOUNDER_EMAIL with a public literal is a full admin takeover.
_FORBIDDEN_SECRETS = frozenset({"", "dev-secret-change-me", "changeme", "secret"})
SECRET_KEY_MIN_LEN = 32

# One random key per process: dev without SECRET_KEY still works in a single
# uvicorn process (create + verify share it), while a deployment that forgot
# to set SECRET_KEY signs with an unguessable value instead of a public
# literal — sessions break visibly across restarts/workers, nothing forgeable.
_EPHEMERAL_DEV_SECRET = secrets.token_urlsafe(48)


class MissingCredential(RuntimeError):
    """Raised by key-gated components when a required env var is absent."""

    def __init__(self, var: str) -> None:
        super().__init__(f"missing credential: set {var} to enable this component")
        self.var = var


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- works now (dev defaults) ---
    database_url: str = "postgresql+asyncpg://place:place@localhost:5433/place"
    # itsdangerous: magic-link tokens + session cookies. Unset (or the old
    # dev literal) -> per-process random key; explicit keys must be strong.
    secret_key: str = ""
    magic_link_max_age_s: int = 15 * 60
    session_max_age_s: int = 180 * 24 * 3600
    http_user_agent: str = "place-backend/0.1 (+https://github.com/parthivnair/place)"
    data_cache_dir: Path = _REPO_ROOT / "backend" / "data" / "cache"
    evaluator_lockfile: Path = Path("/tmp/place-evaluator.lock")
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    # Founder identity is an env allowlist until users has an is_founder column.
    founder_email: str | None = None

    # --- key-gated (None => component raises MissingCredential and is skipped) ---
    ridb_api_key: str | None = None
    anthropic_api_key: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    airnow_api_key: str | None = None
    resend_api_key: str | None = None
    sentry_dsn: str | None = None
    vapid_private_key: str | None = None
    vapid_public_key: str | None = None
    vapid_subject: str | None = None  # e.g. mailto:you@example.com

    @field_validator("secret_key")
    @classmethod
    def _harden_secret_key(cls, value: str) -> str:
        if value in _FORBIDDEN_SECRETS:
            if value:
                log.warning(
                    "SECRET_KEY is a known-weak literal; refusing to sign with it — "
                    "using a per-process random key (sessions will not survive "
                    "restarts). Set a real SECRET_KEY (>= %d chars).",
                    SECRET_KEY_MIN_LEN,
                )
            return _EPHEMERAL_DEV_SECRET
        if len(value) < SECRET_KEY_MIN_LEN:
            raise ValueError(
                f"SECRET_KEY must be at least {SECRET_KEY_MIN_LEN} characters "
                f"(e.g. `python -c 'import secrets; print(secrets.token_urlsafe(48))'`)"
            )
        return value

    def require(self, var: str) -> str:
        """Return the named credential or raise MissingCredential."""
        value = getattr(self, var.lower())
        if not value:
            raise MissingCredential(var.upper())
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
