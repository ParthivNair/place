"""POST /push/subscribe — store a Web Push (VAPID) subscription.

Sending (the Sunday 6pm composition) is PR-9, out of scope this round;
storage and the VAPID keygen helper (place.api.vapid_keygen) are in.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert

from place.api import security
from place.api.deps import CurrentUser, Db
from place.api.schemas import PushSubscriptionIn
from place.models import push_subscriptions

router = APIRouter(prefix="/push", tags=["push"])


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: PushSubscriptionIn, db: Db, user: CurrentUser
) -> dict[str, bool]:
    await db.execute(
        pg_insert(push_subscriptions)
        .values(
            user_id=user["id"],
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
        )
        .on_conflict_do_update(
            index_elements=[push_subscriptions.c.endpoint],
            set_={
                "user_id": user["id"],
                "p256dh": body.keys.p256dh,
                "auth": body.keys.auth,
            },
        )
    )
    return {"stored": True}


@router.get("/vapid-public-key")
async def vapid_public_key() -> dict[str, str]:
    """The applicationServerKey the PWA needs to subscribe."""
    settings = security.get_api_settings()
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=404,
            detail="VAPID_PUBLIC_KEY not configured; run python -m place.api.vapid_keygen",
        )
    return {"public_key": settings.vapid_public_key}
