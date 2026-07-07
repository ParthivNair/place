"""Region tooling end-to-end: proposals -> review queue, coverage counts.

Everything the proposals loader writes must land at status='review' and must
NOT satisfy the publication gate (docs/00 §7 "Claim"; trigger in alembic
0001) — a review-status claim is not a published claim, so publishing the
affordance still raises. Re-running a file must converge (no dup rows).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from place.ingest import bindings, proposals
from place.ingest.regions import coverage_report, load_regions, pick_next, region_by_slug

# Two proposals: one matches a pre-seeded place ~170 m away (crosswalk merge),
# one is genuinely new. Coordinates are inside the clackamas/gorge regions.
PROPOSALS_YAML = """\
proposals:
  - place:
      name: High Rocks
      lat: 45.4415
      lng: -122.6205
      kind: swim_hole
    activity_id: wild_swim
    claim:
      text: "Deep pool below the ledges; locals jump here in July."
      source_url: "https://www.oregonhikers.org/field_guide/High_Rocks"
      source_type: llm_extracted
      observed_date: 2025-07-15
    dog_ok: false
    kid_ok: false
  - place:
      name: Wahclella Falls Pool
      lat: 45.6170
      lng: -121.9540
      kind: waterfall
    activity_id: waterfall_view
    claim:
      text: "Trail reopened after the slide; bridge crossing intact as of May."
      source_url: "https://www.reddit.com/r/Portland/comments/wahclella"
      source_type: user_reported
      observed_date: 2026-05-20
      class: access
"""


def _write(tmp_path: Path, content: str = PROPOSALS_YAML) -> Path:
    path = tmp_path / "proposals.yaml"
    path.write_text(content)
    return path


def _seed(conn) -> None:
    bindings.load_activities(conn)
    # skeleton row the first proposal should merge onto, not duplicate
    conn.execute(
        text(
            "INSERT INTO places (name, kind, geom) VALUES "
            "('High Rocks', 'swim_hole', ST_SetSRID(ST_MakePoint(-122.62, 45.44), 4326))"
        )
    )


def test_proposals_end_to_end_and_idempotent(db: Engine, tmp_path: Path) -> None:
    path = _write(tmp_path)
    with db.begin() as conn:
        _seed(conn)
        stats = proposals.load(conn, path)

    assert stats["places_matched"] == 1  # High Rocks merged onto the seeded row
    assert stats["places_created"] == 1  # Wahclella is new
    assert stats["affordances_created"] == 2
    assert stats["claims_created"] == 2
    assert stats["claims_skipped"] == 0

    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM places")).scalar_one() == 2
        aff = conn.execute(
            text("SELECT status::text, dog_ok, kid_ok FROM affordances")
        ).all()
        assert [row[0] for row in aff] == ["review", "review"]  # never published
        claims = conn.execute(
            text(
                "SELECT status::text, stype::text, source_domain, log_odds, "
                "quote_internal, extractor_ver FROM claims ORDER BY stype"
            )
        ).mappings().all()
        assert len(claims) == 2
        assert all(c["status"] == "review" for c in claims)
        assert all(c["extractor_ver"] == proposals.PROPOSALS_VERSION for c in claims)
        by_stype = {c["stype"]: c for c in claims}
        assert by_stype["llm_extracted"]["source_domain"] == "oregonhikers.org"
        assert float(by_stype["llm_extracted"]["log_odds"]) == pytest.approx(-0.619, abs=1e-3)
        assert by_stype["user_reported"]["source_domain"] == "reddit.com"
        assert float(by_stype["user_reported"]["log_odds"]) == pytest.approx(0.2007, abs=1e-3)

    # re-run: same file converges — no new places/affordances/claims
    with db.begin() as conn:
        rerun = proposals.load(conn, path)
    assert rerun["claims_created"] == 0
    assert rerun["claims_skipped"] == 2
    assert rerun["places_created"] == 0
    assert rerun["affordances_created"] == 0
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM claims")).scalar_one() == 2
        assert conn.execute(text("SELECT count(*) FROM places")).scalar_one() == 2


def test_review_claims_do_not_satisfy_the_publication_gate(db: Engine, tmp_path: Path) -> None:
    path = _write(tmp_path)
    with db.begin() as conn:
        _seed(conn)
        proposals.load(conn, path)
        aff_id = conn.execute(text("SELECT id FROM affordances LIMIT 1")).scalar_one()
        with pytest.raises(DBAPIError, match="publication gate"):
            with conn.begin_nested():
                conn.execute(
                    text("UPDATE affordances SET status = 'published' WHERE id = :i"),
                    {"i": aff_id},
                )


def test_invalid_file_writes_nothing(db: Engine, tmp_path: Path) -> None:
    bad = PROPOSALS_YAML.replace("activity_id: wild_swim", "activity_id: jetski")
    path = _write(tmp_path, bad)
    with db.begin() as conn:
        _seed(conn)
    with pytest.raises(proposals.ProposalError, match="jetski"):
        with db.begin() as conn:
            proposals.load(conn, path)
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM claims")).scalar_one() == 0
        # only the seeded skeleton row survives
        assert conn.execute(text("SELECT count(*) FROM places")).scalar_one() == 1


def test_coverage_counts_and_next_pick(db: Engine) -> None:
    regions = load_regions()
    pdx = region_by_slug(regions, "pdx-west")
    bend = region_by_slug(regions, "bend")
    with db.begin() as conn:
        bindings.load_activities(conn)
        place_ids = []
        for name, lat, lng in (
            ("Forest Park Fire Lane 7", pdx.lat, pdx.lng),
            ("Sauvie Overlook", pdx.lat + 0.07, pdx.lng + 0.10),  # ~10 km, inside
            ("Tumalo Falls", bend.lat, bend.lng),  # bend only
        ):
            place_ids.append(
                conn.execute(
                    text(
                        "INSERT INTO places (name, kind, geom) VALUES "
                        "(:n, 'viewpoint', ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)) "
                        "RETURNING id"
                    ),
                    {"n": name, "lat": lat, "lng": lng},
                ).scalar_one()
            )
        conn.execute(
            text(
                "INSERT INTO affordances (place_id, activity_id, status) "
                "VALUES (:p, 'viewpoint', 'review')"
            ),
            {"p": place_ids[0]},
        )
    with db.connect() as conn:
        report = coverage_report(conn, regions)
    by_slug = {c.region.slug: c for c in report}
    assert by_slug["pdx-west"].places == 2
    assert by_slug["pdx-west"].affordances["review"] == 1
    assert by_slug["pdx-west"].affordances_total == 1
    assert by_slug["bend"].places == 1
    assert by_slug["eugene"].places == 0
    # everything is far below target, so priority order decides: pdx-west first
    nxt = pick_next(report)
    assert nxt is not None and nxt.region.slug == "pdx-west"
