# Place

Place is an outdoor **experience discovery** product built on an experience graph: places linked
to activities through verifiable affordances ("you can wild-swim here"), each bound to executable
condition predicates over live public sensor feeds (USGS streamflow, NOAA tides, SNOTEL snowpack,
NWS weather). The product truth it exists to answer: **"What's good right now, near you."**

Every incumbent answers *"I know the place — tell me how to get there."* Place answers
*"I know what I want to do — tell me where, and whether it's good today."*

## Start here

The strategy and development canon lives in [docs/](docs/) — read
[docs/00-THESIS.md](docs/00-THESIS.md) first. The seven documents commit the decisions
(ontology, schema, product loop, data strategy, architecture, roadmap, competitive position);
new work should extend them, not re-derive them.

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
