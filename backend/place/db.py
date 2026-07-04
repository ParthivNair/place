"""Database plumbing.

- One shared SQLAlchemy MetaData (Core only, no ORM).
- Async engine (asyncpg) for the API/evaluator; sync URL helper (psycopg) for
  Alembic and scripts.
- Minimal PostGIS/pgvector column types (geoalchemy2 is deliberately not a
  dependency; the migration is hand-written SQL, these types only need to
  round-trip in Core queries).
- feed_readings monthly-partition helper (idempotent; call at evaluator startup).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Connection, MetaData, text
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.types import UserDefinedType

from place.config import Settings, get_settings

metadata = MetaData()


class Geometry(UserDefinedType):
    """PostGIS geometry column. Values pass through as WKT/WKB-hex text;
    use ST_* SQL functions for construction and math."""

    cache_ok = True

    def __init__(self, geometry_type: str = "Point", srid: int = 4326) -> None:
        self.geometry_type = geometry_type
        self.srid = srid

    def get_col_spec(self, **_: object) -> str:
        return f"geometry({self.geometry_type},{self.srid})"


class Vector(UserDefinedType):
    """pgvector column; values are lists of floats serialized by the driver as text."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dim})"


def sync_database_url(url: str | None = None) -> str:
    """asyncpg runtime URL -> psycopg sync URL (Alembic, scripts)."""
    url = url or get_settings().database_url
    return url.replace("+asyncpg", "+psycopg")


def get_async_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def get_sync_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    return create_engine(sync_database_url(settings.database_url), pool_pre_ping=True)


# ---------------------------------------------------------------------------
# feed_readings monthly partitions
# ---------------------------------------------------------------------------

def _month_start(d: dt.date) -> dt.date:
    return d.replace(day=1)


def _next_month(d: dt.date) -> dt.date:
    return (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def feed_readings_partition_statements(now: dt.datetime | None = None) -> list[str]:
    """DDL for the current and next month's feed_readings partitions (idempotent)."""
    now = now or dt.datetime.now(dt.UTC)
    start = _month_start(now.date())
    stmts: list[str] = []
    for _ in range(2):
        end = _next_month(start)
        stmts.append(
            f"CREATE TABLE IF NOT EXISTS feed_readings_y{start.year}m{start.month:02d} "
            f"PARTITION OF feed_readings "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        )
        start = end
    return stmts


def ensure_feed_readings_partitions(
    conn: Connection, now: dt.datetime | None = None
) -> None:
    """Idempotently create current+next month partitions.

    The DEFAULT partition (created in the baseline migration) catches anything
    else; keep it empty by running this ahead of each month boundary (the
    evaluator calls it at startup), because creating a partition whose range
    already has rows sitting in DEFAULT raises an error.
    """
    for stmt in feed_readings_partition_statements(now):
        conn.execute(text(stmt))
