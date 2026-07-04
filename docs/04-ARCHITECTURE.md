# Technical Architecture — From main.py to the Graph

**In one breath**
We replace Mongo with Postgres 16 + PostGIS + pgvector in the same docker-compose file (no data migration — there is no data), keep FastAPI and evolve `src/main.py` into the graph API, and build one wedge component that makes the product temporal: a condition-evaluator cron that re-checks every ConditionWindow predicate against USGS NWIS, NOAA CO-OPS, SNOTEL, NWS/Open-Meteo, NWAC, AirNow, and sun/moon feeds, materializing a `good_now` table the feed reads. Frontend is a Next.js PWA with web push; auth is magic-link; an MCP server exposing `search_experiences`/`get_conditions` ships within six months of launch. The whole thing runs on one $10–20 VPS under $50/month, built by one person with AI assistance, in PR-sized steps that never break the running system.

Ontology and DDL live in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); the extraction pipeline in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); the surfaces this serves in [02-PRODUCT.md](02-PRODUCT.md); the sequence's calendar in [05-ROADMAP.md](05-ROADMAP.md).

---

## 1. Where we are (honest, no shame)

`src/main.py` is ~140 lines: a FastAPI app talking to a local MongoDB (pymongo, connection string `mongodb://root:example@localhost:27017` hardcoded at line 15) with two collections:

- **`locations`** — `{_id, name, lat, lng, category}`. Created via `POST /locations/`, queried via `POST /locations/get/` with case-insensitive regex on name/category and a hand-rolled radius filter: convert `radius_km` to degree deltas (`radius_km / 111` for latitude, cosine-corrected for longitude) and range-query `lat`/`lng`. It's a bounding box pretending to be a circle, with no geo index behind it — a full collection scan per search.
- **`reviews`** — `{_id, location_id, rating 0–5, content}`. `POST /reviews/` and `GET /reviews/{location_id}`, with a manual `_id` serializer for BSON.

`src/docker-compose.yml` is a single Mongo container with `root`/`example` credentials. There is no auth, no test, no frontend in the repo, and no geospatial index. Two things in this seed are actually load-bearing: **FastAPI was the right call** (it stays and grows), and **CORS is already opened to `localhost:3000`** — the file was waiting for the Next.js frontend before we knew it. Everything else is scaffolding to be replaced, which is exactly what a first commit should be.

## 2. The storage decision

**Postgres 16 + PostGIS + pgvector. Committed.**

The product is joins: affordance × condition window × live feed reading × verification history, ranked by distance from the user. That is a relational workload with a geospatial accent. PostGIS gives us `ST_DWithin` on a GiST index — a correct, indexed replacement for main.py's cosine arithmetic in one line. Recursive CTEs cover every graph traversal the ontology in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) needs (Place→Affordance→ConditionWindow→Claim→Verification is 3–4 joins, not a graph-database problem). pgvector serves entity resolution during extraction now and NL search later, in the same database, in the same transaction.

- **Mongo lost:** the schema is relational (claims reference affordances reference places), Mongo has no story for the join-heavy `now_score` query, and "minimal migration" preserves nothing — there are ~140 lines of code and zero production rows.
- **Neo4j lost:** real operational overhead on a solo $50/month budget, weak geospatial support, and a second datastore for traversals Postgres CTEs handle fine at this scale.

**There is no data migration.** No users, no production rows. The "migration" is: swap the `mongo` service for `postgis/postgis:16-3.4` in docker-compose, add an Alembic baseline with the DDL from [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md), and delete the pymongo import. Tables: `places`, `access_points`, `activities`, `affordances`, `condition_windows`, `claims`, `verifications`, `users`, plus `saves`, `trips`, `feed_events`, and the materialized `good_now`.

## 3. System diagram

