"""Shared claim/verification loaders for card-rendering routes (feed, places)
and the pack compiler (evaluator/publish.py).

CLAIMS_SQL + project_claims are the single publication gate for claims on
every read path: the API routes execute them async, the pack compiler
executes the same statement sync. There is deliberately no second SQL — a
claim that is unpublished or superseded, and the quote_internal column, are
structurally unreachable from both the JSON API and the static artifacts.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from place import scoring
from place.api.confidence import effective_confidence

# Published, non-superseded claims only serve (docs/01 section 4 gate 1).
# quote_internal is deliberately not selected — it never leaves the DB.
CLAIMS_SQL = text(
    """
    SELECT c.id, c.affordance_id, c.cclass::text AS cclass, c.stype::text AS stype,
           c.source_domain, c.source_url, c.observed_date,
           c.log_odds, c.last_evidence_at
    FROM claims c
    WHERE c.affordance_id IN :ids
      AND c.status = 'published'
      AND c.superseded_by IS NULL
    ORDER BY c.log_odds DESC
    """
).bindparams(bindparam("ids", expanding=True))

LAST_CONFIRM_SQL = text(
    """
    SELECT DISTINCT ON (c.affordance_id)
           c.affordance_id, v.verified_at, u.display_name
    FROM verifications v
    JOIN claims c ON c.id = v.claim_id
    JOIN users u ON u.id = v.user_id
    WHERE c.affordance_id IN :ids AND v.verdict = 'confirm'
    ORDER BY c.affordance_id, v.verified_at DESC
    """
).bindparams(bindparam("ids", expanding=True))


def project_claims(
    rows: Sequence[Mapping[str, Any]], now: dt.datetime
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Pure projection over CLAIMS_SQL rows, per affordance.

    Corroboration boost (docs/01 section 5): +0.5 nats per *other*
    independent published source_domain on the same affordance, capped
    +1.5 — same read-time math the good_now materialization uses. Emits
    both the derived `confidence` (what the API renders) and the raw
    `log_odds` + `corroboration_nats` (what the pack ships so an offline
    client re-derives confidence at view time from the same constants).
    """
    domains: dict[uuid.UUID, set[str]] = {}
    for row in rows:
        if row["source_domain"] is not None:
            domains.setdefault(row["affordance_id"], set()).add(row["source_domain"])
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        others = domains.get(row["affordance_id"], set()) - {row["source_domain"]}
        boost = scoring.corroboration_boost(len(others))
        boosted = float(row["log_odds"]) + boost
        out.setdefault(row["affordance_id"], []).append(
            {
                "id": row["id"],
                "affordance_id": row["affordance_id"],
                "cclass": row["cclass"],
                "source_type": row["stype"],
                "source_domain": row["source_domain"],
                "source_url": row["source_url"],
                "observed_date": row["observed_date"],
                "log_odds": float(row["log_odds"]),
                "corroboration_nats": boost,
                "confidence": round(
                    effective_confidence(
                        boosted, row["cclass"], row["last_evidence_at"], now
                    ),
                    4,
                ),
                "last_evidence_at": row["last_evidence_at"],
            }
        )
    return out


async def load_claims(
    db: AsyncConnection,
    affordance_ids: list[uuid.UUID],
    now: dt.datetime | None = None,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Published claims per affordance, with decayed effective confidence."""
    if not affordance_ids:
        return {}
    now = now or dt.datetime.now(dt.UTC)
    rows = (
        await db.execute(CLAIMS_SQL, {"ids": list(affordance_ids)})
    ).mappings().all()
    return project_claims(rows, now)


async def load_last_confirm(
    db: AsyncConnection, affordance_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Most recent confirming verification (timestamp + verifier credit)."""
    if not affordance_ids:
        return {}
    rows = (
        await db.execute(LAST_CONFIRM_SQL, {"ids": list(affordance_ids)})
    ).mappings().all()
    return {row["affordance_id"]: dict(row) for row in rows}
