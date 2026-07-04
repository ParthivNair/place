"""GET /feed — Surface 1, the temporal "This Weekend" feed.

One indexed read: good_now join places with ST_DWithin, ordered by
now_score (docs/01 section 7 Q2). Conditions are NEVER computed here; the
route only renders what the evaluator materialized. Every returned card
logs a feed_events 'impression' with its conditions snapshot
(docs/02 section 5 requirement 2).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import insert, text

from place.api import cards as cards_mod
from place.api import snapshots
from place.api.deps import Db, MaybeUser
from place.api.reasons import iter_leaves, render_reason
from place.api.schemas import (
    ASSUMPTION_OF_RISK,
    FeedCard,
    FeedResponse,
    VerdictControl,
)
from place.models import feed_events

router = APIRouter(tags=["feed"])


def _live_unavailable(
    window_rows: list[dict], metas: dict[str, dict]
) -> list[str]:
    """docs/04 §4 rule 2: label the card's non-gate live windows whose state
    is currently unknown (feed down/stale), so 'no live reason' is explicitly
    'live feed unavailable' rather than ambiguous silence. (Unknown *gate*
    windows never reach the feed — the good_now kill switch removes the row.)
    """
    out: list[str] = []
    for w in window_rows:
        if w["is_gate"] or w["state"] is not None:
            continue
        feed_ids = [
            str(leaf["feed"])
            for leaf in iter_leaves(w.get("predicate") or {})
            if leaf.get("feed")
        ]
        if not feed_ids:
            continue
        labels = []
        for fid in dict.fromkeys(feed_ids):
            meta = metas.get(fid) or {}
            provider = meta.get("provider") or fid.split(":", 1)[0]
            parameter = meta.get("parameter") or fid.rsplit(":", 1)[-1]
            labels.append(f"{provider} {parameter}")
        out.append(f"{', '.join(labels)} ({w['wtype']})")
    return out

_FEED_SQL = """
SELECT gn.affordance_id, gn.now_score, gn.reasons, gn.computed_at,
       a.place_id, a.activity_id, a.difficulty,
       EXTRACT(epoch FROM a.typical_duration) / 60 AS typical_duration_min,
       a.dog_ok, a.kid_ok,
       act.display_name AS activity_name, act.hazard_class,
       p.name AS place_name, p.kind AS place_kind,
       ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng,
       ST_Distance(
           p.geom::geography,
           ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
       ) / 1000 AS distance_km
FROM good_now gn
JOIN affordances a ON a.id = gn.affordance_id
JOIN places p ON p.id = a.place_id
JOIN activities act ON act.id = a.activity_id
WHERE a.status = 'published'
  AND NOT p.sensitive
  AND ST_DWithin(
      p.geom::geography,
      ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
      :radius_m)
{extra}
ORDER BY gn.now_score DESC
LIMIT :limit
"""


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    db: Db,
    user: MaybeUser,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=300)] = 130,  # ~90-min polygon at MVP
    activity: Annotated[str | None, Query()] = None,
    dog_ok: Annotated[bool | None, Query()] = None,
    kid_ok: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedResponse:
    now = dt.datetime.now(dt.UTC)
    extra = []
    params: dict[str, object] = {
        "lat": lat,
        "lng": lng,
        "radius_m": radius_km * 1000,
        "limit": limit,
    }
    if activity is not None:
        extra.append("AND a.activity_id = :activity")
        params["activity"] = activity
    if dog_ok:
        extra.append("AND a.dog_ok")
    if kid_ok:
        extra.append("AND a.kid_ok")

    rows = (
        await db.execute(text(_FEED_SQL.format(extra="\n".join(extra))), params)
    ).mappings().all()
    if not rows:
        return FeedResponse(generated_at=now, count=0, cards=[])

    aff_ids = [row["affordance_id"] for row in rows]
    states = await snapshots.window_states(db, aff_ids)
    all_window_rows = [w for ws in states.values() for w in ws]
    metas = await snapshots.feeds_meta(db, snapshots.collect_feed_ids(all_window_rows))
    claims_by_aff = await cards_mod.load_claims(db, aff_ids, now)
    confirms = await cards_mod.load_last_confirm(db, aff_ids)

    out_cards: list[FeedCard] = []
    impressions: list[dict[str, object]] = []
    for row in rows:
        aff_id = row["affordance_id"]
        window_rows = states.get(aff_id, [])
        windows_by_id = {str(w["window_id"]): w for w in window_rows}

        reasons = []
        for reason_ref in row["reasons"] or []:
            wrow = windows_by_id.get(str(reason_ref.get("window_id", "")))
            if wrow is not None:
                reasons.append(
                    render_reason(
                        window_id=wrow["window_id"],
                        wtype=wrow["wtype"],
                        predicate=wrow["predicate"],
                        inputs=wrow["inputs"],
                        feeds_meta=metas,
                        evaluated_at=wrow["evaluated_at"] or wrow["last_eval"],
                        now=now,
                    )
                )
            else:  # window deleted since materialization: degrade honestly
                reasons.append(
                    render_reason(
                        window_id=None,
                        wtype=str(reason_ref.get("wtype", "seasonal")),
                        predicate=None,
                        inputs=None,
                        feeds_meta=metas,
                        evaluated_at=row["computed_at"],
                        now=now,
                    )
                )

        conditions = snapshots.merge_inputs(window_rows)
        claims = claims_by_aff.get(aff_id, [])
        confirm = confirms.get(aff_id)
        card = FeedCard(
            affordance_id=aff_id,
            place_id=row["place_id"],
            place_name=row["place_name"],
            place_kind=row["place_kind"],
            lat=row["lat"],
            lng=row["lng"],
            distance_km=round(float(row["distance_km"]), 1),
            activity_id=row["activity_id"],
            activity_name=row["activity_name"],
            hazard_class=row["hazard_class"],
            difficulty=row["difficulty"],
            typical_duration_min=row["typical_duration_min"],
            dog_ok=row["dog_ok"],
            kid_ok=row["kid_ok"],
            now_score=float(row["now_score"]),
            computed_at=row["computed_at"],
            reasons=reasons,
            live_unavailable=_live_unavailable(window_rows, metas),
            conditions=conditions,
            last_verified_at=confirm["verified_at"] if confirm else None,
            verified_by=confirm["display_name"] if confirm else None,
            assumption_of_risk=ASSUMPTION_OF_RISK if row["hazard_class"] else None,
            verdict_controls=[VerdictControl(claim_id=c["id"]) for c in claims],
        )
        out_cards.append(card)
        impressions.append(
            {
                "user_id": user["id"] if user else None,
                "affordance_id": aff_id,
                "etype": "impression",
                "now_score": float(row["now_score"]),
                "conditions_snapshot": conditions,
            }
        )

    if impressions:
        await db.execute(insert(feed_events), impressions)

    return FeedResponse(generated_at=now, count=len(out_cards), cards=out_cards)