```
                    ┌──────────────────────────── one VPS, docker compose ───────────────────────────┐
                    │                                                                                 │
  USGS NWIS ─┐      │  ┌──────────────────────┐         ┌─────────────────────────────────┐          │
  NOAA CO-OPS ┤     │  │  condition evaluator │ writes  │        Postgres 16              │          │
  SNOTEL ─────┼────►│  │  (cron, every 15 min │────────►│  PostGIS + pgvector             │          │
  NWS/OpenMet ┤     │  │   to 6 h per feed)   │         │  places · affordances ·         │          │
  NWAC ───────┤     │  └──────────────────────┘         │  condition_windows · claims ·   │          │
  AirNow ─────┤     │                                   │  verifications · good_now (tbl) │          │
  sun/moon ───┘     │  ┌──────────────────────┐ writes  │  feed_events · users · saves    │          │
                    │  │  extraction workers  │────────►│                                 │          │
  Reddit API ─┐     │  │  (batch, offline)    │  claims └───────────────┬─────────────────┘          │
  OregonHikers┼────►│  │  → review queue      │  (pending)              │ reads/writes               │
  corpus cache┘     │  └──────────────────────┘         ┌───────────────▼─────────────────┐          │
                    │                                   │   FastAPI API (from main.py)    │          │
                    │  ┌──────────────────────┐  calls  │   REST + magic-link auth +      │          │
  Claude / other ──►│  │      MCP server      │────────►│   web-push sender               │          │
  LLM clients       │  │ search_experiences · │         └───────────────┬─────────────────┘          │
                    │  │ get_conditions       │                         │ JSON                       │
                    │  └──────────────────────┘                         │                            │
                    └───────────────────────────────────────────────────┼────────────────────────────┘
                                                                        ▼
                                                        Next.js PWA (feed · place pages ·
                                                        saves · Sunday push via Web Push)
```

**FastAPI API.** The direct descendant of `src/main.py`. Serves the four MVP surfaces from [02-PRODUCT.md](02-PRODUCT.md), owns magic-link auth, sends web push, and logs every recommendation→outcome event (`shown`, `saved`, `went`, `verified`) into `feed_events` — the calibration training data from user #1. asyncpg + SQLAlchemy Core; Pydantic models evolve from the ones already in main.py.

**Postgres.** The graph, the event log, and the materialized `good_now` index in one instance. Nightly `pg_dump` to object storage is the entire disaster-recovery plan at this scale.

**Condition evaluator (cron).** The wedge component — detailed in §4. Reads feeds, evaluates every ConditionWindow predicate, refreshes `good_now`.

**Extraction workers.** Offline batch jobs (Claude batch API, ≤$200 one-time per [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)) that turn the cached ~150k-doc corpus into pending claims with `status='review'` (the `pub_status` enum in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)). Nothing auto-publishes: a claim reaches `published` only through the review queue (a founder-facing admin page) or the ≥2-independent-sources gate. Workers run on the same VPS at night; they are not latency-sensitive.

**Next.js PWA + web push.** No native app. Service worker gives installability, offline shell, and Web Push (VAPID) on Android and iOS ≥16.4 — enough for the one Sunday 6 pm notification the loop depends on.

**MCP server.** A thin process exposing `search_experiences` and `get_conditions` over the same query layer the feed uses, shipped within six months of launch. Perishability is the API leverage: callers must keep calling because last month's copy is worthless. The freshest tier stays gated with attribution and rate terms.

## 4. The condition evaluator, in detail

This is the component that makes Place temporal instead of static; it deserves the most careful engineering in the repo.

**Shape:** one Python module (`evaluator/`) run by system cron on the VPS. No Celery, no queue — a lockfile-guarded script is the right amount of infrastructure for one machine. Losing alternative: a long-running scheduler daemon — more to keep alive, nothing gained at this cadence.

**Cadence (per feed, not global):**

