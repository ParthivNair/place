"""Baseline smoke test: extensions, schema, partitions, and the publication gate."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

REPRESENTATIVE_TABLES = [
    "feeds",
    "feed_readings",
    "feed_health",
    "places",
    "access_points",
    "activities",
    "affordances",
    "condition_windows",
    "condition_states",
    "claims",
    "verifications",
    "users",
    "saves",
    "trips",
    "feed_events",
    "good_now",
    "place_edges",
    "push_subscriptions",
]


def test_extensions_present(db: Engine) -> None:
    with db.connect() as conn:
        rows = conn.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    assert {"postgis", "vector", "pg_trgm"} <= set(rows)


def test_tables_present(db: Engine) -> None:
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).scalars().all()
        partitioned = conn.execute(
            text("SELECT relname FROM pg_class WHERE relkind = 'p'")
        ).scalars().all()
    present = set(rows) | set(partitioned)
    missing = [t for t in REPRESENTATIVE_TABLES if t not in present]
    assert not missing, f"missing tables: {missing}"


def test_feed_readings_partitions(db: Engine) -> None:
    with db.connect() as conn:
        parts = conn.execute(
            text(
                "SELECT inhrelid::regclass::text FROM pg_inherits "
                "WHERE inhparent = 'feed_readings'::regclass"
            )
        ).scalars().all()
    assert "feed_readings_default" in parts
    assert len(parts) >= 3  # default + current + next month


def _mk_affordance(conn, *, activity: str = "wild_swim", hazard: bool = True) -> str:
    conn.execute(
        text(
            "INSERT INTO activities (id, display_name, hazard_class) "
            "VALUES (:a, :a, :h) ON CONFLICT (id) DO NOTHING"
        ),
        {"a": activity, "h": hazard},
    )
    place_id = conn.execute(
        text(
            "INSERT INTO places (name, kind, geom) VALUES "
            "('High Rocks', 'swim_hole', ST_SetSRID(ST_MakePoint(-122.62, 45.44), 4326)) "
            "RETURNING id"
        )
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO affordances (place_id, activity_id) VALUES (:p, :a) RETURNING id"
        ),
        {"p": place_id, "a": activity},
    ).scalar_one()


def test_publication_gate_blocks_unsupported_publish(db: Engine) -> None:
    with db.begin() as conn:
        aff_id = _mk_affordance(conn)
        with pytest.raises(DBAPIError, match="publication gate"):
            with conn.begin_nested():
                conn.execute(
                    text("UPDATE affordances SET status = 'published' WHERE id = :i"),
                    {"i": aff_id},
                )
        # one published llm_extracted claim (single domain) still isn't enough
        conn.execute(
            text(
                "INSERT INTO claims (affordance_id, cclass, stype, source_domain, "
                "log_odds, status) VALUES (:i, 'geomorphic', 'llm_extracted', "
                "'reddit.com', -0.62, 'published')"
            ),
            {"i": aff_id},
        )
        with pytest.raises(DBAPIError, match="publication gate"):
            with conn.begin_nested():
                conn.execute(
                    text("UPDATE affordances SET status = 'published' WHERE id = :i"),
                    {"i": aff_id},
                )


def test_publication_gate_passes_with_two_domains(db: Engine) -> None:
    with db.begin() as conn:
        aff_id = _mk_affordance(conn)
        for domain in ("reddit.com", "oregonhikers.org"):
            conn.execute(
                text(
                    "INSERT INTO claims (affordance_id, cclass, stype, source_domain, "
                    "log_odds, status) VALUES (:i, 'geomorphic', 'llm_extracted', "
                    ":d, -0.12, 'published')"
                ),
                {"i": aff_id, "d": domain},
            )
        conn.execute(
            text("UPDATE affordances SET status = 'published' WHERE id = :i"),
            {"i": aff_id},
        )
        status = conn.execute(
            text("SELECT status FROM affordances WHERE id = :i"), {"i": aff_id}
        ).scalar_one()
    assert status == "published"


def test_publication_gate_passes_with_founder_support(db: Engine) -> None:
    with db.begin() as conn:
        aff_id = _mk_affordance(conn)
        conn.execute(
            text(
                "INSERT INTO claims (affordance_id, cclass, stype, source_domain, "
                "log_odds, status) VALUES (:i, 'hazard_calibration', 'founder_verified', "
                "NULL, 2.94, 'published')"
            ),
            {"i": aff_id},
        )
        conn.execute(
            text("UPDATE affordances SET status = 'published' WHERE id = :i"),
            {"i": aff_id},
        )


def test_truncation_between_tests_left_db_clean(db: Engine) -> None:
    """Runs after the gate tests (alphabetical collection is file order); the
    db fixture must have truncated their rows."""
    with db.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM places")).scalar_one()
    assert n == 0
