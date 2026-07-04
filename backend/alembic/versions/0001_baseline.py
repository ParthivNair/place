"""Baseline: full experience-graph DDL from docs/01-EXPERIENCE-GRAPH.md section 2.

Hand-written (no autogen). Deltas vs the doc, all additive:
- feed_readings is declaratively partitioned by month (RANGE on observed_at)
  with a DEFAULT partition; doc text prescribes the partitioning, its inline
  DDL just doesn't show it.
- condition_states / feed_health / push_subscriptions: support tables required
  by docs/04 (evaluator audit trail, adapter health, /push/subscribe).
- pg_trgm extension + GIN trgm index on places.name (keyless entity-resolution
  fallback per the build brief).
- Publication-gate trigger on affordances (docs/04 PR-5: DB-enforced).
"""

from collections.abc import Sequence

import place.db as pdb
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DDL = r"""
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------- enums ----------
CREATE TYPE window_type   AS ENUM ('seasonal','weather_triggered','hydrological',
                                   'tidal','astronomical','snow');
CREATE TYPE source_type   AS ENUM ('llm_extracted','user_reported',
                                   'founder_verified','sensor_derived');
CREATE TYPE claim_class   AS ENUM ('geomorphic','seasonal_bio','access',
                                   'hazard_calibration');
CREATE TYPE verdict_type  AS ENUM ('confirm','refute','changed');
CREATE TYPE pub_status    AS ENUM ('draft','review','published','suppressed');
CREATE TYPE save_kind     AS ENUM ('want_to','been','loved');
CREATE TYPE feed_event_t  AS ENUM ('impression','card_open','save','going',
                                   'verified','rejected');

-- ---------- named external feeds ----------
CREATE TABLE feeds (
  id               text PRIMARY KEY,      -- 'usgs_nwis:14210000:00060'
  provider         text NOT NULL,  -- usgs_nwis|noaa_coops|snotel|nwac|nws|open_meteo|airnow|astro
  station_ref      text,
  parameter        text NOT NULL,
  unit             text NOT NULL,
  poll_interval    interval NOT NULL DEFAULT '1 hour',
  last_value       numeric,
  last_observed_at timestamptz
);

-- Partitioned by month; kept indefinitely (docs/01 retention decision).
CREATE TABLE feed_readings (
  feed_id     text NOT NULL REFERENCES feeds(id),
  observed_at timestamptz NOT NULL,
  value       numeric NOT NULL,
  PRIMARY KEY (feed_id, observed_at)
) PARTITION BY RANGE (observed_at);
CREATE INDEX feed_readings_recent ON feed_readings (feed_id, observed_at DESC);
CREATE TABLE feed_readings_default PARTITION OF feed_readings DEFAULT;

CREATE TABLE feed_health (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  feed_id             text NOT NULL REFERENCES feeds(id),
  checked_at          timestamptz NOT NULL DEFAULT now(),
  ok                  boolean NOT NULL,
  latency_ms          integer,
  reading_observed_at timestamptz,
  error               text
);
CREATE INDEX feed_health_feed ON feed_health (feed_id, checked_at DESC);

-- ---------- core graph ----------
CREATE TABLE places (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  kind        text NOT NULL,
  geom        geometry(Point, 4326) NOT NULL,
  osm_id      bigint,
  gnis_id     text,
  ridb_id     text,
  elev_m      integer,
  sensitive   boolean NOT NULL DEFAULT false,
  name_embedding vector(1024),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX places_geom_gist ON places USING GIST (geom);
CREATE INDEX places_name_vec  ON places USING hnsw (name_embedding vector_cosine_ops);
CREATE INDEX places_name_trgm ON places USING GIN (name gin_trgm_ops);
CREATE UNIQUE INDEX places_osm ON places (osm_id) WHERE osm_id IS NOT NULL;

CREATE TABLE access_points (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id    uuid NOT NULL REFERENCES places(id),
  kind        text NOT NULL,
  geom        geometry(Point, 4326) NOT NULL,
  osm_id      bigint,
  notes       text
);
CREATE INDEX access_points_geom_gist ON access_points USING GIST (geom);

CREATE TABLE activities (
  id            text PRIMARY KEY,
  display_name  text NOT NULL,
  hazard_class  boolean NOT NULL DEFAULT false
);

CREATE TABLE affordances (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id      uuid NOT NULL REFERENCES places(id),
  activity_id   text NOT NULL REFERENCES activities(id),
  difficulty    smallint,
  typical_duration interval,
  dog_ok        boolean,
  kid_ok        boolean,
  base_quality  numeric NOT NULL DEFAULT 0.5,
  status        pub_status NOT NULL DEFAULT 'draft',
  UNIQUE (place_id, activity_id)
);
CREATE INDEX affordances_published ON affordances (activity_id) WHERE status = 'published';

CREATE TABLE condition_windows (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  wtype         window_type NOT NULL,
  predicate     jsonb NOT NULL,
  multiplier    numeric NOT NULL DEFAULT 1.5,
  is_gate       boolean NOT NULL DEFAULT false,
  state         boolean,              -- NULL = unknown
  state_since   timestamptz,
  last_eval     timestamptz
);
CREATE INDEX cw_affordance ON condition_windows (affordance_id);
CREATE INDEX cw_state_flip ON condition_windows (state, state_since);

CREATE TABLE condition_states (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  window_id     uuid NOT NULL REFERENCES condition_windows(id),
  satisfied     boolean NOT NULL,
  evaluated_at  timestamptz NOT NULL DEFAULT now(),
  inputs        jsonb NOT NULL
);
CREATE INDEX condition_states_window ON condition_states (window_id, evaluated_at DESC);

CREATE TABLE claims (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  affordance_id  uuid NOT NULL REFERENCES affordances(id),
  window_id      uuid REFERENCES condition_windows(id),
  cclass         claim_class NOT NULL,
  stype          source_type NOT NULL,
  source_url     text,
  source_domain  text,
  quote_internal text,                 -- never republished by any serializer
  observed_date  date,
  extractor_ver  text,
  self_conf      numeric,
  status         pub_status NOT NULL DEFAULT 'review',
  log_odds       numeric NOT NULL,
  last_evidence_at timestamptz NOT NULL DEFAULT now(),
  superseded_by  uuid REFERENCES claims(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX claims_affordance ON claims (affordance_id, cclass);

-- ---------- users & exhaust ----------
CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text UNIQUE NOT NULL,
  display_name   text,
  power_verifier boolean NOT NULL DEFAULT false,
  home_geom      geometry(Point, 4326),
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE trips (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  planned_date  date NOT NULL,
  declared_at   timestamptz NOT NULL DEFAULT now(),
  followed_up   boolean NOT NULL DEFAULT false
);
CREATE INDEX trips_followup ON trips (planned_date) WHERE NOT followed_up;

CREATE TABLE verifications (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id     uuid NOT NULL REFERENCES claims(id),
  user_id      uuid NOT NULL REFERENCES users(id),
  trip_id      uuid REFERENCES trips(id),
  verdict      verdict_type NOT NULL,
  conditions_snapshot jsonb NOT NULL,
  verified_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX verifications_claim ON verifications (claim_id, verified_at DESC);

CREATE TABLE saves (
  user_id       uuid NOT NULL REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  kind          save_kind NOT NULL,
  last_alerted_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, affordance_id, kind)
);

CREATE TABLE feed_events (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       uuid REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  etype         feed_event_t NOT NULL,
  now_score     numeric,
  conditions_snapshot jsonb NOT NULL,
  occurred_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feed_events_time ON feed_events USING BRIN (occurred_at);

CREATE TABLE push_subscriptions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id),
  endpoint    text UNIQUE NOT NULL,
  p256dh      text NOT NULL,
  auth        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------- materialization ----------
CREATE TABLE good_now (
  affordance_id uuid PRIMARY KEY REFERENCES affordances(id),
  now_score     numeric NOT NULL,
  reasons       jsonb NOT NULL,
  computed_at   timestamptz NOT NULL
);
CREATE INDEX good_now_rank ON good_now (now_score DESC);

CREATE TABLE place_edges (
  src uuid REFERENCES places(id), dst uuid REFERENCES places(id),
  etype text NOT NULL CHECK (etype IN ('quiet_alternative_to','pairs_with')),
  weight numeric NOT NULL DEFAULT 0,
  PRIMARY KEY (src, dst, etype)
);

-- ---------- publication gate (docs/04 PR-5: DB-enforced, docs/01 section 4 rule 2) ----------
-- Structural gate on the transition to 'published': >=2 published, non-superseded
-- claims from independent source_domains OR >=1 published founder_verified /
-- user_reported claim. The confidence bar (>=0.45) and the hazard serving gates
-- are time-varying and enforced at query time (good_now, docs/01 section 7 Q1).
CREATE FUNCTION affordance_publication_gate() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  n_domains   integer;
  has_support boolean;
BEGIN
  IF NEW.status = 'published'
     AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'published') THEN
    SELECT count(DISTINCT c.source_domain) INTO n_domains
    FROM claims c
    WHERE c.affordance_id = NEW.id
      AND c.status = 'published'
      AND c.superseded_by IS NULL
      AND c.source_domain IS NOT NULL;

    SELECT EXISTS (
      SELECT 1 FROM claims c
      WHERE c.affordance_id = NEW.id
        AND c.status = 'published'
        AND c.superseded_by IS NULL
        AND c.stype IN ('founder_verified','user_reported')
    ) INTO has_support;

    IF n_domains < 2 AND NOT has_support THEN
      RAISE EXCEPTION USING
        ERRCODE = 'check_violation',
        MESSAGE = format(
          'publication gate: affordance %s needs >=2 published claims from '
          'independent source_domains or a founder_verified/user_reported claim',
          NEW.id);
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER affordances_publication_gate
  BEFORE INSERT OR UPDATE OF status ON affordances
  FOR EACH ROW EXECUTE FUNCTION affordance_publication_gate();
"""


def upgrade() -> None:
    for stmt in _split(DDL):
        op.execute(stmt)
    # current + next month partitions (DEFAULT already exists as backstop)
    pdb.ensure_feed_readings_partitions(op.get_bind())


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS place_edges, good_now, push_subscriptions, feed_events,
          saves, verifications, trips, users, claims, condition_states,
          condition_windows, affordances, activities, access_points, places,
          feed_health, feed_readings, feeds CASCADE;
        DROP FUNCTION IF EXISTS affordance_publication_gate();
        DROP TYPE IF EXISTS feed_event_t, save_kind, pub_status, verdict_type,
          claim_class, source_type, window_type;
        """
    )


def _split(sql: str) -> list[str]:
    """Split on semicolons at end-of-statement, keeping $$-quoted bodies intact."""
    stmts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in sql.splitlines():
        if line.count("$$") % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt.strip("; \n"):
                stmts.append(stmt)
            buf = []
    if any(line.strip() for line in buf):
        stmts.append("\n".join(buf).strip())
    return stmts