| Feed | Adapter target | Cadence | Notes |
|---|---|---|---|
| USGS NWIS | instantaneous values (e.g., gauges 14210000 Clackamas @ Estacada, 14137000 Sandy @ Bull Run), discharge + water temp | 15 min | Backbone of the 40 swim-hole bindings |
| NWS / Open-Meteo | point forecast + 72-h observed precipitation per place centroid | 1 h | Drives the 60 Gorge waterfall bindings |
| NOAA CO-OPS | tide predictions per station | 6 h (predictions are stable) | Minus-tide windows for Haystack Rock tidepooling |
| SNOTEL | snow-water equivalent, snow depth | 6 h | Snowshoe/larch-season gating on Hood |
| NWAC | avalanche danger rating by zone | 6 h in season | Hard-gate input: feeds snow-travel `is_gate` windows (rule 3 below; rating cutoffs are bindings per [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) |
| AirNow | AQI per reporting area | 1 h | Smoke-season suppression of everything outdoor |
| Sun/moon | computed locally (astral lib) | daily precompute | Sunrise/sunset/golden hour/moon phase — no network dependency |

Per-feed fetch cadence ranges 15 min–6 h (the adapter table above governs), and a 30-minute evaluation/materialization sweep re-evaluates predicates and rewrites `good_now` — the same cadence contract stated in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §7.

**Per run:** each adapter fetches raw readings into a `feed_readings` table (feed, station_id, metric, value, observed_at, fetched_at — kept forever, partitioned monthly; the retention decision is owned by [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md), and this history is itself moat material for learning thresholds). Then the evaluator loads every published ConditionWindow, evaluates its predicate (the DSL from [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) — typed comparisons over named feed metrics, e.g. `nwis:14210000:discharge < 1200 AND openmeteo:point:temp_f > 75`) against the latest readings, and writes the result to `condition_states` (window_id, satisfied bool, evaluated_at, inputs jsonb — the exact readings used, so every recommendation served can log its conditions snapshot per the safety requirements in [02-PRODUCT.md](02-PRODUCT.md) §5).

**`now_score` computation:** after evaluation, the evaluator rewrites the `good_now` table (the upsert in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §7 Q1), which computes per affordance: `now_score = base_quality × Π(active condition multipliers) × decayed top-claim confidence` (the three-factor definition and decay math in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)), where each satisfied window contributes its multiplier (a freshly-fired `weather_triggered` window like "72-h precip > 1.5 in" boosts a waterfall hard; an unsatisfied `hydrological` window on a hazard-class swim affordance zeroes it, and so does the absence of a confirming verification within the claim class's decay horizon ([01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) — both hazard gates are multiplicative kill switches, not penalties). The feed endpoint is then a single indexed read: `good_now` join `places` with `ST_DWithin`, ordered by `now_score`. The feed never computes conditions at request time.

**Failure handling — the non-negotiable rules:**
1. **Never show stale as fresh.** Every `condition_states` row carries `evaluated_at` and the reading's `observed_at`. If a feed's latest reading is older than 2× its cadence, its windows flip to `state='unknown'`, and any card still shown says "as of \<time\>" — never an implicitly-current claim.
2. **Degrade to seasonal priors, not to silence.** Every affordance carries a `seasonal` ConditionWindow (month-range prior) alongside its live windows. When USGS is down, High Rocks doesn't vanish from a July feed — it falls back to its seasonal prior score, loses its live-reason provenance line, and is marked "live flow unavailable." The feed-quality gate (≥60% of cards with a live reason) is measured against this honestly.
3. **Hazard-class affordances degrade DOWN only.** A cliff-jump or wild-swim card requires a recent verification AND a currently-satisfied live trigger (a `CONFIRMS` within the class decay horizon, per the hazard gate in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)); if either prong lapses or its feed is down, it is suppressed, never shown on priors alone.
4. **Adapters are isolated.** One adapter throwing does not abort the run; failures log to `feed_health` and three consecutive failures fire an alert (§8).

## 5. API surface

