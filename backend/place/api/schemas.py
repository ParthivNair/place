"""Pydantic response/request schemas for every route.

Hard rule (docs/01 section 2): claims.quote_internal is NEVER serialized by
any API — no schema in this module may carry it, including the founder
review queue. Every schema that renders a claim carries the one-tap verdict
affordance data (claim_id + allowed verdicts).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

VerdictLiteral = Literal["confirm", "refute", "changed"]
ALLOWED_VERDICTS: list[VerdictLiteral] = ["confirm", "refute", "changed"]

# docs/02 section 5: hazard cards always ship assumption-of-risk framing.
ASSUMPTION_OF_RISK = (
    "Conditions change; you are responsible for your own judgment. "
    "Verify current conditions on arrival."
)


# --------------------------------------------------------------------------
# shared claim / reason fragments
# --------------------------------------------------------------------------


class VerdictControl(BaseModel):
    claim_id: uuid.UUID
    allowed_verdicts: list[VerdictLiteral] = ALLOWED_VERDICTS


class ProvenanceReading(BaseModel):
    feed_id: str
    provider: str | None = None
    station_ref: str | None = None
    parameter: str | None = None
    unit: str | None = None
    value: Any = None
    observed_at: dt.datetime | None = None


class ReasonOut(BaseModel):
    window_id: uuid.UUID | None = None
    wtype: str
    text: str
    source: str | None = None
    fresh: bool = True
    as_of: dt.datetime | None = None
    evaluated_at: dt.datetime | None = None
    provenance: list[ProvenanceReading] = []


class ClaimOut(BaseModel):
    id: uuid.UUID
    affordance_id: uuid.UUID
    cclass: str
    source_type: str
    source_domain: str | None = None
    source_url: str | None = None
    observed_date: dt.date | None = None
    confidence: float
    last_evidence_at: dt.datetime
    allowed_verdicts: list[VerdictLiteral] = ALLOWED_VERDICTS


class WindowOut(BaseModel):
    window_id: uuid.UUID
    wtype: str
    is_gate: bool
    multiplier: float
    state: Literal["true", "false", "unknown"]
    state_since: dt.datetime | None = None
    last_eval: dt.datetime | None = None
    live: ReasonOut | None = None


# --------------------------------------------------------------------------
# feed
# --------------------------------------------------------------------------


class FeedCard(BaseModel):
    affordance_id: uuid.UUID
    place_id: uuid.UUID
    place_name: str
    place_kind: str
    lat: float
    lng: float
    distance_km: float
    activity_id: str
    activity_name: str
    hazard_class: bool
    difficulty: int | None = None
    typical_duration_min: float | None = None
    dog_ok: bool | None = None
    kid_ok: bool | None = None
    now_score: float
    computed_at: dt.datetime
    reasons: list[ReasonOut]
    # docs/04 §4 rule 2 degradation marker: labels of non-gate live windows
    # currently state=unknown (feed down/stale). The card serves on its
    # remaining windows (seasonal prior); consumers render "live …
    # unavailable" instead of implying "conditions bad".
    live_unavailable: list[str] = []
    conditions: dict[str, Any]
    last_verified_at: dt.datetime | None = None
    verified_by: str | None = None
    assumption_of_risk: str | None = None
    verdict_controls: list[VerdictControl]


class FeedResponse(BaseModel):
    generated_at: dt.datetime
    count: int
    cards: list[FeedCard]


# --------------------------------------------------------------------------
# places
# --------------------------------------------------------------------------


class PlaceSearchResult(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    lat: float
    lng: float
    distance_km: float
    activities: list[str] = []


class AffordanceDetail(BaseModel):
    affordance_id: uuid.UUID
    activity_id: str
    activity_name: str
    hazard_class: bool
    difficulty: int | None = None
    typical_duration_min: float | None = None
    dog_ok: bool | None = None
    kid_ok: bool | None = None
    windows: list[WindowOut] = []
    claims: list[ClaimOut] = []
    last_verified_at: dt.datetime | None = None
    verified_by: str | None = None
    assumption_of_risk: str | None = None


class PlacePage(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    lat: float
    lng: float
    elev_m: int | None = None
    affordances: list[AffordanceDetail] = []


# --------------------------------------------------------------------------
# saves / trips / verdicts
# --------------------------------------------------------------------------

SaveKind = Literal["want_to", "been", "loved"]


class SaveIn(BaseModel):
    affordance_id: uuid.UUID
    kind: SaveKind


class SavedItem(BaseModel):
    affordance_id: uuid.UUID
    kind: SaveKind
    place_id: uuid.UUID
    place_name: str
    activity_id: str
    created_at: dt.datetime
    last_alerted_at: dt.datetime | None = None


class TripIn(BaseModel):
    affordance_id: uuid.UUID
    planned_date: dt.date


class TripOut(BaseModel):
    id: uuid.UUID
    affordance_id: uuid.UUID
    planned_date: dt.date
    declared_at: dt.datetime


class VerdictIn(BaseModel):
    claim_id: uuid.UUID
    verdict: VerdictLiteral
    trip_id: uuid.UUID | None = None


class VerdictOut(BaseModel):
    verification_id: uuid.UUID
    claim_id: uuid.UUID
    verdict: VerdictLiteral
    log_odds: float
    confidence: float
    conditions_snapshot: dict[str, Any]
    superseding_claim_id: uuid.UUID | None = None


# --------------------------------------------------------------------------
# auth / push / events
# --------------------------------------------------------------------------


class MagicLinkIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v[1:-1]:
            raise ValueError("not an email address")
        return v


class VerifyIn(BaseModel):
    token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = None
    power_verifier: bool = False
    is_founder: bool = False


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=8)
    keys: PushKeys


# /events accepts the product verbs (docs/04 section 5) and maps them onto
# the feed_event_t enum; raw enum values are accepted too.
EVENT_ALIASES: dict[str, str] = {
    "shown": "impression",
    "saved": "save",
    "went": "going",
    "verified": "verified",
    "impression": "impression",
    "card_open": "card_open",
    "save": "save",
    "going": "going",
    "rejected": "rejected",
}


class EventIn(BaseModel):
    affordance_id: uuid.UUID
    etype: str
    now_score: float | None = None
    conditions_snapshot: dict[str, Any] | None = None

    @field_validator("etype")
    @classmethod
    def _known_event(cls, v: str) -> str:
        if v not in EVENT_ALIASES:
            raise ValueError(f"etype must be one of {sorted(EVENT_ALIASES)}")
        return EVENT_ALIASES[v]


class EventOut(BaseModel):
    id: int
    etype: str
    affordance_id: uuid.UUID


# --------------------------------------------------------------------------
# admin review queue
# --------------------------------------------------------------------------


class ReviewQueueItem(BaseModel):
    id: uuid.UUID
    affordance_id: uuid.UUID
    place_name: str
    activity_id: str
    cclass: str
    source_type: str
    source_url: str | None = None
    source_domain: str | None = None
    observed_date: dt.date | None = None
    extractor_ver: str | None = None
    self_conf: float | None = None
    log_odds: float
    created_at: dt.datetime


class ClaimEdits(BaseModel):
    cclass: Literal["geomorphic", "seasonal_bio", "access", "hazard_calibration"] | None = None
    source_url: str | None = None
    source_domain: str | None = None
    observed_date: dt.date | None = None
    self_conf: float | None = None
    log_odds: float | None = None


class ReviewActionIn(BaseModel):
    claim_id: uuid.UUID
    action: Literal["approve", "reject", "edit"]
    edits: ClaimEdits | None = None
    publish_affordance: bool = True


class ReviewActionOut(BaseModel):
    claim_id: uuid.UUID
    claim_status: str
    affordance_id: uuid.UUID
    affordance_published: bool = False
    gate_error: str | None = None
