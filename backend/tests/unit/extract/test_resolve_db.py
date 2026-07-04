"""Resolution against seeded fixture places (needs the compose postgres)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from place.extract.resolve import find_candidates, resolve_claim_row
from place.extract.worker import DEFAULT_MODEL, extractor_version

EXTRACTOR_VERSION = extractor_version("anthropic", DEFAULT_MODEL)

pytestmark = pytest.mark.integration

HIGH_ROCKS = (-122.5560, 45.4172)  # Clackamas at Gladstone
PDX = (-122.658, 45.512)


@pytest.fixture()
def seeded(db: Engine) -> Engine:
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO activities (id, display_name, hazard_class) VALUES "
                "('wild_swim', 'Wild swim', true) ON CONFLICT (id) DO NOTHING"
            )
        )
        for name, kind, lon, lat in [
            ("High Rocks", "swim_hole", *HIGH_ROCKS),
            ("Rocky Butte", "viewpoint", -122.5636, 45.5462),
            ("Latourell Falls", "waterfall", -122.2178, 45.5387),
        ]:
            conn.execute(
                text(
                    "INSERT INTO places (name, kind, geom) VALUES "
                    "(:n, :k, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))"
                ),
                {"n": name, "k": kind, "lon": lon, "lat": lat},
            )
    return db


def claim_row_fixture(place_ref: str) -> dict:
    return {
        "place_ref": place_ref,
        "activity": "wild_swim",
        "cclass": "hazard_calibration",
        "stype": "llm_extracted",
        "source_url": "https://www.reddit.com/r/Portland/comments/aa1/",
        "source_domain": "reddit.com",
        "quote_internal": "felt safe around 900 cfs",
        "condition_text": "safe around 900 cfs",
        "observed_date": "2024-07-13",
        "extractor_ver": EXTRACTOR_VERSION,
        "self_conf": 0.7,
        "status": "review",
        "log_odds": -0.619,
        "doc_id": "reddit-test",
    }


def test_find_candidates_ranks_by_trigram_similarity(seeded: Engine) -> None:
    with seeded.connect() as conn:
        candidates = find_candidates(conn, "high rocks")
    assert candidates
    assert candidates[0].name == "High Rocks"
    assert candidates[0].similarity > 0.5


def test_geo_hint_populates_distance(seeded: Engine) -> None:
    with seeded.connect() as conn:
        candidates = find_candidates(conn, "high rocks", near=PDX)
    assert candidates[0].distance_m is not None
    assert 0 < candidates[0].distance_m < 30_000


def test_resolve_inserts_claim_under_matched_place(
    seeded: Engine, tmp_path: Path
) -> None:
    unresolved = tmp_path / "unresolved.jsonl"
    with seeded.begin() as conn:
        claim_id = resolve_claim_row(
            conn, claim_row_fixture("high rocks"), near=PDX, unresolved_path=unresolved
        )
        assert claim_id is not None
        row = conn.execute(
            text(
                """
                SELECT c.status, c.stype, c.extractor_ver, c.quote_internal,
                       p.name AS place_name, a.activity_id, a.status AS a_status
                  FROM claims c
                  JOIN affordances a ON a.id = c.affordance_id
                  JOIN places p ON p.id = a.place_id
                 WHERE c.id = :id
                """
            ),
            {"id": claim_id},
        ).one()
    assert row.place_name == "High Rocks"
    assert row.activity_id == "wild_swim"
    assert row.status == "review"  # nothing auto-publishes (docs/03 §2 stage 5)
    assert row.a_status == "draft"
    assert row.stype == "llm_extracted"
    assert row.extractor_ver == EXTRACTOR_VERSION
    assert not unresolved.exists()


def test_resolve_reuses_existing_affordance(seeded: Engine, tmp_path: Path) -> None:
    unresolved = tmp_path / "unresolved.jsonl"
    with seeded.begin() as conn:
        id1 = resolve_claim_row(conn, claim_row_fixture("High Rocks"), unresolved_path=unresolved)
        id2 = resolve_claim_row(conn, claim_row_fixture("High Rocks"), unresolved_path=unresolved)
        assert id1 != id2
        n_affordances = conn.execute(text("SELECT count(*) FROM affordances")).scalar()
    assert n_affordances == 1


def test_unmatched_place_ref_is_parked_with_ref_preserved(
    seeded: Engine, tmp_path: Path
) -> None:
    unresolved = tmp_path / "unresolved.jsonl"
    ref = "the falls past the second bridge on Eagle Creek"
    with seeded.begin() as conn:
        claim_id = resolve_claim_row(
            conn, claim_row_fixture(ref), unresolved_path=unresolved
        )
        assert claim_id is None
        assert conn.execute(text("SELECT count(*) FROM claims")).scalar() == 0
    parked = json.loads(unresolved.read_text().splitlines()[0])
    assert parked["place_ref"] == ref
    assert parked["unresolved_reason"] == "no confident place match"


def test_unknown_activity_is_parked(seeded: Engine, tmp_path: Path) -> None:
    unresolved = tmp_path / "unresolved.jsonl"
    row = claim_row_fixture("High Rocks") | {"activity": "unicycle_polo"}
    with seeded.begin() as conn:
        assert resolve_claim_row(conn, row, unresolved_path=unresolved) is None
    parked = json.loads(unresolved.read_text().splitlines()[0])
    assert "unicycle_polo" in parked["unresolved_reason"]
