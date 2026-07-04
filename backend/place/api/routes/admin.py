"""Founder review queue — GET/POST /admin/review-queue (docs/04 PR-5).

Approve/reject/edit pending extracted claims. Approving flips the claim to
'published' and then attempts to publish the affordance; the publication
gate is DB-enforced (trigger affordances_publication_gate), so when the
structural gate blocks, the trigger error is caught in a savepoint and
surfaced cleanly — the claim approval itself still commits.

quote_internal is never selected: the founder reviews via source_url.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from place.api.deps import Db, Founder
from place.api.schemas import ReviewActionIn, ReviewActionOut, ReviewQueueItem
from place.models import affordances, claims

router = APIRouter(prefix="/admin", tags=["admin"])

_QUEUE_SQL = text(
    """
    SELECT c.id, c.affordance_id, c.cclass::text AS cclass, c.stype::text AS stype,
           c.source_url, c.source_domain, c.observed_date, c.extractor_ver,
           c.self_conf, c.log_odds, c.created_at,
           p.name AS place_name, a.activity_id
    FROM claims c
    JOIN affordances a ON a.id = c.affordance_id
    JOIN places p ON p.id = a.place_id
    WHERE c.status = 'review'
    ORDER BY c.created_at
    LIMIT :limit OFFSET :offset
    """
)


@router.get("/review-queue", response_model=list[ReviewQueueItem])
async def review_queue(
    db: Db,
    founder: Founder,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReviewQueueItem]:
    rows = (
        await db.execute(_QUEUE_SQL, {"limit": limit, "offset": offset})
    ).mappings().all()
    return [
        ReviewQueueItem(
            id=row["id"],
            affordance_id=row["affordance_id"],
            place_name=row["place_name"],
            activity_id=row["activity_id"],
            cclass=row["cclass"],
            source_type=row["stype"],
            source_url=row["source_url"],
            source_domain=row["source_domain"],
            observed_date=row["observed_date"],
            extractor_ver=row["extractor_ver"],
            self_conf=float(row["self_conf"]) if row["self_conf"] is not None else None,
            log_odds=float(row["log_odds"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post("/review-queue", response_model=ReviewActionOut)
async def review_action(
    body: ReviewActionIn, db: Db, founder: Founder
) -> ReviewActionOut:
    claim = (
        await db.execute(
            text("SELECT id, affordance_id, status::text AS status FROM claims WHERE id = :cid"),
            {"cid": body.claim_id},
        )
    ).mappings().first()
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")

    if body.action == "edit":
        if body.edits is None:
            raise HTTPException(status_code=422, detail="edit requires edits")
        edits = body.edits.model_dump(exclude_none=True)
        if not edits:
            raise HTTPException(status_code=422, detail="no editable fields supplied")
        await db.execute(
            update(claims).where(claims.c.id == body.claim_id).values(**edits)
        )
        return ReviewActionOut(
            claim_id=body.claim_id,
            claim_status=claim["status"],
            affordance_id=claim["affordance_id"],
        )

    new_status = "published" if body.action == "approve" else "suppressed"
    await db.execute(
        update(claims).where(claims.c.id == body.claim_id).values(status=new_status)
    )

    affordance_published = False
    gate_error: str | None = None
    if body.action == "approve" and body.publish_affordance:
        # Attempt the affordance transition in a savepoint so the DB gate
        # (trigger) can block it without rolling back the claim approval.
        savepoint = await db.begin_nested()
        try:
            result = await db.execute(
                update(affordances)
                .where(
                    affordances.c.id == claim["affordance_id"],
                    affordances.c.status != "published",
                )
                .values(status="published")
            )
            await savepoint.commit()
            affordance_published = result.rowcount > 0
        except DBAPIError as exc:
            await savepoint.rollback()
            orig = getattr(exc, "orig", exc)
            gate_error = str(orig).strip() or "publication gate blocked the transition"

    return ReviewActionOut(
        claim_id=body.claim_id,
        claim_status=new_status,
        affordance_id=claim["affordance_id"],
        affordance_published=affordance_published,
        gate_error=gate_error,
    )
