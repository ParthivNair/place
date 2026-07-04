"""SQLAlchemy Core Table objects, mirroring alembic/versions/0001_baseline.py exactly.

The migration is the source of truth (hand-written SQL); these Tables exist for
query building only. Enum types use create_type=False — the migration owns DDL.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Interval,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TIMESTAMP, UUID

from place.db import Geometry, Vector, metadata


def _enum(name: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, create_type=False)


window_type = _enum(
    "window_type", "seasonal", "weather_triggered", "hydrological", "tidal",
    "astronomical", "snow",
)
source_type = _enum(
    "source_type", "llm_extracted", "user_reported", "founder_verified", "sensor_derived",
)
claim_class = _enum(
    "claim_class", "geomorphic", "seasonal_bio", "access", "hazard_calibration",
)
verdict_type = _enum("verdict_type", "confirm", "refute", "changed")
pub_status = _enum("pub_status", "draft", "review", "published", "suppressed")
save_kind = _enum("save_kind", "want_to", "been", "loved")
feed_event_t = _enum(
    "feed_event_t", "impression", "card_open", "save", "going", "verified", "rejected",
)

_uuid_pk = dict(
    primary_key=True, server_default=text("gen_random_uuid()"),
)
_now = text("now()")


feeds = Table(
    "feeds", metadata,
    Column("id", Text, primary_key=True),           # 'usgs_nwis:14210000:00060'
    Column("provider", Text, nullable=False),
    Column("station_ref", Text),
    Column("parameter", Text, nullable=False),
    Column("unit", Text, nullable=False),
    Column("poll_interval", Interval, nullable=False, server_default=text("'1 hour'::interval")),
    Column("last_value", Numeric),
    Column("last_observed_at", TIMESTAMP(timezone=True)),
)

# Declaratively partitioned by month (RANGE on observed_at); partitions are
# created by db.ensure_feed_readings_partitions + a DEFAULT partition.
feed_readings = Table(
    "feed_readings", metadata,
    Column("feed_id", Text, ForeignKey("feeds.id"), nullable=False),
    Column("observed_at", TIMESTAMP(timezone=True), nullable=False),
    Column("value", Numeric, nullable=False),
    PrimaryKeyConstraint("feed_id", "observed_at"),
    Index("feed_readings_recent", "feed_id", text("observed_at DESC")),
    postgresql_partition_by="RANGE (observed_at)",
)

feed_health = Table(
    "feed_health", metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("feed_id", Text, ForeignKey("feeds.id"), nullable=False),
    Column("checked_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Column("ok", Boolean, nullable=False),
    Column("latency_ms", Integer),
    Column("reading_observed_at", TIMESTAMP(timezone=True)),
    Column("error", Text),
    Index("feed_health_feed", "feed_id", text("checked_at DESC")),
)

places = Table(
    "places", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("geom", Geometry("Point", 4326), nullable=False),
    Column("osm_id", BigInteger),
    Column("gnis_id", Text),
    Column("ridb_id", Text),
    Column("elev_m", Integer),
    Column("sensitive", Boolean, nullable=False, server_default=text("false")),
    Column("name_embedding", Vector(1024)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
)

access_points = Table(
    "access_points", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("place_id", UUID(as_uuid=True), ForeignKey("places.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("geom", Geometry("Point", 4326), nullable=False),
    Column("osm_id", BigInteger),
    Column("notes", Text),
)

activities = Table(
    "activities", metadata,
    Column("id", Text, primary_key=True),
    Column("display_name", Text, nullable=False),
    Column("hazard_class", Boolean, nullable=False, server_default=text("false")),
)

affordances = Table(
    "affordances", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("place_id", UUID(as_uuid=True), ForeignKey("places.id"), nullable=False),
    Column("activity_id", Text, ForeignKey("activities.id"), nullable=False),
    Column("difficulty", SmallInteger),
    Column("typical_duration", Interval),
    Column("dog_ok", Boolean),
    Column("kid_ok", Boolean),
    Column("base_quality", Numeric, nullable=False, server_default=text("0.5")),
    Column("status", pub_status, nullable=False, server_default=text("'draft'")),
    UniqueConstraint("place_id", "activity_id"),
)

condition_windows = Table(
    "condition_windows", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), nullable=False),
    Column("wtype", window_type, nullable=False),
    Column("predicate", JSONB, nullable=False),
    Column("multiplier", Numeric, nullable=False, server_default=text("1.5")),
    Column("is_gate", Boolean, nullable=False, server_default=text("false")),
    Column("state", Boolean),                       # NULL = unknown
    Column("state_since", TIMESTAMP(timezone=True)),
    Column("last_eval", TIMESTAMP(timezone=True)),
    Index("cw_affordance", "affordance_id"),
    Index("cw_state_flip", "state", "state_since"),
)

condition_states = Table(
    "condition_states", metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("window_id", UUID(as_uuid=True), ForeignKey("condition_windows.id"), nullable=False),
    Column("satisfied", Boolean, nullable=False),
    Column("evaluated_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Column("inputs", JSONB, nullable=False),
    Index("condition_states_window", "window_id", text("evaluated_at DESC")),
)

claims = Table(
    "claims", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), nullable=False),
    Column("window_id", UUID(as_uuid=True), ForeignKey("condition_windows.id")),
    Column("cclass", claim_class, nullable=False),
    Column("stype", source_type, nullable=False),
    Column("source_url", Text),
    Column("source_domain", Text),
    Column("quote_internal", Text),                  # NEVER serialized by any API
    Column("observed_date", Date),
    Column("extractor_ver", Text),
    Column("self_conf", Numeric),
    Column("status", pub_status, nullable=False, server_default=text("'review'")),
    Column("log_odds", Numeric, nullable=False),
    Column("last_evidence_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Column("superseded_by", UUID(as_uuid=True), ForeignKey("claims.id")),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Index("claims_affordance", "affordance_id", "cclass"),
)

users = Table(
    "users", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("email", Text, nullable=False, unique=True),
    Column("display_name", Text),
    Column("power_verifier", Boolean, nullable=False, server_default=text("false")),
    Column("home_geom", Geometry("Point", 4326)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
)

verifications = Table(
    "verifications", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("claim_id", UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("trip_id", UUID(as_uuid=True), ForeignKey("trips.id")),
    Column("verdict", verdict_type, nullable=False),
    Column("conditions_snapshot", JSONB, nullable=False),
    Column("verified_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Index("verifications_claim", "claim_id", text("verified_at DESC")),
)

saves = Table(
    "saves", metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), nullable=False),
    Column("kind", save_kind, nullable=False),
    Column("last_alerted_at", TIMESTAMP(timezone=True)),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    PrimaryKeyConstraint("user_id", "affordance_id", "kind"),
)

trips = Table(
    "trips", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), nullable=False),
    Column("planned_date", Date, nullable=False),
    Column("declared_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
    Column("followed_up", Boolean, nullable=False, server_default=text("false")),
)

feed_events = Table(
    "feed_events", metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), nullable=False),
    Column("etype", feed_event_t, nullable=False),
    Column("now_score", Numeric),
    Column("conditions_snapshot", JSONB, nullable=False),
    Column("occurred_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
)

good_now = Table(
    "good_now", metadata,
    Column(
        "affordance_id", UUID(as_uuid=True), ForeignKey("affordances.id"), primary_key=True
    ),
    Column("now_score", Numeric, nullable=False),
    Column("reasons", JSONB, nullable=False),
    Column("computed_at", TIMESTAMP(timezone=True), nullable=False),
    Index("good_now_rank", text("now_score DESC")),
)

place_edges = Table(
    "place_edges", metadata,
    Column("src", UUID(as_uuid=True), ForeignKey("places.id"), nullable=False),
    Column("dst", UUID(as_uuid=True), ForeignKey("places.id"), nullable=False),
    Column("etype", Text, nullable=False),
    Column("weight", Numeric, nullable=False, server_default=text("0")),
    PrimaryKeyConstraint("src", "dst", "etype"),
    CheckConstraint("etype IN ('quiet_alternative_to','pairs_with')", name="place_edges_etype"),
)

push_subscriptions = Table(
    "push_subscriptions", metadata,
    Column("id", UUID(as_uuid=True), **_uuid_pk),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("endpoint", Text, nullable=False, unique=True),
    Column("p256dh", Text, nullable=False),
    Column("auth", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_now),
)
