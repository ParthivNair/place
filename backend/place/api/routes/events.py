"""POST /events — shown/saved/went/verified telemetry into feed_events.

The ranking exhaust from user #1 (docs/04 section 5). Product verbs map to
the feed_event_t enum in schemas.EVENT_ALIASES; the conditions snapshot is
auto-attached from the affordance's latest condition states when the
client doesn't supply one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, text

from place.api import snapshots
from place.api.deps import CurrentUser, Db
from place.api.schemas import EventIn, EventOut
from place.models import feed_events

router = APIRouter(tags=["events"])


@router.post("/events", status_code=201, response_model=EventOut)
async def post_event(body: EventIn, db: Db, user: CurrentUser) -> EventOut:
    exists = (
        await db.execute(
            text("SELECT 1 FROM affordances WHERE id = :aid"),
            {"aid": body.affordance_id},
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="affordance not found")

    snapshot = body.conditions_snapshot
    if snapshot is None:
        snapshot = await snapshots.snapshot_for_affordance(db, body.affordance_id)

    event_id = (
        await db.execute(
            insert(feed_events)
            .values(
                user_id=user["id"],
                affordance_id=body.affordance_id,
                etype=body.etype,  # already alias-mapped by the schema validator
                now_score=body.now_score,
                conditions_snapshot=snapshot,
            )
            .returning(feed_events.c.id)
        )
    ).scalar()
    return EventOut(id=event_id, etype=body.etype, affordance_id=body.affordance_id)
