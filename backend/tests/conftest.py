"""Shared fixtures.

Markers (declared in pyproject.toml) are applied automatically by directory:
tests/unit -> none, tests/integration -> integration, tests/live -> live.
`live` is deselected by default (addopts) and in CI.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from place.config import Settings, get_settings
from place.db import get_sync_engine
from place.models import metadata

# ---------------------------------------------------------------------------
# marker-by-directory
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/tests/live/" in path:
            item.add_marker(pytest.mark.live)


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Fresh Settings per test; mutate via monkeypatch.setenv before use,
    or setattr on the returned object."""
    get_settings.cache_clear()
    yield Settings()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# integration DB (compose postgres on localhost:5433, migrated to head)
# ---------------------------------------------------------------------------

_APP_TABLES = [t.name for t in metadata.sorted_tables]


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = get_sync_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"integration tests need the compose postgres (make db-up migrate): {exc}")
    yield engine
    engine.dispose()


def _truncate_all(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE " + ", ".join(_APP_TABLES) + " RESTART IDENTITY CASCADE")
        )


@pytest.fixture()
def db(db_engine: Engine) -> Iterator[Engine]:
    """Engine for integration tests; truncates every app table before AND
    after the test, so tests stay order-independent even when the shared dev
    DB carries live ingested data. Re-run ingest after a test pass."""
    _truncate_all(db_engine)
    yield db_engine
    _truncate_all(db_engine)


# ---------------------------------------------------------------------------
# FastAPI app (stub — the API component fills in place.api.app.create_app)
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(settings: Settings):
    try:
        from place.api.app import create_app
    except ImportError:
        pytest.skip("place.api.app.create_app not implemented yet")
    return create_app()