Evolves from main.py's four endpoints. `POST /locations/get/` becomes `GET /feed` and `GET /places/search`; `reviews` are replaced by claims and verifications (a review is prose; a verification is a labeled data point).

| Endpoint | Method | Surface | Purpose |
|---|---|---|---|
| `/feed` | GET | 1 — This Weekend feed | Ranked cards from `good_now` within drive-time of `lat,lng`; each card carries `now_score`, live reason, provenance line, conditions snapshot |
| `/places/{id}` | GET | 2 — Place page | Place + affordances + current condition states + published claims with provenance + last-verified |
| `/places/search` | GET | 2 | `ST_DWithin` + activity filter; replaces the bounding-box hack |
| `/affordances/{id}/claims` | GET | 2 | Claim list with source_type, observed_date, confidence |
| `/saves` | POST/DELETE/GET | 3 — Want-to/been/loved | Saves are standing queries: the evaluator's post-run step matches newly-satisfied windows against saves and enqueues alerts |
| `/trips` | POST | 4 — loop | "I'm going" tap; creates trip intent that Sunday's push resolves |
| `/verdicts` | POST | 4 — Sunday push | One-tap claim verdict `{claim_id, verdict: confirm\|refute\|changed}` (the `verdict_type` enum in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)); server auto-attaches the conditions snapshot from `condition_states` at trip time — never ask users to describe weather |
| `/auth/magic-link`, `/auth/verify` | POST | all | Magic-link auth (§7) |
| `/push/subscribe` | POST | 4 | Store Web Push subscription (VAPID) |
| `/events` | POST | telemetry | `shown/saved/went/verified` — ranking exhaust from user #1 |
| `/admin/review-queue` | GET/POST | founder | Approve/reject/edit pending extracted claims |
| **MCP: `search_experiences`** | tool | month ≤6 | Same query as `/feed`, structured params (activity, drive-time, dog-friendly), attribution required |
| **MCP: `get_conditions`** | tool | month ≤6 | Live condition state + provenance for a named place — the "is Punch Bowl swimmable today?" answer no generic LLM can retrieve |

Every claim rendered by any endpoint includes its one-tap confirm/refute/changed control (the `/verdicts` enum) — the verification surface is ambient, not a separate feature.

## 6. Migration sequence — PR-sized, always working

Each step is one reviewable PR; the system runs after every merge. Dates align with [05-ROADMAP.md](05-ROADMAP.md) toward the swim tool's hard date (3 weeks before July 4 — for the 2027 season, given today is 2026-07-03 and the stack must exist first; interim seasonal tools per roadmap).

