"""POST /events — shown/saved/went/verified telemetry into feed_events.

The ranking exhaust from user #1 (docs/04 section 5). Product verbs map to
the feed_event_t enum in schemas.EVENT_ALIASES; the conditions snapshot is
auto-attached from the affordance's latest condition states when the
client doesn't supply one.

POST /events/impressions is the feed's impression beacon: GET /feed is a
pure read (static-pack read path), so the client reports what it rendered
and the server re-attaches each snapshot as of the card's computed_at —
the impression log (docs/02 section 5 requirement 2: legal record + moat
M4 training data) stays server-attested, never client-supplied.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import bindparam, insert, text

from place.api import snapshots
from place.api.deps import CurrentUser, Db, MaybeUser
from place.api.schemas import EventIn, EventOut, ImpressionsIn, ImpressionsOut
from place.models import feed_events

router = APIRouter(tags=["events"])

_AFFORDANCES_EXIST_SQL = text(
    "SELECT id FROM affordances WHERE id IN :ids"
).bindparams(bindparam("ids", expanding=True))


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


@router.post("/events/impressions", status_code=201, response_model=ImpressionsOut)
async def post_impressions(
    body: ImpressionsIn, db: Db, user: MaybeUser
) -> ImpressionsOut:
    # MaybeUser, not CurrentUser: the feed is public and its impressions
    # logged user_id=None for signed-out sessions when GET /feed wrote them
    # itself — anonymity stays legal here even though single events above
    # keep requiring a session.
    ids = sorted({item.affordance_id for item in body.items})
    known = {
        row[0] for row in await db.execute(_AFFORDANCES_EXIST_SQL, {"ids": ids})
    }
    if unknown := [str(i) for i in ids if i not in known]:
        raise HTTPException(
            status_code=404,
            detail=f"unknown affordance ids: {', '.join(unknown)}",
        )

    # One good_now sweep stamps every card it serves with the same
    # computed_at, so a feed response's whole batch normally reconstructs
    # from a single as-of read.
    by_at: dict[dt.datetime, list[uuid.UUID]] = {}
    for item in body.items:
        by_at.setdefault(item.computed_at, []).append(item.affordance_id)
    snapshot_at: dict[tuple[dt.datetime, uuid.UUID], dict[str, Any]] = {}
    for at, aff_ids in by_at.items():
        reconstructed = await snapshots.snapshots_for_affordances(db, aff_ids, at=at)
        for aff_id, snapshot in reconstructed.items():
            snapshot_at[(at, aff_id)] = snapshot

    await db.execute(
        insert(feed_events),
        [
            {
                "user_id": user["id"] if user else None,
                "affordance_id": item.affordance_id,
                "etype": "impression",
                "now_score": item.now_score,
                "conditions_snapshot": snapshot_at[(item.computed_at, item.affordance_id)],
            }
            for item in body.items
        ],
    )
    return ImpressionsOut(stored=len(body.items))
