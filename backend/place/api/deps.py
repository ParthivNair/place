"""FastAPI dependencies: DB connection and the auth chain.

Auth policy (build brief): /feed and /places/* are public (optional user),
saves/trips/verdicts/events/push require a session, /admin/* requires the
founder. Object ownership is enforced in routes by scoping every write to
the session user's id.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from place.api import security
from place.models import users


async def get_db(request: Request) -> AsyncIterator[AsyncConnection]:
    """One connection + transaction per request; commit on success."""
    engine = request.app.state.engine
    async with engine.begin() as conn:
        yield conn


Db = Annotated[AsyncConnection, Depends(get_db)]


async def get_current_user(request: Request, db: Db) -> dict[str, Any] | None:
    token = request.cookies.get(security.SESSION_COOKIE)
    if not token:
        return None
    user_id: uuid.UUID | None = security.verify_session_token(
        token, security.get_api_settings()
    )
    if user_id is None:
        return None
    row = (
        await db.execute(select(users).where(users.c.id == user_id))
    ).mappings().first()
    return dict(row) if row else None


MaybeUser = Annotated[dict[str, Any] | None, Depends(get_current_user)]


async def require_user(user: MaybeUser) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(require_user)]


async def require_founder(user: CurrentUser) -> dict[str, Any]:
    if not security.is_founder(user["email"], security.get_api_settings()):
        raise HTTPException(status_code=403, detail="founder only")
    return user


Founder = Annotated[dict[str, Any], Depends(require_founder)]
