"""Founder-verified demo seeding (integration phase, docs/01 §4).

Nothing auto-publishes: the bindings loader leaves affordances 'draft' and
creates no claims. This step is the founder acting — it inserts one
founder_verified published claim per NON-hazard draft affordance created by
the launch bindings, then flips the affordance to 'published' (the DB
publication-gate trigger checks the support). Hazard affordances (wild-swim)
are deliberately untouched: the hazard serving gate requires a real founder
verification event, and weakening it for the demo is forbidden by the brief.

Decision (docs silent): the seeded claim's class is 'geomorphic' — the claim
being vouched for is the structural one ("this affordance exists and is
good"), which carries the long half-life; condition windows carry the
time-varying part.

Idempotent: an affordance with an existing founder_verified claim is skipped.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from place.scoring import prior_log_odds

log = logging.getLogger("place.ingest.seed_demo")

FOUNDER_SOURCE_DOMAIN = "founder.place"


def load(conn: Connection) -> dict[str, int]:
    """Seed founder_verified claims and publish non-hazard draft affordances."""
    rows = conn.execute(
        text(
            """
            SELECT a.id
            FROM affordances a
            JOIN activities act ON act.id = a.activity_id
            WHERE a.status = 'draft'
              AND NOT act.hazard_class
              AND NOT EXISTS (
                  SELECT 1 FROM claims c
                  WHERE c.affordance_id = a.id AND c.stype = 'founder_verified'
              )
            """
        )
    ).fetchall()

    claims_created = 0
    published = 0
    log_odds = prior_log_odds("founder_verified")  # logit(0.95) ~= +2.94
    for (aff_id,) in rows:
        conn.execute(
            text(
                "INSERT INTO claims (affordance_id, cclass, stype, source_domain, "
                "status, log_odds, observed_date) "
                "VALUES (:aid, 'geomorphic', 'founder_verified', :dom, 'published', "
                ":lo, CURRENT_DATE)"
            ),
            {"aid": aff_id, "dom": FOUNDER_SOURCE_DOMAIN, "lo": log_odds},
        )
        claims_created += 1
        conn.execute(
            text("UPDATE affordances SET status = 'published' WHERE id = :aid"),
            {"aid": aff_id},
        )
        published += 1
    log.info("seed_demo: %d founder claims, %d affordances published", claims_created, published)
    return {"claims_created": claims_created, "affordances_published": published}
