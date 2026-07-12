# The Experience Graph — Ontology & Schema

**In one breath:** The experience graph is the substrate the WHEN engine runs on ([00-THESIS.md](00-THESIS.md) §2) — eleven core Postgres tables plus five support tables (PostGIS + pgvector) in which the *Affordance* — "you can wild-swim at High Rocks" — is a first-class node, not a tag; every affordance binds to machine-evaluable *ConditionWindows* (JSON predicates over named public feeds like USGS gauge 14210000), is supported by provenance-carrying *Claims*, and accumulates a *Verification* log with auto-attached condition snapshots. The engine core survives the reframe untouched: condition windows, the evaluator sweep, and the watcher query (§7 Q3) *are* the window engine — the reframe re-centers them, it does not change them. What is new is deliberately thin and clearly fenced: three window types and a two-table product layer (watchables and watchers, §2a), every DDL element of which is a **committed addition slated for the Phase 1 migration in [05-ROADMAP.md](05-ROADMAP.md)** — this document mirrors shipped code, and the code has not changed yet. Confidence is log-odds math: source-type priors, +0.5 nats per independent corroborating source, Bayesian updates from verification verdicts (+1.50 confirm / −2.08 refute), and per-claim-class exponential decay whose half-lives are eventually *learned* from the verification log itself. Nothing auto-publishes from a single LLM extraction, and hazard-class affordances additionally require a recent verification plus a currently-true live trigger. This document is the engineering contract: the DDL, the predicate DSL, the update math, and the four canonical queries the product runs.

Vocabulary (affordance, condition window, claim, verification, binding — and the product layer's watchable and watcher) is defined narratively in [00-THESIS.md](00-THESIS.md) §8; the family doctrine behind the new window types is [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md); the Almanac's editorial spec is [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md); how the tables get *filled* is [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); where the evaluator cron and feed pollers live is [04-ARCHITECTURE.md](04-ARCHITECTURE.md).

---

## 1. Ontology

**Entities:** `Place` (canonical, with OSM/GNIS/RIDB crosswalk IDs and geometry), `AccessPoint` (trailhead, parking lot, put-in — where you actually go, distinct from the thing you go to see), `Activity` (a closed vocabulary of ~120 verbs: wild-swim, cliff-jump, larch-view, tidepool, stargaze, paddle, snowshoe, forage…), `Affordance` (the reified place×activity node carrying difficulty, typical duration, dog/kid flags), `ConditionWindow` (typed seasonal | weather_triggered | hydrological | tidal | astronomical | snow — plus availability, air_quality, and phenological, committed Phase 1 additions per §2; body is an executable predicate over a named feed), `Claim` (provenance record with source type, URL, minimal internal verbatim quote, **observed_date** — when the experience happened, not when it was posted — extractor version, confidence), `Verification` (one-tap verdict + auto conditions snapshot), and `Hazard` handling as a *claim class and activity flag* with stricter gates rather than a separate node type.

**Edges:** Place–SUPPORTS→Activity (materialized as the Affordance row); Affordance–VALID_WHEN→ConditionWindow; Claim–ASSERTS→Affordance; Verification–CONFIRMS/REFUTES→Claim; Place–ACCESSED_VIA→AccessPoint; Place–QUIET_ALTERNATIVE_TO→Place and Place–PAIRS_WITH→Place (deferred edges, schema-ready via `place_edges`); User–DID/SAVED/REJECTED→Affordance (the `saves`, `trips`, and `feed_events` tables).

**Why reified affordances beat activity-as-tag** (stated once, here): a tag is a boolean on someone else's primary key — it cannot carry a condition predicate, a provenance chain, a confidence value, or a verification history, which means it can never answer "is this good *now*, and how do you know?" AllTrails tags a trail "swimming" and the knowledge stops there; Place's `affordance` row is the anchor every claim asserts, every condition window gates, and every Sunday-night verification tap updates — the tag model is precisely the ceiling the product is built to break through.

---

## 2. Schema (Postgres 16 + PostGIS + pgvector)

Committed store: **Postgres + PostGIS + pgvector** ([04-ARCHITECTURE.md](04-ARCHITECTURE.md) carries the deployment side of this decision). Neo4j lost on operational overhead and weak geo; keeping the repo's Mongo lost because at ~140 lines there is nothing to migrate. The product is joins — affordance × condition × live feed × verification — and recursive CTEs cover every traversal we need.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- enums ----------
CREATE TYPE window_type   AS ENUM ('seasonal','weather_triggered','hydrological',
                                   'tidal','astronomical','snow');
-- COMMITTED ADDITION — Phase 1 migration (docs/05-ROADMAP.md); not yet in code:
--   ALTER TYPE window_type ADD VALUE 'availability';  -- reservation family: inventory-state predicates
--   ALTER TYPE window_type ADD VALUE 'air_quality';   -- health family: AirNow / heat-index predicates
--   ALTER TYPE window_type ADD VALUE 'phenological';  -- bloom/flush/foliage earn their own type
--                                                     --   rather than overloading 'seasonal'
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
  id              text PRIMARY KEY,      -- 'usgs_nwis:14210000:00060'
  provider        text NOT NULL,         -- usgs_nwis|noaa_coops|snotel|nwac|nws|open_meteo|airnow|astro
                                         --   + swpc (committed, Phase 1) and recgov (committed, Phase 4)
  station_ref     text,                  -- provider-native station/point id
  parameter       text NOT NULL,         -- discharge_cfs|tide_pred_ft_mllw|swe_in|precip_in|...
  unit            text NOT NULL,
  poll_interval   interval NOT NULL DEFAULT '1 hour',
  last_value      numeric,
  last_observed_at timestamptz
);

