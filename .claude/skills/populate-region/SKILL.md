---
name: populate-region
description: Explore and populate the next priority region's places, affordances, and claims into the review queue
---

# Populate the next priority region

Recurring, founder-deployable run: pick the next region from the founder's
priority list, ingest its public-source skeleton, web-research its
condition-dependent experiences, and land everything in the **review queue**
for the founder to triage at `/admin/review-queue`. This is the "initial 10%
contribution" pass — the goal is that the app is usable for one person in
that region, not that the region is finished.

An optional argument is a region slug (e.g. `/populate-region gorge-west`);
without one, work whatever `coverage` marks NEXT.

## Hard guardrails (read before doing anything)

- **NEVER publish anything.** No `status='published'` on any row, ever. The
  publication gates (≥2 independent sources or founder/user verification —
  docs/00-THESIS.md §7 "Claim", DB trigger in alembic 0001) are canon and
  founder-operated. Your entire output is `status='review'`.
- **NEVER edit `backend/data/regions/priority.yaml` order or targets** — the
  list is founder-owned. Adding nothing, reordering nothing.
- **NEVER touch hazard-class gating** (activities.yaml `hazard_class` flags,
  gate predicates, the trigger). Hazard affordances degrade DOWN only.
- **NEVER invent coordinates.** Every proposal's lat/lng comes from a source
  you actually read or from a place row the ingest already created —
  cross-check names against ingested places before writing coordinates.
- **Keep the run ≤ ~30 minutes of work.** Depth over breadth: 15-40 strong
  proposals beat 100 thin ones (docs/03 §6 step 8).
- **Always end with the coverage table.**

## Steps

### a. Preflight

```bash
docker compose up -d          # from repo root; postgres lands on localhost:5433
cd backend && .venv/bin/alembic upgrade head
```

If `backend/.venv` is missing: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

### b. Pick the region

```bash
cd backend && .venv/bin/python -m place.ingest.cli coverage
```

Work the region marked `NEXT` (first in founder priority order below target:
default 150 places / 30 affordances of any status), unless a slug was passed
as the skill argument.

### c. Skeleton ingest

```bash
.venv/bin/python -m place.ingest.cli region --slug <slug>
```

This runs Overpass bbox-scoped to the region's 20-mile circle, then
gnis/ridb/usfs as-is (launch-polygon-wide, idempotent; RIDB skips without
`RIDB_API_KEY`), then bindings. Safe to re-run.

### d. EXPLORE — web research into a proposals YAML

Research the region for **condition-dependent outdoor experiences**: swim
holes, waterfalls, viewpoints, tidepools, larch/wildflower spots, paddle
put-ins. Prioritize the oregonhikers.org field guide and official sources
(state parks, USFS, ODFW, NOAA); Reddit trip reports are good corroboration.
For each candidate collect: a real source URL you actually loaded, the date
the experience *happened* (not the posting date; null when undatable), and
coordinates cross-checked against the just-ingested places
(`SELECT name, ST_Y(geom), ST_X(geom) FROM places WHERE name ILIKE '%...%'`).

Write the **15-40 BEST candidates** — depth over breadth — to a YAML file
(e.g. `backend/data/regions/proposals-<slug>-<date>.yaml`, gitignored-safe
anywhere) with this schema:

```yaml
proposals:
  - place:
      name: Punch Bowl Falls        # as sources name it
      lat: 45.6265                  # from a source or an ingested place row
      lng: -121.8935
      kind: waterfall               # waterfall | swim_hole | viewpoint | trailhead | ...
    activity_id: wild_swim          # MUST exist in backend/data/activities.yaml
    claim:
      text: "Deep pool below the falls; locals swim it July-September."
      source_url: "https://www.oregonhikers.org/field_guide/Punch_Bowl_Falls"
      source_type: llm_extracted    # or user_reported; nothing else is accepted
      observed_date: 2025-08-10     # when it HAPPENED; null if undatable
      class: geomorphic             # optional: geomorphic | seasonal_bio | access | hazard_calibration
    dog_ok: true                    # optional
    kid_ok: true                    # optional
```

Unknown `activity_id`s are rejected (closed vocabulary); `founder_verified`
and `sensor_derived` source types are rejected (earned, never proposed).

### e. Load, verify, report

```bash
.venv/bin/python -m place.ingest.cli proposals --file <yaml>
.venv/bin/python -m place.ingest.cli coverage
```

The loader is idempotent (same affordance + source_url = skipped), matches
places within 500 m by name similarity, and writes everything at
`status='review'`.

Report back:
1. What was added (the proposals summary line: created/matched/skipped).
2. That the founder should triage the new rows at `/admin/review-queue`.
3. Which region is NEXT after this run (from the final coverage table).
4. If `DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY` is set, note that the
   extraction worker (`backend/place/extract/worker.py`) can densify claims
   from the cached corpus — **suggest it, do not run it unless asked**.
5. The final coverage table, verbatim.
