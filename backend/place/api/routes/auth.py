"""Magic-link auth (docs/04 section 7). No passwords.

POST /auth/magic-link creates a signed 15-minute token and emails it via
Resend when RESEND_API_KEY is set; in dev (no key) the link is logged at
INFO. POST /auth/verify exchanges the token for a long-lived httpOnly
session cookie and upserts the user row.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.dialects.postgresql import insert as pg_insert

from place.api import security
from place.api.deps import CurrentUser, Db
from place.api.schemas import MagicLinkIn, UserOut, VerifyIn
from place.models import users

logger = logging.getLogger("place.api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

_RESEND_URL = "https://api.resend.com/emails"


def _verify_base_url(settings: security.ApiSettings) -> str:
    # The PWA hosts the verify screen; first CORS origin is the frontend.
    origin = settings.cors_origins.split(",")[0].strip() or "http://localhost:3000"
    return f"{origin.rstrip('/')}/auth/verify"


async def _send_email(settings: security.ApiSettings, email: str, link: str) -> None:
    payload = {
        "from": settings.magic_link_from,
        "to": [email],
        "subject": "Your Place sign-in link",
        "html": (
            f'<p><a href="{link}">Sign in to Place</a> — this link is valid for '
            f"{settings.magic_link_max_age_s // 60} minutes.</p>"
        ),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            _RESEND_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )
    if resp.status_code >= 400:
        logger.error("resend send failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="email delivery failed")


@router.post("/magic-link", status_code=202)
async def request_magic_link(body: MagicLinkIn) -> dict[str, bool]:
    settings = security.get_api_settings()
    token = security.create_magic_token(body.email, settings)
    link = f"{_verify_base_url(settings)}?token={token}"
    if settings.resend_api_key:
        await _send_email(settings, body.email, link)
    else:
        # dev mode: RESEND_API_KEY absent -> the link IS the delivery channel
        logger.info("magic-link (dev, email not sent) for %s: %s", body.email, link)
    return {"sent": True}


@router.post("/verify", response_model=UserOut)
async def verify_magic_link(body: VerifyIn, response: Response, db: Db) -> UserOut:
    settings = security.get_api_settings()
    email = security.verify_magic_token(body.token, settings)
    if email is None:
        raise HTTPException(status_code=400, detail="invalid or expired token")

    row = (
        await db.execute(
            pg_insert(users)
            .values(email=email)
            .on_conflict_do_update(
                index_elements=[users.c.email], set_={"email": email}
            )
            .returning(
                users.c.id, users.c.email, users.c.display_name, users.c.power_verifier
            )
        )
    ).mappings().first()

    response.set_cookie(
        key=security.SESSION_COOKIE,
        value=security.create_session_token(row["id"], settings),
        max_age=settings.session_max_age_s,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return UserOut(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        power_verifier=row["power_verifier"],
        is_founder=security.is_founder(row["email"], settings),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    settings = security.get_api_settings()
    return UserOut(
        id=user["id"],
        email=user["email"],
        display_name=user.get("display_name"),
        power_verifier=bool(user.get("power_verifier")),
        is_founder=security.is_founder(user["email"], settings),
    )
