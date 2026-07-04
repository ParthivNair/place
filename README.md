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

[src/main.py](src/main.py) is the original seed backend: FastAPI + MongoDB with basic
location/review CRUD and a hand-rolled bounding-box search. It predates the docs and is the
starting point of the migration sequence in
[docs/04-ARCHITECTURE.md](docs/04-ARCHITECTURE.md), which replaces it step by step with
Postgres + PostGIS + pgvector, the claims/affordances schema, and the condition-evaluator cron.

```bash
# legacy seed backend (to be migrated per docs/04-ARCHITECTURE.md)
cd src && docker compose up -d   # Mongo
python main.py                   # FastAPI on :8000
```