1. **PR-1: Postgres in compose.** Swap `mongo` → `postgis/postgis:16-3.4` in docker-compose; compose credentials to a `.env` (main.py's hardcoded connection string dies with pymongo in PR-2); add Alembic + empty baseline. main.py untouched and still runnable against nothing — the app boots.
2. **PR-2: Core DDL + port existing endpoints.** Migration for `places`, `activities`, `affordances` (DDL from [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)); re-implement `POST /locations/` and search as `/places` + `/places/search` on `ST_DWithin`; delete pymongo. First pytest suite: geosearch correctness (the case the cosine hack got wrong: search radius crossing a longitude band).
3. **PR-3: Seed the skeleton.** Overpass/GNIS/RIDB loaders → ~1,200 canonical places with crosswalk IDs (per [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)). Idempotent, re-runnable.
4. **PR-4: Condition windows + evaluator v1.** `condition_windows`, `feed_readings`, `condition_states` tables; NWIS + Open-Meteo adapters only; cron entry; the first ~10 hand-forged bindings (Clackamas 14210000 swim holes). `good_now` table + `GET /feed`. **The product is now temporal.** This PR is the wedge.
5. **PR-5: Claims + review queue.** `claims`, `verifications` tables; extraction worker consuming the cached corpus via Claude batch API; `/admin/review-queue`. Publication gates enforced in the DB (a `published` claim requires ≥2 sources or a founder/user verification — as a CHECK-adjacent trigger, not app-layer honor code).
6. **PR-6: Remaining adapters.** CO-OPS, SNOTEL, NWAC, AirNow, sun/moon; per-feed cadence config; `feed_health` + degradation rules from §4.
7. **PR-7: Auth + users + saves.** Magic link, `users`, `saves`, saved-query alert matching.
8. **PR-8: PWA.** Next.js app (the CORS config has been waiting since commit `c0cd32c`): feed, place pages, save taps. Deployed behind Caddy on the same VPS.
9. **PR-9: Push + verdicts.** Web Push subscribe, Sunday 6 pm cron composing the capped two-question verdict push, `/verdicts` with auto-snapshot.
10. **PR-10: Events + Plausible.** `feed_events` logging, Plausible script, the moat-metric query (% of served claims backed by in-product ground truth) as a saved dashboard query.
11. **PR-11 (by launch+6 mo): MCP server.** `search_experiences`/`get_conditions` over the existing query layer; API keys + attribution terms.

## 7. Auth and push

**Magic link, no passwords.** `POST /auth/magic-link` emails a 15-minute single-use token (Resend free tier; plain SMTP is the fallback if pricing changes); `POST /auth/verify` exchanges it for a long-lived httpOnly session cookie. A weekly-ritual app cannot afford a password wall in front of a Sunday one-tap verdict; sessions live for months. Losing alternative: OAuth socials — more consent-screen setup than a solo project needs pre-1,000 users, and it leaks nothing we want.

**Web Push on the PWA.** VAPID keypair, `pywebpush` from the API, service-worker handler that deep-links the verdict UI so "Was High Rocks swimmable?" is answerable from the notification in one tap. Hard cap enforced server-side: one push per user per week (Sunday 6 pm local), plus opted-in saved-query alerts. iOS requires the PWA installed to Home Screen (iOS ≥16.4) — the install prompt is therefore part of onboarding, not an afterthought.

## 8. Observability minimums

Solo-operator scale: enough to know the moat is compounding and the feeds are alive, nothing more.

- **Plausible** (self-hosted on the same VPS) for product analytics — cookieless, one script tag.
- **Structured JSON logs** from API and evaluator to journald; `docker compose logs` is the log platform.
- **`feed_health` table + one alert path:** every adapter run writes status/latency/reading-age; a post-run check emails (and pushes to the founder's own device — dogfooding the push stack) on three consecutive failures of any feed or on `good_now` staleness > 2 h.
- **Sentry free tier** for exceptions in API, evaluator, and PWA.
- **Four numbers on the admin page, computed nightly:** weekly-active-planners, verification rate, % of feed cards with a live condition reason (gate: ≥60%), and the moat metric (% of served claims ground-truthed). If a metric isn't one of these or debugging, we don't collect it yet.
- **Backups:** nightly `pg_dump` to Backblaze B2, 30-day retention, restore rehearsed once before launch.

## 9. The <$50/month deployment story

One Hetzner CAX21-class VPS (~$10–20/month) running docker compose: `postgres` (PostGIS+pgvector), `api` (FastAPI), `cron` (evaluator + Sunday push + nightly jobs), `web` (Next.js), `plausible`, `caddy` (TLS, reverse proxy, static). Every data feed — USGS, NOAA, SNOTEL, NWS, NWAC, AirNow, Overpass, GNIS, RIDB — is a free government or open API. Reddit stays within the official free tier pre-revenue. Extraction is ≤$200 one-time plus ~$20/month incremental (batch API, and the cached corpus re-extracts cheaper as models improve — extractor version is stored on every claim for exactly this). Domain + email + B2 backups round to a few dollars. Total steady-state burn: **under $50/month**, with the single largest line item being the LLM incremental — the correct place for the money, because it is the line that buys claims.

No Kubernetes, no managed databases, no queue infrastructure. The day one VPS is not enough is the day the moat metric has already justified the next one.
