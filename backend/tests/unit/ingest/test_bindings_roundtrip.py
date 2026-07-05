"""Bindings loader round-trip against the compose postgres (integration).

Lives under tests/unit/ingest/ per component ownership; explicitly marked
integration. Non-destructive by construction: every test runs inside a
single transaction that is rolled back — the shared dev database is never
truncated or mutated, and assertions are deltas so pre-existing skeleton
data (other loaders run against the same DB) cannot break them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from place.ingest import bindings

pytestmark = pytest.mark.integration


@pytest.fixture()
def tx(db_engine):
    """Open transaction, always rolled back — no trace left in the shared DB."""
    conn = db_engine.connect()
    outer = conn.begin()
    yield conn
    outer.rollback()
    conn.close()


def _count(conn, sql: str, **params) -> int:
    return conn.execute(text(sql), params).scalar()


class TestBindingsRoundTrip:
    def test_load_creates_the_launch_bindings(self, tx):
        before_aff = _count(tx, "SELECT count(*) FROM affordances")
        stats = bindings.load(tx)
        assert stats["bindings"] == 16
        assert stats["feeds"] == 19
        assert stats["activities"] >= 26
        # one affordance per binding, whether its place pre-existed or not
        assert _count(tx, "SELECT count(*) FROM affordances") - before_aff == 16
        # every binding place resolves to exactly one canonical row
        for name in ("High Rocks", "Tamanawas Falls", "Haystack Rock", "Dog Mountain"):
            assert _count(tx, "SELECT count(*) FROM places WHERE name = :n", n=name) == 1

    def test_reload_is_idempotent(self, tx):
        first = bindings.load(tx)
        n_places = _count(tx, "SELECT count(*) FROM places")
        n_windows = _count(tx, "SELECT count(*) FROM condition_windows")
        n_aps = _count(tx, "SELECT count(*) FROM access_points")
        again = bindings.load(tx)
        assert again["places_created"] == 0
        assert again["windows_created"] == 0
        assert again["windows_updated"] == first["windows_created"] + first["windows_updated"]
        assert _count(tx, "SELECT count(*) FROM places") == n_places
        assert _count(tx, "SELECT count(*) FROM condition_windows") == n_windows
        assert _count(tx, "SELECT count(*) FROM access_points") == n_aps

    def test_round_trip_preserves_predicates(self, tx):
        bindings.load(tx)
        row = tx.execute(
            text(
                "SELECT cw.predicate, cw.is_gate FROM condition_windows cw "
                "JOIN affordances a ON a.id = cw.affordance_id "
                "JOIN places p ON p.id = a.place_id "
                "WHERE p.name = 'High Rocks' AND a.activity_id = 'wild_swim' "
                "AND cw.wtype = 'hydrological'"
            )
        ).one()
        assert row.is_gate is True
        flow_leaf, temp_leaf = row.predicate["all"]
        assert flow_leaf == {
            "feed": "usgs_nwis:14210000:00060", "op": "<", "value": 1050,
            "exit_value": 1200,
        }
        assert temp_leaf["value"] == 75

    def test_hazard_affordances_start_unpublished(self, tx):
        bindings.load(tx)
        statuses = tx.execute(
            text(
                "SELECT DISTINCT a.status::text FROM affordances a "
                "JOIN activities act ON act.id = a.activity_id "
                "JOIN condition_windows cw ON cw.affordance_id = a.id "
                "WHERE act.hazard_class AND cw.is_gate"
            )
        ).scalars().all()
        assert statuses == ["draft"]

    def test_binding_merges_onto_existing_skeleton_place(self, tx):
        """A place already seeded from OSM absorbs the binding instead of
        being duplicated — the crosswalk in action."""
        existing = _count(tx, "SELECT count(*) FROM places WHERE name = 'Latourell Falls'")
        if existing == 0:
            tx.execute(
                text(
                    "INSERT INTO places (name, kind, geom, osm_id) VALUES "
                    "('Latourell Falls', 'waterfall', "
                    "ST_SetSRID(ST_MakePoint(-122.21769, 45.53716), 4326), 356087149)"
                )
            )
        bindings.load(tx)
        assert _count(tx, "SELECT count(*) FROM places WHERE name = 'Latourell Falls'") == 1
