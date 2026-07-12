# Place — Development Documents

Written 2026-07-03; re-founded 2026-07-11 around the WHEN-engine thesis. These eleven documents
are the project canon: they commit decisions rather than listing options, and every feature in
them earns its place by feeding the graph, exercising the graph, or defending the graph. When
new work would contradict them, change the document first — deliberately — or follow it.

Read in order the first time; afterwards each stands alone.

| # | Document | What it commits |
|---|----------|-----------------|
| 00 | [Vision & Moat Thesis](00-THESIS.md) | The founding inversion (nobody owns *when*), the window-engine thesis, the ranked moat stack M1–M7, vigilance as the paid unit, perishability as the governing design principle, the five refusals, and the vocabulary every other doc uses. **Start here.** |
| 01 | [The Experience Graph — Ontology & Schema](01-EXPERIENCE-GRAPH.md) | The engineering contract: full ontology, Postgres + PostGIS + pgvector DDL, the condition-predicate DSL, the confidence/decay math, publication and hazard gates, worked examples on real places, the watchables/watchers thin layer, and the canonical queries (`good_now`, feed, the watcher query). |
| 02 | [Product Spec — The Weekly Ritual, the Almanac & the Vigilance Tier](02-PRODUCT.md) | The Thursday/Saturday/Sunday loop, the five surfaces (Good Now feed, the Almanac, the watcher list, place & window pages, the Sunday push), experience-card anatomy, **the canon's only pricing section**, the deferral table, safety/dispersal requirements, and north-star metrics. |
| 03 | [Data Strategy — Seeding, Extraction & Bindings](03-DATA-STRATEGY.md) | The three-layer seed (skeleton/flesh/pulse), the LLM extraction pipeline with cost math, the bindings program (the moat's M1, now the template every window family instantiates), the per-family adapter appendix, catalog curation gates, the verification-overtake plan, source risk and legal posture, and the per-metro replication playbook. |
| 04 | [Technical Architecture — From main.py to the Graph](04-ARCHITECTURE.md) | The honest starting point, the storage decision, the system diagram, the condition evaluator (the wedge component) with failure rules, the API surface, the PR-sized migration sequence, and the <$50/month deployment. |
| 05 | [Roadmap — Seasons, Moat Checkpoints & Gates](05-ROADMAP.md) | **The calendar of record.** Phases keyed to real seasonal windows (October 2026 waterfall tool = public launch #1; the Phase 3 Watcher MVP; the June 2027 swim tool + Vigilance paid launch), a moat checkpoint per phase, go/no-go gates, the transposition rule, and the year-2 horizon. |
| 06 | [Competitive Landscape — Keys, Locks & Bright Lines](06-COMPETITIVE-LANDSCAPE.md) | Per-incumbent analysis (primary-key lock-in; nobody's key is the window), the single-family alert utilities (the willingness-to-pay proof and the bundle fight), the AllTrails-extraction threat and its counter, the generic-LLM/standing-order threat and the tool position (MCP → Groundwire), structural-vs-cosmetic advantages, and how Place dies. |
| 07 | [Users — Personas, Frequency & the Everyday Layer](07-USERS.md) | Evidence-based persona breakdown (P2 named the buyer), the three-beat resolution (everyday retains, magic converts to watchers, watchers monetize), refined ranked user stories including the WHEN-form rows, the pairing-node resolution of "Beer," and the adoption-wave analysis. |
| 08 | [Window Families — The Doctrine & the Admission Test](08-WINDOW-FAMILIES.md) | The one-adapter-class-plus-bindings invariant, the five-gate admission test, per-family specs for all six families (outdoor, sky, harvest, reservation, health, crowd — with crowd and pollen honestly failing gates today), sequencing rationale, and what the doctrine forbids. |
| 09 | [The Watcher Catalog — the Almanac Spec](09-WATCHER-CATALOG.md) | What a watchable is (editorial layer, never new machinery), its anatomy, naming and voice rules, the curation gates (backtest-stated frequencies, the ~70% hit-rate floor), the ~25-watchable Portland launch composition, the tooling gaps, and the Almanac as SEO surface. |
| 10 | [Groundwire — the Freshness-Certificate Endgame](10-GROUNDWIRE.md) | The year-2+ API face: signed expiring freshness certificates over MCP, perishability as the rate card priced by watch exhaust, why it waits for graph density, what it never does, and its honest kill risk. |

Two rules the set lives by:

1. **The moat metric** — the percentage of served claims backed by in-product ground truth — is
   the number the company is graded on, not claim count or user count.
2. **Where documents could disagree on dates, [05-ROADMAP.md](05-ROADMAP.md) wins.**