CREATE TABLE feed_readings (              -- windowed aggregates (72-h sums); kept indefinitely, see design notes
  feed_id     text NOT NULL REFERENCES feeds(id),
  observed_at timestamptz NOT NULL,
  value       numeric NOT NULL,
  PRIMARY KEY (feed_id, observed_at)
);
CREATE INDEX feed_readings_recent ON feed_readings (feed_id, observed_at DESC);

-- ---------- core graph ----------
CREATE TABLE places (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  kind        text NOT NULL,              -- waterfall|swim_hole|viewpoint|tidepool_area|peak|...
                                          --   + region (committed, Phase 1 — the placeless-window anchor, §2a)
  geom        geometry(Point, 4326) NOT NULL,  -- widens beyond Point for kind='region' rows (Phase 1, §2a)
  osm_id      bigint,
  gnis_id     text,
  ridb_id     text,
  elev_m      integer,
  sensitive   boolean NOT NULL DEFAULT false,   -- curated exclusion list (§7 of brief)
  name_embedding vector(1024),            -- entity resolution for extraction pipeline
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX places_geom_gist ON places USING GIST (geom);
CREATE INDEX places_name_vec  ON places USING hnsw (name_embedding vector_cosine_ops);
CREATE UNIQUE INDEX places_osm ON places (osm_id) WHERE osm_id IS NOT NULL;

CREATE TABLE access_points (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id    uuid NOT NULL REFERENCES places(id),
  kind        text NOT NULL,              -- trailhead|parking|put_in|beach_access
  geom        geometry(Point, 4326) NOT NULL,
  osm_id      bigint,
  notes       text                        -- 'lot ~20 cars, fills by 10am summer weekends'
);
CREATE INDEX access_points_geom_gist ON access_points USING GIST (geom);

CREATE TABLE activities (                 -- closed vocabulary, ~120 rows, hand-curated
  id            text PRIMARY KEY,         -- 'wild_swim','cliff_jump','larch_view','tidepool'
  display_name  text NOT NULL,
  hazard_class  boolean NOT NULL DEFAULT false   -- cliff_jump, wild_swim, snow_travel = true
);

CREATE TABLE affordances (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id      uuid NOT NULL REFERENCES places(id),
  activity_id   text NOT NULL REFERENCES activities(id),
  difficulty    smallint,                 -- 1..5
  typical_duration interval,
  dog_ok        boolean,
  kid_ok        boolean,
  base_quality  numeric NOT NULL DEFAULT 0.5,   -- 0..1, editorial seed, later learned
  status        pub_status NOT NULL DEFAULT 'draft',
  UNIQUE (place_id, activity_id)
);
CREATE INDEX affordances_published ON affordances (activity_id) WHERE status = 'published';

CREATE TABLE condition_windows (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  wtype         window_type NOT NULL,
  predicate     jsonb NOT NULL,           -- the DSL, §3
  multiplier    numeric NOT NULL DEFAULT 1.5,  -- now_score boost while satisfied
  is_gate       boolean NOT NULL DEFAULT false,-- if true, affordance hidden unless satisfied
  state         boolean,                  -- current evaluation result
  state_since   timestamptz,
  last_eval     timestamptz
);
CREATE INDEX cw_affordance ON condition_windows (affordance_id);
CREATE INDEX cw_state_flip ON condition_windows (state, state_since);

CREATE TABLE condition_states (           -- per-evaluation history; current state stays on condition_windows
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  window_id     uuid NOT NULL REFERENCES condition_windows(id),
  satisfied     boolean NOT NULL,
  evaluated_at  timestamptz NOT NULL DEFAULT now(),
  inputs        jsonb NOT NULL             -- the exact readings used, keyed by feeds.id
);
CREATE INDEX condition_states_window ON condition_states (window_id, evaluated_at DESC);

CREATE TABLE claims (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  affordance_id  uuid NOT NULL REFERENCES affordances(id),
  window_id      uuid REFERENCES condition_windows(id),  -- when claim calibrates a threshold
  cclass         claim_class NOT NULL,
  stype          source_type NOT NULL,
  source_url     text,
  source_domain  text,                    -- 'reddit.com','oregonhikers.org' — independence check
  quote_internal text,                    -- minimal verbatim evidence, NEVER republished
  observed_date  date,                    -- when the experience happened
  extractor_ver  text,                    -- 'haiku-batch-v3' — enables cheap re-extraction
  self_conf      numeric,                 -- extractor's own 0..1
  status         pub_status NOT NULL DEFAULT 'review',  -- §4 gate 1: the review queue; only 'published' claims serve
  log_odds       numeric NOT NULL,        -- L, the living confidence state (§5)
  last_evidence_at timestamptz NOT NULL DEFAULT now(),   -- decay clock
  superseded_by  uuid REFERENCES claims(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX claims_affordance ON claims (affordance_id, cclass);

CREATE TABLE verifications (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id     uuid NOT NULL REFERENCES claims(id),
  user_id      uuid NOT NULL REFERENCES users(id),
  trip_id      uuid REFERENCES trips(id),
  verdict      verdict_type NOT NULL,
  conditions_snapshot jsonb NOT NULL,     -- keyed by feeds.id: {'usgs_nwis:14210000:00060': 410, ...}
  verified_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX verifications_claim ON verifications (claim_id, verified_at DESC);

-- ---------- users & exhaust ----------
CREATE TABLE users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text UNIQUE NOT NULL,    -- magic-link auth, see 04-ARCHITECTURE.md
  display_name   text,
  power_verifier boolean NOT NULL DEFAULT false,  -- named provenance credit
  home_geom      geometry(Point, 4326),
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE saves (                      -- saves ARE standing queries (§7 Q3, the watcher query);
                                          --   generalizes to watchers in Phase 1 (§2a)
  user_id       uuid NOT NULL REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  kind          save_kind NOT NULL,
  last_alerted_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, affordance_id, kind)
);

CREATE TABLE trips (                      -- the "I'm going" tap
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  planned_date  date NOT NULL,
  declared_at   timestamptz NOT NULL DEFAULT now(),
  followed_up   boolean NOT NULL DEFAULT false    -- Sunday push sent?
);
CREATE INDEX trips_followup ON trips (planned_date) WHERE NOT followed_up;

CREATE TABLE feed_events (                -- moat M4: temporal ranking exhaust, logged from user #1
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       uuid REFERENCES users(id),
  affordance_id uuid NOT NULL REFERENCES affordances(id),
  etype         feed_event_t NOT NULL,
  now_score     numeric,
  conditions_snapshot jsonb NOT NULL,     -- condition vector X, place Y, date Z: the label
  occurred_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feed_events_time ON feed_events USING BRIN (occurred_at);

-- ---------- materialization ----------
CREATE TABLE good_now (                   -- rewritten by the evaluator cron, §7 Q1
  affordance_id uuid PRIMARY KEY REFERENCES affordances(id),
  now_score     numeric NOT NULL,
  reasons       jsonb NOT NULL,           -- [{'window_id':..., 'wtype':...}]; text rendered from leaf + live reading (§6)
  computed_at   timestamptz NOT NULL
);
CREATE INDEX good_now_rank ON good_now (now_score DESC);

CREATE TABLE place_edges (                -- M5, deferred but schema-ready
  src uuid REFERENCES places(id), dst uuid REFERENCES places(id),
  etype text NOT NULL CHECK (etype IN ('quiet_alternative_to','pairs_with')),
  weight numeric NOT NULL DEFAULT 0,
  PRIMARY KEY (src, dst, etype)
);
```

Design decisions worth one line each: `log_odds` lives on the claim (confidence is *state*, recomputed on read with decay — §5); geometry over geography type because all math is regional and GIST + `ST_DWithin` on geography casts where needed; `feed_readings` kept indefinitely, partitioned by month (at one-metro scale the volume is trivial for Postgres, and reading history is calibration material for learning thresholds and decay parameters); `condition_states` exists for the audit trail — every recommendation served logs its conditions snapshot, the safety requirement in [02-PRODUCT.md](02-PRODUCT.md) §5 — and as the source for `/verdicts` auto-snapshots, while current state stays denormalized on `condition_windows` (`state`, `state_since`, `last_eval`) for cheap reads; `quote_internal` is schema-enforced private by never appearing in any API serializer; hazard is a claim class + activity flag, not a table — a deliberate narrowing of the ontology's `Hazard` entity ("dedicated class with stricter publication gates"): the class survives as `hazard_calibration` + `hazard_class`, the stricter gates survive intact in §4, and only the separate node type is dropped, because a hazard is a property of what's being claimed, not a different kind of node.

---

## 2a. Watchables and watchers — the thin product layer

*(Numbered 2a so that §3–§7 — referenced by sibling docs and by code comments in `backend/place/` — keep their addresses.)*

The WHEN reframe adds exactly two tables, and **no change to any existing graph table**: places, affordances, condition windows, claims, and verifications are the substrate and stay frozen. Both tables below are **committed additions slated for the Phase 1 migration in [05-ROADMAP.md](05-ROADMAP.md)** — DDL sketches, not shipped code.

### (a) Watchables — the editorial layer

A watchable is one curated, nameable moment in the Almanac ("Haystack minus tides"): an editorial row *over* existing condition windows and affordances. Its anatomy, naming voice, curation gates, and launch composition are [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md)'s to specify — this doc only fixes where it sits in the schema. Sketch:

```sql
-- COMMITTED ADDITION — Phase 1 migration (docs/05-ROADMAP.md). DDL SKETCH ONLY.
CREATE TABLE watchables (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text UNIQUE NOT NULL,      -- 'haystack-minus-tides'
  name          text NOT NULL,             -- 'Haystack minus tides'
  promise       text NOT NULL,             -- the one-line editorial promise (voice rules: 09)
  family        text NOT NULL,             -- outdoor|sky|harvest|reservation|health|crowd (08)
  window_ids    uuid[] NOT NULL,           -- refs into condition_windows; becomes a join
                                           --   table if curation churn ever demands FKs
  expected_open_freq text,                 -- 'opens ~6×/winter' — stated from backtest (09's gate)
  backtest_opens_per_season numeric,       -- computed against 5 years of feed history
  measured_hit_rate numeric,               -- live precision; the publication floor is 09's
  hazard_flag    boolean NOT NULL DEFAULT false,
  dispersal_flag boolean NOT NULL DEFAULT false,  -- forage-class: regions, never pins (02 §5)
  status        pub_status NOT NULL DEFAULT 'draft'
);
```

Delete every `watchables` row and the graph is untouched — that is the design test for "editorial layer," and it is why the Almanac's prose is explicitly not a moat ([00-THESIS.md](00-THESIS.md) §3).

### (b) Watchers — the generalization of saves

Saves already ARE standing queries — §7 Q3 has run against the `saves` table since the first line of DDL, and that is the whole reason the paid product is cheap to build. The Phase 1 generalization renames the concept and adds the three things the product contract needs: an **optional watchable ref** (watch an Almanac entry, not just a single affordance), a **delivery contract** — a watcher fires on the *open transition* only, never on readings, and every fire logs delivery telemetry, because "guaranteed delivery" is a measured claim before it is a marketing one — and a **tier flag** for the Vigilance gate (tiers and pricing live in [02-PRODUCT.md](02-PRODUCT.md), nowhere else). Sketch:

```sql
-- COMMITTED ADDITION — Phase 1 migration: saves generalize to watchers. DDL SKETCH ONLY.
-- want_to saves are grandfathered as watchers; 'saves' survives only as DDL history.
CREATE TABLE watchers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  affordance_id uuid REFERENCES affordances(id),  -- a direct watch (the old save), or…
  watchable_id  uuid REFERENCES watchables(id),   -- …an Almanac watch; exactly one is set
  tier          text NOT NULL DEFAULT 'starter',  -- starter|vigilance — the gate is 02's
  last_fired_at timestamptz,                      -- open transitions only ("not an alert firehose")
  last_delivered_at timestamptz,                  -- delivery telemetry (per-fire log omitted here)
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK ((affordance_id IS NULL) <> (watchable_id IS NULL))
);
```

The fire → deliver → respond telemetry this table accumulates is the raw material of watch exhaust, moat M7 ([00-THESIS.md](00-THESIS.md) §3).

### (c) The one real ontology decision: windows without a place

Aurora over the metro, regional smoke, (someday) pollen — real windows with no natural place × activity anchor. It has to be settled here, because every other table hangs off the affordance.

**Committed: region-scoped affordances.** A `places` row of `kind = 'region'` carries metro-scale geometry — for these rows `geom` widens beyond `Point` (concept-level here; the type change ships in the Phase 1 migration) — crossed with a closed-vocabulary activity (`aurora_view`, `smoke_clear`; the ~120-verb vocabulary stays closed and hand-curated). The result is an ordinary affordance row, so claims, verifications, condition windows, and watchers anchor exactly as they always have, and Q1–Q4 run unmodified — zero new machinery. Losing alternative (one line): affordance-less windows — they orphan the claim/verification anchor and fork every canonical query.

---

## 3. The condition-predicate DSL

A `ConditionWindow.predicate` is a JSON expression tree the evaluator cron can execute against `feeds` with zero code changes per binding. Grammar:

```
node  := leaf | {"all": [node,...]} | {"any": [node,...]} | {"not": node}
leaf  := {
  "feed": "<feeds.id>",
  "op": "<" | "<=" | ">" | ">=" | "=" | "between",
  "value": number | [lo, hi],
  "agg": "latest" | "sum" | "min" | "max",   -- default "latest"
  "window_h": integer,                        -- required when agg != latest
  "exit_value": number                        -- optional hysteresis: once true, stays
}                                              -- true until crossing exit_value
```

`agg`+`window_h` compute over `feed_readings` (e.g., a 72-hour precipitation sum). `exit_value` prevents flapping — a swim window shouldn't strobe as the gauge oscillates around its threshold. Rule: on `is_gate` (hazard) windows the band sits on the *safe* side of `value` — `value` is the conservative entry, `exit_value` the earned hard bound — so anti-flap never holds a hazard window open past its limit. Losing alternative: a mini expression *language* string ("flow < 1200 && temp > 75") — parsing and injection surface for zero gain; JSON trees are directly indexable and diffable.

**Real examples from the Portland polygon:**

**(a) High Rocks wild-swim — hydrological.** Clackamas River gauge at Estacada, USGS 14210000, discharge parameter 00060; swimmable when flow is low and it's actually hot:

```json
{"all": [
  {"feed": "usgs_nwis:14210000:00060", "op": "<", "value": 1050, "exit_value": 1200},
  {"feed": "open_meteo:45.44,-122.62:air_temp_f", "op": ">", "value": 75}
]}
```

**(b) Tamanawas Falls flowing hard — weather_triggered.** Waterfalls in and near the Gorge photograph best after sustained rain; 72-hour accumulated precipitation at the NWS grid point for the falls:

```json
{"feed": "nws:45.40,-121.57:precip_in", "agg": "sum", "window_h": 72,
 "op": ">=", "value": 1.0}
```

**(c) Haystack Rock tide pools — tidal ∧ astronomical.** Tide pools expose at minus tides, and only daylight ones count. The feed row's `station_ref` holds the nearest NOAA CO-OPS station id (resolved once, at binding time); the predicate references our internal feed id:

```json
{"all": [
  {"feed": "noaa_coops:haystack_rock:tide_pred_ft_mllw", "op": "<=", "value": 0.0},
  {"feed": "astro:45.88,-123.97:is_daylight", "op": "=", "value": 1}
]}
```

**(d) Mt. Hood snowshoe — snow.** Enough settled snow at the Mt. Hood SNOTEL station, the access road not buried in an active dump, and — snow_travel being hazard-class — NWAC avalanche danger at moderate or below:

```json
{"all": [
  {"feed": "snotel:mt_hood:snow_depth_in", "op": ">=", "value": 30},
  {"feed": "nws:45.33,-121.71:precip_in", "agg": "sum", "window_h": 24, "op": "<", "value": 1.5},
  {"feed": "nwac:mt_hood:danger_level", "op": "<=", "value": 2}
]}
```

**(e) The new families are already expressible — committed feeds, zero grammar changes.** A sky-family aurora window (SWPC adapter committed for Phase 1; the family ships Phase 3 per [05-ROADMAP.md](05-ROADMAP.md)) is two ordinary leaves:

```json
{"all": [
  {"feed": "swpc:planetary:kp_index", "op": ">=", "value": 5},
  {"feed": "open_meteo:45.52,-122.68:cloud_cover_pct", "op": "<", "value": 30}
]}
```

And a reservation-family availability window is one: `{"feed": "recgov:232450:site_available", "op": "=", "value": 1}` — the Phase 4 adapter reduces a Recreation.gov availability response to a 0/1 reading (1 = a matching site is open), so an inventory-state change rides the same machinery as a tide. The grammar in this section is frozen; a family is adapters plus bindings, never DSL surgery ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) §1).

The *thresholds* in these predicates are the M1 moat: 1,200 cfs for High Rocks is earned local judgment, recorded as a `hazard_calibration` claim pointing at the window (`claims.window_id`), and tightened by every verification snapshot ("sketchy" verdict at 700 cfs narrows the bound). The forging process is [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)'s bindings program.

---

## 4. Publication gates

1. **Nothing auto-publishes from a single LLM extraction.** Every extracted claim lands at `claims.status = 'review'`; the queue drains to `published` (counts toward confidence and serving) or `suppressed`.
2. **Standard affordances** publish — the transition is `affordances.status → 'published'` — when top-claim effective confidence ≥ 0.45 **and** structurally: ≥ 2 published claims from independent `source_domain`s, **or** ≥ 1 `founder_verified`/`user_reported` support.
3. **Hazard gate** (activities with `hazard_class = true`: cliff_jump, wild_swim, snow_travel): all of the above, **plus** at least one `confirm` verification within the class half-life (60 days, §5), **plus** the affordance's `is_gate` condition window currently `state = true`. If either lapses, the affordance drops from the feed automatically — the query in §7 enforces this; no human has to remember.
4. **Rendering rule:** hazard cards always carry provenance, last-verified date, and assumption-of-risk framing ("verified 6 days ago at 410 cfs"). The gate *is* the trust feature.
5. **Suppression:** `places.sensitive = true` hard-excludes from all serving; parking-full verification spikes downrank via `base_quality` adjustment (the dispersal posture in [02-PRODUCT.md](02-PRODUCT.md) §5).

---

## 5. The confidence model

A claim's served confidence is a probability derived from a log-odds state plus decay:

```
confidence(t) = σ(L) · exp(−λ_class · Δt)      where σ(L) = 1/(1+e^−L),
Δt = now − last_evidence_at,  λ_class = ln 2 / half_life_class
```

Decay multiplies the *probability*, not the log-odds: an unrefreshed claim tends toward "unknown," never toward "false."

**Source-type priors** (initial L = logit(p₀)):

| source_type | p₀ | L₀ |
|---|---|---|
| llm_extracted | 0.35 | −0.62 |
| user_reported | 0.55 | +0.20 |
| sensor_derived | 0.90 | +2.20 |
| founder_verified | 0.95 | +2.94 |

**Corroboration boost:** each additional claim asserting the same affordance from an *independent* `source_domain` adds **+0.5 nats**, capped at +1.5 (three corroborators). Worked: one Reddit extraction σ(−0.62) = 0.35 → an independent Oregon Hikers extraction σ(−0.12) = 0.47 → a third domain σ(+0.38) = 0.59. Two independent extractions clear the 0.45 publish bar; one never does — the math and the structural gate agree by construction. Losing alternative: full naive-Bayes odds multiplication — it overshoots wildly on correlated sources (Reddit threads quote each other), and a capped additive boost is honest about that correlation.

**Verification updates (Bayesian, in log-odds):** treat a verdict as a noisy test of the claim with sensitivity 0.90 (P(confirm | claim true)) and specificity 0.80 (P(refute | claim false)):

```
confirm:  L += ln(0.90/0.20) = +1.50        refute:  L += ln(0.10/0.80) = −2.08
changed:  claim marked superseded_by → new user_reported claim spawned
```

A `power_verifier` verdict is weighted ×1.25; the founder is verifier #1 and carries the flag from day one. Any confirming evidence resets `last_evidence_at` — verification refreshes the decay clock, which is why one Sunday tap is worth more than ten stale sources. Example lifecycle: High Rocks swim claim at L = −0.12 (two sources, 0.47); founder confirms in the field → L = −0.12 + 1.25×1.50 = +1.76, confidence 0.85, clock reset; an unweighted refute after a flood-shifted channel → L = −0.32, back below the bar, pulled from serving until re-verified.

**Per-class decay half-lives (hand-set launch priors):**

| claim_class | example | half-life |
|---|---|---|
| geomorphic | "the waterfall exists" | 10 years |
| seasonal_bio | "balsamroot peaks late April here" | 2 years |
| access | "rope swing intact / gate open / log crossing in" | 180 days |
| hazard_calibration | "swim-safe under 1,200 cfs" | 60 days |

**Learning λ from the log (this is moat M3):** every (confirm at t₀ → refute at t₁) pair on the same claim is a labeled decay event. For each class, treat refutation as the failure event in an exponential survival model; the MLE is simply

```
λ̂_class = (# refute events) / (Σ days of exposure between confirming and terminal evidence)
```

Recomputed quarterly per class once a class has ≥ 50 refute events; later stratified by class × terrain (coastal access claims rot faster than Gorge ones). Nobody without the outcome labels can run this fit — a competitor cloning the claims inherits our priors and none of our calibration, and miscalibration is felt directly as product failure (a family sent to a washed-out swimming hole).

---

## 6. Worked examples

Three complete chains, place → affordance → condition window → claim → verification. Values are illustrative product records over real places, using the project's canonical gauge and API identities ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)); readable ids ('p-highrocks') stand in for the uuids the DDL generates.

**Example 1 — High Rocks, Clackamas River (wild-swim, hazard class).**

```sql
INSERT INTO places (id, name, kind, geom, osm_id) VALUES
 ('p-highrocks', 'High Rocks', 'swim_hole',
  ST_SetSRID(ST_MakePoint(-122.62, 45.44), 4326), 123456789);

INSERT INTO access_points (place_id, kind, geom, notes) VALUES
 ('p-highrocks', 'parking', ST_SetSRID(ST_MakePoint(-122.618, 45.441), 4326),
  'Cross park lot; fills by 11am on hot July weekends');

INSERT INTO affordances (id, place_id, activity_id, difficulty, typical_duration,
                          dog_ok, kid_ok, base_quality, status) VALUES
 ('a-hr-swim', 'p-highrocks', 'wild_swim', 3, '2 hours', true, false, 0.8, 'published');

INSERT INTO condition_windows (id, affordance_id, wtype, predicate, multiplier, is_gate) VALUES
 ('cw-hr-flow', 'a-hr-swim', 'hydrological',
  '{"all":[{"feed":"usgs_nwis:14210000:00060","op":"<","value":1050,"exit_value":1200},
           {"feed":"open_meteo:45.44,-122.62:air_temp_f","op":">","value":75}]}',
  2.0, true);   -- is_gate: hazard affordance invisible unless satisfied

INSERT INTO claims (id, affordance_id, window_id, cclass, stype, source_url, source_domain,
                    quote_internal, observed_date, extractor_ver, self_conf, log_odds, status) VALUES
 ('c-hr-1', 'a-hr-swim', 'cw-hr-flow', 'hazard_calibration', 'llm_extracted',
  'https://reddit.com/r/Portland/comments/...', 'reddit.com',
  '[internal evidence quote, never republished]', '2025-07-19',
  'haiku-batch-v3', 0.72, -0.12, 'published');   -- -0.12 = prior -0.62 + one corroborator +0.5

INSERT INTO verifications (claim_id, user_id, verdict, conditions_snapshot) VALUES
 ('c-hr-1', 'u-founder', 'confirm',
  '{"usgs_nwis:14210000:00060": 410, "open_meteo:45.44,-122.62:air_temp_f": 84,
    "date": "2026-07-01"}');
-- update applied: L = -0.12 + 1.25×1.50 = +1.76 (power verifier); confidence 0.85; clock reset
```

The snapshot ("confirmed swimmable at 410 cfs") is a calibration point: verifications at 400–700 cfs confirming, plus any "sketchy" refute near 1,100, let the threshold tighten from folklore to a fitted bound.

**Example 2 — Tamanawas Falls (waterfall-view, weather-triggered, standard class).**

```sql
INSERT INTO places (id, name, kind, geom, gnis_id) VALUES
 ('p-tamanawas', 'Tamanawas Falls', 'waterfall',
  ST_SetSRID(ST_MakePoint(-121.57, 45.40), 4326), 'gnis:...');

INSERT INTO affordances (id, place_id, activity_id, difficulty, typical_duration,
                          dog_ok, kid_ok, base_quality, status) VALUES
 ('a-tf-wf', 'p-tamanawas', 'waterfall_view', 2, '3 hours', true, true, 0.7, 'published');

INSERT INTO condition_windows (id, affordance_id, wtype, predicate, multiplier, is_gate) VALUES
 ('cw-tf-rain', 'a-tf-wf', 'weather_triggered',
  '{"feed":"nws:45.40,-121.57:precip_in","agg":"sum","window_h":72,"op":">=","value":1.0}',
  1.8, false);  -- not a gate: falls are viewable anytime, GREAT after rain

INSERT INTO claims (id, affordance_id, cclass, stype, source_domain, observed_date,
                    extractor_ver, log_odds, status) VALUES
 ('c-tf-1', 'a-tf-wf', 'seasonal_bio', 'llm_extracted', 'oregonhikers.org',
  '2024-11-02', 'haiku-batch-v3', -0.12, 'published');  -- corroborated by a reddit.com claim (not shown)
```

When the window opens, the feed card renders its provenance line exactly as this binding generates it — satisfied leaf plus live reading: *"Tamanawas Falls flowing hard: 1.6 in rain in 72 h"* (card copy always prints the leaf's `window_h`; nothing is hand-written).

**Example 3 — Haystack Rock tide pools (tidepool, standard class, tidal window).**

```sql
INSERT INTO places (id, name, kind, geom, gnis_id) VALUES
 ('p-haystack', 'Haystack Rock', 'tidepool_area',
  ST_SetSRID(ST_MakePoint(-123.97, 45.88), 4326), 'gnis:...');

INSERT INTO affordances (id, place_id, activity_id, difficulty, typical_duration,
                          dog_ok, kid_ok, base_quality, status) VALUES
 ('a-hs-tp', 'p-haystack', 'tidepool', 1, '90 minutes', true, true, 0.9, 'published');

INSERT INTO condition_windows (id, affordance_id, wtype, predicate, multiplier) VALUES
 ('cw-hs-tide', 'a-hs-tp', 'tidal',
  '{"all":[{"feed":"noaa_coops:haystack_rock:tide_pred_ft_mllw","op":"<=","value":0.0},
           {"feed":"astro:45.88,-123.97:is_daylight","op":"=","value":1}]}', 2.2);

INSERT INTO claims (id, affordance_id, cclass, stype, source_domain, observed_date,
                    extractor_ver, log_odds, status) VALUES
 ('c-hs-1', 'a-hs-tp', 'geomorphic', 'llm_extracted', 'reddit.com',
  '2025-06-10', 'haiku-batch-v3', -0.12, 'published');  -- corroborated (second domain not shown)

INSERT INTO verifications (claim_id, user_id, verdict, conditions_snapshot) VALUES
 ('c-hs-1', 'u-powerverifier-3', 'confirm',
  '{"noaa_coops:haystack_rock:tide_pred_ft_mllw": -1.2,
    "date": "2026-06-14", "time_local": "07:40"}');
```

Tidal windows are *forecastable* — CO-OPS predictions extend months out — so this affordance can appear in Thursday's feed with "minus tide Saturday 7:12 am," which no reactive weather binding can do.

---

## 7. Canonical queries

**Q1 — `good_now` materialization** (the "one script that makes the product temporal," see [04-ARCHITECTURE.md](04-ARCHITECTURE.md)). Per-feed fetch cadence ranges 15 min–6 h ([04-ARCHITECTURE.md](04-ARCHITECTURE.md)'s adapter table governs), and a 30-minute evaluation/materialization sweep re-evaluates predicates and rewrites `good_now`. After re-evaluating each `condition_windows.predicate` against `feeds`/`feed_readings` in application code (the JSON tree walker), updating `state`, and appending a `condition_states` history row:

```sql
INSERT INTO good_now (affordance_id, now_score, reasons, computed_at)
SELECT a.id,
       a.base_quality
         * COALESCE(EXP(SUM(LN(cw.multiplier)) FILTER (WHERE cw.state)), 1.0)
         * COALESCE(top_claim.conf, 0.0) AS now_score,  -- claimless edge (mid-supersession): floor, never NULL-abort
       COALESCE(jsonb_agg(jsonb_build_object('window_id', cw.id, 'wtype', cw.wtype))
                FILTER (WHERE cw.state), '[]') AS reasons,
       now()
FROM affordances a
LEFT JOIN condition_windows cw ON cw.affordance_id = a.id
CROSS JOIN LATERAL (          -- decay applied at read: confidence(t) = σ(L)·exp(−λΔt)
  SELECT MAX( (1/(1+EXP(-c.log_odds)))
            * EXP(-(LN(2)/hl.days) * EXTRACT(epoch FROM now()-c.last_evidence_at)/86400)
        ) AS conf
  FROM claims c
  JOIN (VALUES ('geomorphic',3650),('seasonal_bio',730),
               ('access',180),('hazard_calibration',60)) hl(cclass, days)
    ON hl.cclass = c.cclass::text
  WHERE c.affordance_id = a.id AND c.superseded_by IS NULL AND c.status = 'published'
) top_claim
WHERE a.status = 'published'
  AND NOT EXISTS (SELECT 1 FROM places p WHERE p.id = a.place_id AND p.sensitive)
  AND NOT EXISTS ( -- hazard gate: gated window must be live
      SELECT 1 FROM condition_windows g
      WHERE g.affordance_id = a.id AND g.is_gate AND g.state IS DISTINCT FROM true)
  AND ( -- hazard gate: recent confirm within class half-life
      NOT EXISTS (SELECT 1 FROM activities act
                  WHERE act.id = a.activity_id AND act.hazard_class)
      OR EXISTS (SELECT 1 FROM verifications v JOIN claims c2 ON c2.id = v.claim_id
                 WHERE c2.affordance_id = a.id AND v.verdict = 'confirm'
                   AND v.verified_at > now() - interval '60 days'))
GROUP BY a.id, a.base_quality, top_claim.conf
ON CONFLICT (affordance_id) DO UPDATE
  SET now_score = EXCLUDED.now_score, reasons = EXCLUDED.reasons,
      computed_at = EXCLUDED.computed_at;
```

Decision: `now_score` is three-factor — base quality × active condition multipliers × decayed top-claim confidence — so an unverified affordance can't outrank a verified one; [02-PRODUCT.md](02-PRODUCT.md) inherits this definition.

**Q2 — the Thursday feed** (per user; the 90-minute polygon approximated as 130 km geodesic at MVP — true isochrones are an [04-ARCHITECTURE.md](04-ARCHITECTURE.md) upgrade):

```sql
SELECT p.name, act.display_name, gn.now_score, gn.reasons,
       ST_Distance(p.geom::geography, u.home_geom::geography)/1000 AS km
FROM good_now gn
JOIN affordances a ON a.id = gn.affordance_id
JOIN places p      ON p.id = a.place_id
JOIN activities act ON act.id = a.activity_id
JOIN users u       ON u.id = $1
WHERE ST_DWithin(p.geom::geography, u.home_geom::geography, 130000)
ORDER BY gn.now_score DESC
LIMIT 20;   -- every returned row also inserts a feed_events 'impression' with snapshot
```

**Q3 — the watcher query** (saves already ARE standing queries; run after each evaluator pass, it catches windows that have *opened* since the watcher last fired). This is the paid product's core query: every Vigilance push is one row of this result set, delivered ([02-PRODUCT.md](02-PRODUCT.md)). After the Phase 1 migration (§2a) the FROM clause reads `watchers`, the `want_to` filter becomes the tier gate, and `last_alerted_at` becomes `last_fired_at` — the shape below does not change:

```sql
SELECT s.user_id, p.name, cw.wtype, cw.state_since
FROM saves s
JOIN condition_windows cw ON cw.affordance_id = s.affordance_id
JOIN affordances a ON a.id = s.affordance_id
JOIN places p ON p.id = a.place_id
WHERE s.kind = 'want_to'
  AND cw.state = true
  AND cw.state_since > COALESCE(s.last_alerted_at, s.created_at)
  AND a.status = 'published';
-- → 'Dog Mountain balsamroot peaking — you've been watching since January'
```

**Q4 — constraint search** ("dog-friendly wild-swim within 90 minutes, uncrowded, good now" — at launch the feed IS the query; this is the same machinery with WHERE clauses, which is the point):

```sql
SELECT p.name, gn.now_score, gn.reasons
FROM good_now gn
JOIN affordances a ON a.id = gn.affordance_id AND a.status = 'published'
JOIN places p ON p.id = a.place_id
WHERE a.activity_id = 'wild_swim'
  AND a.dog_ok
  AND ST_DWithin(p.geom::geography, $user_point::geography, 130000)
  AND NOT EXISTS (      -- crowd proxy: recent parking-full refutes on access claims
      SELECT 1 FROM claims c JOIN verifications v ON v.claim_id = c.id
      WHERE c.affordance_id = a.id AND c.cclass = 'access'
        AND v.verdict = 'refute' AND v.verified_at > now() - interval '14 days')
ORDER BY gn.now_score DESC LIMIT 10;
```

Later NL search compiles to exactly this shape — pgvector maps free text onto `activities` and filter predicates; the graph, not the model, answers the question. That, and the MCP `search_experiences`/`get_conditions` tools six months post-launch, are [04-ARCHITECTURE.md](04-ARCHITECTURE.md)'s and [06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)'s to detail; this schema is the contract they build on.
