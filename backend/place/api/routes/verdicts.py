"""POST /verdicts — the one-tap claim verdict (Surface 4).

The server auto-attaches the conditions snapshot from condition_states at
trip time — the user is never asked to describe the weather. A verdict is
a Bayesian log-odds update on the claim (docs/01 section 5): confirm
+1.50, refute -2.08 (power verifier x1.25); confirm resets the decay
clock; 'changed' supersedes the claim and spawns a user_reported one.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, text, update

from place.api import snapshots
from place.api.confidence import (
    USER_REPORTED_PRIOR_L,
    effective_confidence,
    verdict_delta,
)
from place.api.deps import CurrentUser, Db
from place.api.schemas import VerdictIn, VerdictOut
from place.models import claims, verifications

router = APIRouter(tags=["verdicts"])

# Trip dates are local calendar dates in the launch metro (same constant
# place/dsl.py uses); "end of the planned day" must be local midnight, not
# UTC midnight (= 5 pm PDT), or evening readings drop out of the snapshot.
_LOCAL_TZ = ZoneInfo("America/Los_Angeles")

# Rate/idempotency guard: one verdict per (user, claim) per trip, and at most
# one per 24 h without a distinct trip — a single account cannot loop
# confirm/refute to pump or crater a claim's log-odds.
_DUPLICATE_VERDICT_SQL = text(
    """
    SELECT 1 FROM verifications
    WHERE user_id = :uid AND claim_id = :cid
      AND ( (CAST(:tid AS uuid) IS NOT NULL AND trip_id = CAST(:tid AS uuid))
            OR verified_at > :cutoff )
    LIMIT 1
    """
)

_CLAIM_SQL = text(
    """
    SELECT c.id, c.affordance_id, c.cclass::text AS cclass, c.status::text AS status,
           c.log_odds, c.last_evidence_at
    FROM claims c
    WHERE c.id = :cid
    """
)

_TRIP_SQL = text(
    """
    SELECT id, user_id, affordance_id, planned_date
    FROM trips WHERE id = :tid
    """
)

_LATEST_TRIP_SQL = text(
    """
    SELECT id, planned_date
    FROM trips
    WHERE user_id = :uid AND affordance_id = :aid
    ORDER BY declared_at DESC
    LIMIT 1
    """
)


@router.post("/verdicts", status_code=201, response_model=VerdictOut)
async def post_verdict(body: VerdictIn, db: Db, user: CurrentUser) -> VerdictOut:
    now = dt.datetime.now(dt.UTC)
    claim = (await db.execute(_CLAIM_SQL, {"cid": body.claim_id})).mappings().first()
    if claim is None or claim["status"] == "suppressed":
        raise HTTPException(status_code=404, detail="claim not found")
    if claim["status"] != "published":
        # draft/review claims are never rendered, so no legitimate one-tap
        # verdict can reference them; accepting a verdict here would let an
        # unprivileged user pre-seed a hazard-gate confirm before publication.
        raise HTTPException(
            status_code=409, detail="claim is not published; verdicts apply to served claims"
        )

    # Resolve the trip: explicit trip_id must belong to the caller (object
    # ownership); otherwise fall back to the caller's latest trip for the
    # claim's affordance.
    trip: dict[str, Any] | None = None
    if body.trip_id is not None:
        trip_row = (await db.execute(_TRIP_SQL, {"tid": body.trip_id})).mappings().first()
        if trip_row is None or trip_row["user_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="trip not found")
        if trip_row["affordance_id"] != claim["affordance_id"]:
            raise HTTPException(
                status_code=422, detail="trip is for a different affordance"
            )
        trip = dict(trip_row)
    else:
        trip_row = (
            await db.execute(
                _LATEST_TRIP_SQL,
                {"uid": user["id"], "aid": claim["affordance_id"]},
            )
        ).mappings().first()
        trip = dict(trip_row) if trip_row else None

    duplicate = (
        await db.execute(
            _DUPLICATE_VERDICT_SQL,
            {
                "uid": user["id"],
                "cid": body.claim_id,
                "tid": trip["id"] if trip else None,
                "cutoff": now - dt.timedelta(hours=24),
            },
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="verdict already recorded for this claim (one per trip / 24 h)",
        )

    # Snapshot conditions as of trip time (end of the planned day in the
    # launch metro's timezone), never asking the user; no trip -> as of now.
    at: dt.datetime | None = None
    if trip is not None:
        at = dt.datetime.combine(
            trip["planned_date"], dt.time(23, 59, 59), tzinfo=_LOCAL_TZ
        ).astimezone(dt.UTC)
        if at > now:
            at = now
    snapshot = await snapshots.snapshot_for_affordance(
        db, claim["affordance_id"], at=at
    )

    verification_id = (
        await db.execute(
            insert(verifications)
            .values(
                claim_id=body.claim_id,
                user_id=user["id"],
                trip_id=trip["id"] if trip else None,
                verdict=body.verdict,
                conditions_snapshot=snapshot,
            )
            .returning(verifications.c.id)
        )
    ).scalar()

    log_odds = float(claim["log_odds"])
    last_evidence_at = claim["last_evidence_at"]
    superseding_claim_id: uuid.UUID | None = None

    if body.verdict == "changed":
        # supersede: spawn a user_reported claim at its source-type prior
        superseding_claim_id = (
            await db.execute(
                insert(claims)
                .values(
                    affordance_id=claim["affordance_id"],
                    cclass=claim["cclass"],
                    stype="user_reported",
                    observed_date=(trip["planned_date"] if trip else now.date()),
                    log_odds=USER_REPORTED_PRIOR_L,
                    status="review",
                    last_evidence_at=now,
                )
                .returning(claims.c.id)
            )
        ).scalar()
        await db.execute(
            update(claims)
            .where(claims.c.id == body.claim_id)
            .values(superseded_by=superseding_claim_id)
        )
    else:
        delta = verdict_delta(body.verdict, bool(user.get("power_verifier")))
        # Atomic read-modify-write in SQL: concurrent verdicts each add their
        # delta instead of the last writer silently discarding the others.
        values: dict[str, Any] = {"log_odds": claims.c.log_odds + delta}
        if body.verdict == "confirm":
            # confirming evidence resets the decay clock (docs/01 section 5)
            values["last_evidence_at"] = now
            last_evidence_at = now
        log_odds = float(
            (
                await db.execute(
                    update(claims)
                    .where(claims.c.id == body.claim_id)
                    .values(**values)
                    .returning(claims.c.log_odds)
                )
            ).scalar_one()
        )

    return VerdictOut(
        verification_id=verification_id,
        claim_id=body.claim_id,
        verdict=body.verdict,
        log_odds=round(log_odds, 4),
        confidence=round(
            effective_confidence(log_odds, claim["cclass"], last_evidence_at, now), 4
        ),
        conditions_snapshot=snapshot,
        superseding_claim_id=superseding_claim_id,
    )
