"""POST /trips — the "I'm going" tap (Surface 4 entry point).

Creates trip intent that the Sunday push resolves, and logs a feed_events
'going' row with the conditions snapshot the recommendation was served
under — the legal record and the calibration label (docs/02 section 5).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, text

from place.api import snapshots
from place.api.deps import CurrentUser, Db
from place.api.schemas import TripIn, TripOut
from place.models import feed_events, trips

router = APIRouter(tags=["trips"])


@router.post("/trips", status_code=201, response_model=TripOut)
async def create_trip(body: TripIn, db: Db, user: CurrentUser) -> TripOut:
    exists = (
        await db.execute(
            text("SELECT 1 FROM affordances WHERE id = :aid"),
            {"aid": body.affordance_id},
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="affordance not found")

    row = (
        await db.execute(
            insert(trips)
            .values(
                user_id=user["id"],
                affordance_id=body.affordance_id,
                planned_date=body.planned_date,
            )
            .returning(trips.c.id, trips.c.declared_at)
        )
    ).mappings().first()

    now_score = (
        await db.execute(
            text("SELECT now_score FROM good_now WHERE affordance_id = :aid"),
            {"aid": body.affordance_id},
        )
    ).scalar()
    snapshot = await snapshots.snapshot_for_affordance(db, body.affordance_id)
    await db.execute(
        insert(feed_events).values(
            user_id=user["id"],
            affordance_id=body.affordance_id,
            etype="going",
            now_score=now_score,
            conditions_snapshot=snapshot,
        )
    )
    return TripOut(
        id=row["id"],
        affordance_id=body.affordance_id,
        planned_date=body.planned_date,
        declared_at=row["declared_at"],
    )
