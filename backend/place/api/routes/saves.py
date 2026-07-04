"""Surface 3 — saves are standing queries, not bookmarks.

POST/DELETE/GET /saves, always scoped to the session user (ownership is
structural: the user id comes from the cookie, never the body). Every save
logs a feed_events row with the conditions snapshot it happened under
(docs/02 section 5 requirement 2). Alert matching runs in the evaluator.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import delete, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from place.api import snapshots
from place.api.deps import CurrentUser, Db
from place.api.schemas import SavedItem, SaveIn, SaveKind
from place.models import feed_events, saves

router = APIRouter(tags=["saves"])

_LIST_SQL = text(
    """
    SELECT s.affordance_id, s.kind::text AS kind, s.created_at, s.last_alerted_at,
           a.place_id, a.activity_id, p.name AS place_name
    FROM saves s
    JOIN affordances a ON a.id = s.affordance_id
    JOIN places p ON p.id = a.place_id
    WHERE s.user_id = :uid
    ORDER BY s.created_at DESC
    """
)


async def _affordance_exists(db: Any, affordance_id: uuid.UUID) -> bool:
    row = (
        await db.execute(
            text("SELECT 1 FROM affordances WHERE id = :aid"), {"aid": affordance_id}
        )
    ).first()
    return row is not None


@router.post("/saves", status_code=201)
async def create_save(body: SaveIn, db: Db, user: CurrentUser) -> dict[str, Any]:
    if not await _affordance_exists(db, body.affordance_id):
        raise HTTPException(status_code=404, detail="affordance not found")
    await db.execute(
        pg_insert(saves)
        .values(user_id=user["id"], affordance_id=body.affordance_id, kind=body.kind)
        .on_conflict_do_nothing(
            index_elements=[saves.c.user_id, saves.c.affordance_id, saves.c.kind]
        )
    )
    snapshot = await snapshots.snapshot_for_affordance(db, body.affordance_id)
    await db.execute(
        insert(feed_events).values(
            user_id=user["id"],
            affordance_id=body.affordance_id,
            etype="save",
            conditions_snapshot=snapshot,
        )
    )
    return {"affordance_id": str(body.affordance_id), "kind": body.kind, "saved": True}


@router.delete("/saves", status_code=204)
async def delete_save(
    db: Db,
    user: CurrentUser,
    affordance_id: Annotated[uuid.UUID, Query()],
    kind: Annotated[SaveKind, Query()],
) -> None:
    result = await db.execute(
        delete(saves).where(
            saves.c.user_id == user["id"],
            saves.c.affordance_id == affordance_id,
            saves.c.kind == kind,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="save not found")


@router.get("/saves", response_model=list[SavedItem])
async def list_saves(db: Db, user: CurrentUser) -> list[SavedItem]:
    rows = (await db.execute(_LIST_SQL, {"uid": user["id"]})).mappings().all()
    return [SavedItem(**dict(row)) for row in rows]
