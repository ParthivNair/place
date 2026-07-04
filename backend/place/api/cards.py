"""Shared claim/verification loaders for card-rendering routes (feed, places)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from place import scoring
from place.api.confidence import effective_confidence

# Published, non-superseded claims only serve (docs/01 section 4 gate 1).
# quote_internal is deliberately not selected — it never leaves the DB.
_CLAIMS_SQL = text(
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

_LAST_CONFIRM_SQL = text(
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
        await db.execute(_CLAIMS_SQL, {"ids": list(affordance_ids)})
    ).mappings().all()
    # Corroboration boost (docs/01 section 5): +0.5 nats per *other*
    # independent published source_domain on the same affordance, capped
    # +1.5 — same read-time math the good_now materialization uses.
    domains: dict[uuid.UUID, set[str]] = {}
    for row in rows:
        if row["source_domain"] is not None:
            domains.setdefault(row["affordance_id"], set()).add(row["source_domain"])
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        others = domains.get(row["affordance_id"], set()) - {row["source_domain"]}
        boosted = float(row["log_odds"]) + scoring.corroboration_boost(len(others))
        out.setdefault(row["affordance_id"], []).append(
            {
                "id": row["id"],
                "affordance_id": row["affordance_id"],
                "cclass": row["cclass"],
                "source_type": row["stype"],
                "source_domain": row["source_domain"],
                "source_url": row["source_url"],
                "observed_date": row["observed_date"],
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


async def load_last_confirm(
    db: AsyncConnection, affordance_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Most recent confirming verification (timestamp + verifier credit)."""
    if not affordance_ids:
        return {}
    rows = (
        await db.execute(_LAST_CONFIRM_SQL, {"ids": list(affordance_ids)})
    ).mappings().all()
    return {row["affordance_id"]: dict(row) for row in rows}
