# Place

Place is the **WHEN engine** — a perishable-decision-window company. Every incumbent answers
*where*: find the place, get to the place, book the place. Place answers **when**. Its primary
object is the **window** — the minus tide that exposes the Haystack pools, the first larch
weekend, the campsite cancellation at a full campground, the first smoke-free morning — each
bound to an executable condition predicate over free public sensor feeds (USGS streamflow,
NOAA tides, space weather, Recreation.gov availability, AirNow) with **verified local
thresholds** that appear in no corpus. Users browse the **Almanac** — the per-metro catalog
of watchable moments — tap **Watch**, and a watcher (a standing query, re-evaluated on every
sweep) pushes the moment the window opens. Outdoors is window family #1 of six, and the
everyday screen it powers is still the one no incumbent can render:
**"What's good right now, near you."**

## Start here

The strategy and development canon lives in [docs/](docs/) — docs/00 through docs/10 — read
[docs/00-THESIS.md](docs/00-THESIS.md) first. The canon commits the decisions (thesis, graph
ontology, product loop, data strategy, architecture, roadmap, competitive position, the
window-family doctrine, the Almanac, Groundwire); new work should extend them, not re-derive
them.

## Current state of the code

[backend/](backend/) implements the architecture in
[docs/04-ARCHITECTURE.md](docs/04-ARCHITECTURE.md) through the temporal-feed milestone (PR-1
to PR-7 of its migration sequence): Postgres 16 + PostGIS + pgvector, the full experience-graph
schema, the condition evaluator with live adapters (USGS NWIS, Open-Meteo/NWS, NOAA CO-OPS,
SNOTEL, NWAC, AirNow, sun/moon), Overpass/GNIS/RIDB/USFS ingestion, the launch bindings, the
FastAPI surface (feed, places, saves, trips, verdicts, magic-link auth, admin review queue),
and the key-gated extraction pipeline. The original Mongo seed (`src/`) is replaced.

```bash
make db-up      # Postgres (PostGIS + pgvector) via docker compose, port 5433
make migrate    # Alembic baseline
make seed       # Overpass + GNIS skeleton places (keyless, live APIs)
cd backend && .venv/bin/python -m place.ingest.cli bindings   # launch bindings
make evaluate   # one live evaluator sweep -> good_now
make api        # FastAPI on :8000  ->  GET /feed?lat=45.512&lng=-122.658
make test       # pytest (unit + integration; live tests: pytest -m live)
```

Runs end to end with **zero credentials** — every live feed is a free public API. Optional
keys (Anthropic extraction, Reddit corpus, RIDB, AirNow, Resend email, Sentry) are documented
in [.env.example](.env.example); copy it to `.env` and fill what you need.
