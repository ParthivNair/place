# Place — Development Documents

Written 2026-07-03. These seven documents are the project canon: they commit decisions rather
than listing options, and every feature in them earns its place by feeding the graph, exercising
the graph, or defending the graph. When new work would contradict them, change the document first
— deliberately — or follow it.

Read in order the first time; afterwards each stands alone.

| # | Document | What it commits |
|---|----------|-----------------|
| 00 | [Vision & Moat Thesis](00-THESIS.md) | The founding inversion (activity-first), the experience-graph thesis, the ranked moat stack M1–M6, perishability as the governing design principle, what Place is NOT, and the five-term vocabulary every other doc uses. **Start here.** |
| 01 | [The Experience Graph — Ontology & Schema](01-EXPERIENCE-GRAPH.md) | The engineering contract: full ontology, Postgres + PostGIS + pgvector DDL, the condition-predicate DSL, the confidence/decay math, publication and hazard gates, worked examples on real places, and the canonical queries (`good_now`, feed, standing-query alerts). |
| 02 | [Product Spec — The Weekly Ritual & MVP](02-PRODUCT.md) | The Thursday/Saturday/Sunday loop, the four MVP surfaces, the Sunday push mechanics (verification = re-engagement, one notification), experience-card anatomy, the deferral table, safety/dispersal requirements, and north-star metrics. |
| 03 | [Data Strategy — Seeding, Extraction & Bindings](03-DATA-STRATEGY.md) | The three-layer seed (skeleton/flesh/pulse), the LLM extraction pipeline with cost math, the bindings program (the moat's M1), the verification-overtake plan, source risk and legal posture, and the per-metro replication playbook. |
| 04 | [Technical Architecture — From main.py to the Graph](04-ARCHITECTURE.md) | The honest starting point, the storage decision, the system diagram, the condition evaluator (the wedge component) with failure rules, the API surface, the PR-sized migration sequence, and the <$50/month deployment. |
| 05 | [Roadmap — Seasons, Moat Checkpoints & Gates](05-ROADMAP.md) | **The calendar of record.** Phases keyed to real seasonal windows (October 2026 waterfall tool = public launch #1; swim tool June 2027), a moat checkpoint per phase, go/no-go gates, the transposition rule, and the year-2 horizon. |
| 06 | [Competitive Landscape — Keys, Locks & Bright Lines](06-COMPETITIVE-LANDSCAPE.md) | Per-incumbent analysis (primary-key lock-in), the AllTrails-extraction threat and its counter, the generic-LLM threat and the tool position (MCP), structural-vs-cosmetic advantages, and how Place dies. |

Two rules the set lives by:

1. **The moat metric** — the percentage of served claims backed by in-product ground truth — is
   the number the company is graded on, not claim count or user count.
2. **Where documents could disagree on dates, [05-ROADMAP.md](05-ROADMAP.md) wins.**
