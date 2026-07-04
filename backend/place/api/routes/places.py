"""Surface 2 — /places/search, /places/{id}, /affordances/{id}/claims.

The place page is a rendering of the graph: published affordances, current
condition window states with the live sensor value behind each, and every
published claim's provenance + decayed confidence + one-tap verdict
controls. Hazard-class affordances render only when the serving gates pass
(docs/01 section 4 rule 3): a confirm within the class half-life AND every
is_gate window currently true.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from place.api import cards as cards_mod
from place.api import snapshots
from place.api.confidence import HAZARD_CONFIRM_WINDOW_DAYS
from place.api.deps import Db
from place.api.reasons import render_reason
from place.api.schemas import (
    ASSUMPTION_OF_RISK,
    AffordanceDetail,
    ClaimOut,
    PlacePage,
    PlaceSearchResult,
    ReasonOut,
    WindowOut,
)

router = APIRouter(tags=["places"])

_SEARCH_SQL = """
SELECT p.id, p.name, p.kind, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng,
       ST_Distance(
           p.geom::geography,
           ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
       ) / 1000 AS distance_km,
       COALESCE(
           array_agg(DISTINCT a.activity_id) FILTER (WHERE a.id IS NOT NULL),
           '{{}}'
       ) AS activities
FROM places p
LEFT JOIN affordances a ON a.place_id = p.id AND a.status = 'published'
WHERE NOT p.sensitive
  AND ST_DWithin(
      p.geom::geography,
      ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
      :radius_m)
{extra}
GROUP BY p.id
ORDER BY distance_km
LIMIT :limit
"""

_PLACE_SQL = text(
    """
    SELECT id, name, kind, elev_m, sensitive,
           ST_Y(geom) AS lat, ST_X(geom) AS lng
    FROM places WHERE id = :pid
    """
)

_AFFORDANCES_SQL = text(
    """
    SELECT a.id AS affordance_id, a.activity_id, a.difficulty,
           EXTRACT(epoch FROM a.typical_duration) / 60 AS typical_duration_min,
           a.dog_ok, a.kid_ok,
           act.display_name AS activity_name, act.hazard_class
    FROM affordances a
    JOIN activities act ON act.id = a.activity_id
    WHERE a.place_id = :pid AND a.status = 'published'
    ORDER BY act.display_name
    """
)


@router.get("/places/search", response_model=list[PlaceSearchResult])
async def search_places(
    db: Db,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=300)] = 130,
    activity: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[PlaceSearchResult]:
    extra = []
    params: dict[str, object] = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_km * 1000,
        "limit": limit,
    }
    if q is not None:
        extra.append("AND p.name ILIKE :q")
        params["q"] = f"%{q}%"
    if activity is not None:
        extra.append(
            "AND EXISTS (SELECT 1 FROM affordances af WHERE af.place_id = p.id"
            " AND af.status = 'published' AND af.activity_id = :activity)"
        )
        params["activity"] = activity

    rows = (
        await db.execute(text(_SEARCH_SQL.format(extra="\n".join(extra))), params)
    ).mappings().all()
    return [
        PlaceSearchResult(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            lat=row["lat"],
            lng=row["lng"],
            distance_km=round(float(row["distance_km"]), 1),
            activities=sorted(row["activities"] or []),
        )
        for row in rows
    ]


def _window_out(
    wrow: dict[str, Any], metas: dict[str, dict[str, Any]], now: dt.datetime
) -> WindowOut:
    live: ReasonOut | None = None
    if wrow["inputs"] is not None:
        live = ReasonOut(
            **render_reason(
                window_id=wrow["window_id"],
                wtype=wrow["wtype"],
                predicate=wrow["predicate"],
                inputs=wrow["inputs"],
                feeds_meta=metas,
                evaluated_at=wrow["evaluated_at"] or wrow["last_eval"],
                now=now,
            )
        )
    state = "unknown" if wrow["state"] is None else ("true" if wrow["state"] else "false")
    return WindowOut(
        window_id=wrow["window_id"],
        wtype=wrow["wtype"],
        is_gate=wrow["is_gate"],
        multiplier=float(wrow["multiplier"]),
        state=state,
        state_since=wrow["state_since"],
        last_eval=wrow["last_eval"],
        live=live,
    )


@router.get("/places/{place_id}", response_model=PlacePage)
async def get_place(place_id: uuid.UUID, db: Db) -> PlacePage:
    now = dt.datetime.now(dt.UTC)
    place = (await db.execute(_PLACE_SQL, {"pid": place_id})).mappings().first()
    if place is None or place["sensitive"]:
        # sensitive places are hard-excluded from all serving (docs/01 section 4)
        raise HTTPException(status_code=404, detail="place not found")

    aff_rows = (
        await db.execute(_AFFORDANCES_SQL, {"pid": place_id})
    ).mappings().all()
    aff_ids = [row["affordance_id"] for row in aff_rows]
    states = await snapshots.window_states(db, aff_ids)
    all_window_rows = [w for ws in states.values() for w in ws]
    metas = await snapshots.feeds_meta(db, snapshots.collect_feed_ids(all_window_rows))
    claims_by_aff = await cards_mod.load_claims(db, aff_ids, now)
    confirms = await cards_mod.load_last_confirm(db, aff_ids)

    details: list[AffordanceDetail] = []
    for row in aff_rows:
        aff_id = row["affordance_id"]
        window_rows = states.get(aff_id, [])
        confirm = confirms.get(aff_id)

        if row["hazard_class"]:
            # hazard serving gate: recent confirm AND every is_gate window true
            recent_confirm = confirm is not None and confirm["verified_at"] > (
                now - dt.timedelta(days=HAZARD_CONFIRM_WINDOW_DAYS)
            )
            gates_ok = all(
                w["state"] is True for w in window_rows if w["is_gate"]
            )
            if not (recent_confirm and gates_ok):
                continue

        details.append(
            AffordanceDetail(
                affordance_id=aff_id,
                activity_id=row["activity_id"],
                activity_name=row["activity_name"],
                hazard_class=row["hazard_class"],
                difficulty=row["difficulty"],
                typical_duration_min=row["typical_duration_min"],
                dog_ok=row["dog_ok"],
                kid_ok=row["kid_ok"],
                windows=[_window_out(w, metas, now) for w in window_rows],
                claims=[ClaimOut(**c) for c in claims_by_aff.get(aff_id, [])],
                last_verified_at=confirm["verified_at"] if confirm else None,
                verified_by=confirm["display_name"] if confirm else None,
                assumption_of_risk=ASSUMPTION_OF_RISK if row["hazard_class"] else None,
            )
        )

    return PlacePage(
        id=place["id"],
        name=place["name"],
        kind=place["kind"],
        lat=place["lat"],
        lng=place["lng"],
        elev_m=place["elev_m"],
        affordances=details,
    )


@router.get("/affordances/{affordance_id}/claims", response_model=list[ClaimOut])
async def get_affordance_claims(affordance_id: uuid.UUID, db: Db) -> list[ClaimOut]:
    exists = (
        await db.execute(
            text("SELECT 1 FROM affordances WHERE id = :aid"), {"aid": affordance_id}
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="affordance not found")
    claims_by_aff = await cards_mod.load_claims(db, [affordance_id])
    return [ClaimOut(**c) for c in claims_by_aff.get(affordance_id, [])]
