# Vision & Moat Thesis

**In one breath:** Place is an outdoor experience graph company whose first product is a discovery app. The primary object is the activity, not the pin: we answer "I want to wild-swim for 3 hours this afternoon — where?" instead of "how do I hike the trail I already picked?" The graph binds affordances ("you can wild-swim at High Rocks") to executable condition predicates over free public sensors ("swimmable when Clackamas gauge 14210000 reads below 1,200 cfs"), and accumulates ground-truth verifications that no competitor can backfill at any price. The moat is deliberately built on perishability: condition claims rot in weeks, so a copied graph is stale on arrival, and only the party running the in-field verification flywheel holds a *current* one. Everything else — the app, the feed, the seasonal tools — exists to feed, exercise, or defend that graph.

---

## 1. The founding inversion

Every incumbent in outdoor recreation answers the same question: *"I already know the place — help me get there, hike it, book it."* AllTrails assumes you picked a trail. Google Maps assumes you picked a destination. Recreation.gov assumes you picked a campground. The place is the primary key; the experience is metadata.

Place inverts this. The user's real question is almost never about a place. It is: **"I have three hours, a dog, and a hot afternoon — what's the best thing I can do outside right now?"** Today that question is answered by stitching together Google Maps, an AllTrails search, a Reddit thread from 2023, a weather app, and a guess about whether the parking lot is full. No product answers it, because no product's data model can: the answer requires joining *activities* to *places* to *live conditions* to *time budgets*, and nobody structured that join.

So the primary object in Place is the **experience** — a reified affordance node, "you can do X at Y under conditions Z" — and places are just where experiences live. That single schema decision is the company.

The product truth this unlocks, the screen no incumbent and no generic LLM can render, is:

> **"What's good right now, near you."**

Not "highest-rated." Not "most-reviewed." *Good today*: Tamanawas Falls flowing hard because 1.6 inches of rain fell in the last 72 hours; High Rocks swim-safe because the Clackamas at Estacada (USGS 14210000) is under 1,200 cfs and the air is above 75°F; Dog Mountain balsamroot at peak per three reports this week. Every card in the feed carries its live reason with provenance. That line — "verified 6 days ago at 410 cfs" — is the signal no competitor can show, and it is the whole brand.

## 2. The experience-graph thesis

Place is not a discovery app with a database; it is **an outdoor experience graph company whose first product is a discovery app**. The graph links places to activities through reified **Affordance** nodes, each bound to **ConditionWindows** — executable predicates over free public sensor feeds — each carrying provenance **Claims** and an accumulating **Verification** log of ground-truth outcomes under recorded conditions.

The critical distinction: places are commodity data. OSM, GNIS, and RIDB will hand anyone 1,200 canonical waterfalls, viewpoints, and swim areas in the Portland 90-minute polygon in an afternoon. What exists *nowhere* in structured form is the affordance layer — you can cliff-jump here, the larches turn gold here in mid-October, this tide pool needs a minus tide — and the conditions layer that makes each affordance true or false on a given day. That knowledge lives scattered across Reddit threads, Oregon Hikers forum posts, and trip reports, unstructured and unqueryable. Structuring it, wiring it to live sensors, and then *ground-truthing* it through use is the asset.

The full ontology, schema, and worked examples live in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md). The product loop that feeds the graph lives in [02-PRODUCT.md](02-PRODUCT.md). This document's job is to fix the thesis and the vocabulary.

## 3. The moat stack

Ranked, structural first. A moat here means: an asset that compounds with use and cannot be bought, scraped, or reconstructed by a well-funded entrant.

**M1 — Sensor bindings (the calibration layer).** The mapping from (place × activity) to a specific public sensor and a learned threshold — "High Rocks is swim-safe below 1,200 cfs on Clackamas gauge 14210000" — appears in no corpus on earth. The feeds themselves (USGS NWIS, NOAA CO-OPS tides, SNOTEL, NWS/Open-Meteo, AirNow, sun/moon ephemeris) are free to everyone; **the joins are earned local judgment**, forged one drainage at a time, then tightened by every verification — a "sketchy at 700 cfs" report narrows the bound. A copycat gets the same feeds and none of the joins. We launch on ~100 hand-forged bindings — 60 Gorge waterfalls against 72-hour NWS precipitation plus creek gauges, live at the October 2026 launch; 40 swim holes against gauges 14210000 and 14137000, forged privately through summer 2026 for the June 2027 swim tool — and grow to ~500 in year one.

**M2 — The time-serial verification log.** Every one-tap claim verdict auto-attaches a condition snapshot — flow, temp, tide, date; we never ask users to describe the weather. The result is labeled claim→outcome pairs under recorded conditions. **This layer cannot be backfilled at any price.** Like Waze's incident history, it requires having been there, in product, when it happened. A 2028 entrant can re-run a frontier model over Reddit and clone our claim layer in a weekend; it cannot recreate two years of outcomes.

**M3 — Calibrated confidence with per-claim-class decay.** Confidence = source-type prior × corroboration boost × recency decay, updated by verifications. Decay is per claim class: geomorphic claims (the waterfall exists) decay over decades; access claims (rope swing intact, gate open, log crossing passable) decay in months. The decay parameters are *learned from the verification log* — nobody without the outcome labels can calibrate — and miscalibration is felt directly as product failure: sending a family to a washed-out swimming hole. The math lives in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md).

**M4 — Temporal ranking exhaust.** Every feed impression, "I'm going" tap, and Sunday verdict is a labeled example of "condition vector X made place Y good/bad on date Z" — joint observations of conditions *and* outcomes at decision time. Incumbents' static surfaces structurally cannot emit these labels; collecting them requires making a temporal feed the primary surface, which is exactly what the MVP does.

**M5 — Substitution and pairing edges (later).** QUIET_ALTERNATIVE_TO (Elowah Falls ← Multnomah when crowded), PAIRS_WITH_IN_WINDOW (sunrise viewpoint + swim + diner = one 4-hour loop), learned from trip acceptances and co-visits. This is what eventually powers the Trip Builder — which is deferred precisely because it exercises the graph without feeding it (see the deferral table in [02-PRODUCT.md](02-PRODUCT.md)).

**M6 — The conditional taste graph (later).** User × affordance × condition preference labels: "will drive 90 minutes for larches, not for a viewpoint; hikes with a reactive dog." Worthless to a competitor without the condition layer to index into — which is why it stacks *on top of* M1–M4 rather than substituting for them.

### Explicitly NOT moats

- **The scraped claim layer.** Our 5,000–10,000 LLM-extracted claims are the *drawbridge*, not the castle: 2027-class models will let anyone replicate them in a weekend, and that's fine. Their job is to bootstrap the flywheel that builds M1–M4.
- **The place database.** OSM/GNIS/RIDB commodity. Anyone can have it by Friday.
- **Every UI feature.** Natural-language search, trip builder, experience cards — each is a sprint for any competent team. Features exercise the graph; they are not the graph.

### The moat metric

**Percentage of served claims backed by in-product ground truth** (verification events), not raw claim count. Raw claims measure the drawbridge; verified claims measure the castle. Roadmap goal ([05-ROADMAP.md](05-ROADMAP.md)): user verification overtakes extraction as the dominant claim support within 12–18 months of launch.

## 4. Why now

Three curves crossed, and none of them was true in 2019.

**1. LLM extraction over unstructured trip reports became cheap.** The affordance layer has always existed — in twenty years of Reddit threads, Oregon Hikers field-guide pages, and forum trip reports. What changed is that a Haiku-class model on the batch API can now read ~150k source documents and emit 5,000–10,000 structured claims ({place_ref, activity, …} — abbreviated; the frozen schema lives in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)) for **≤$200 one-time, ~$20/month incremental**. When AllTrails and Google built their datasets, structuring this corpus was economically impossible, so they didn't; their schemas fossilized around what was cheap then. And the corpus *appreciates*: we cache it and store an extractor version on every claim, so each model generation re-extracts denser claims from the same documents at lower cost. Pipeline details in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md).

**2. The sensor layer is free and public.** USGS NWIS streamflow, NOAA CO-OPS tides, SNOTEL snowpack, NWS/Open-Meteo forecasts, NWAC avalanche, AirNow smoke — every feed needed to make the graph *temporal* costs nothing. The entire why-now burn is under $50/month. The scarce input is not data access; it is the judgment to bind gauge 14210000 to a specific swimming hole at a specific threshold (M1).

**3. Incumbents are locked to their primary keys.** AllTrails' revenue is per-trail SEO pages; a swimming hole at mile 1.2 has no home in its schema, and re-keying the database restructures the pages that drive its organic traffic. Google Maps monetizes commercial POIs; unowned nature earns nothing, and at Google's scale liability forces category suppression — they *cannot* recommend a cliff jump. Recreation.gov is a Booz Allen contract scoped to bookable federal inventory. Nobody's P&L rewards structuring the tail, and for the big two, changing the data model means changing the revenue model. The per-incumbent analysis is [06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)'s job; the thesis-level point is that the window is structural, not temporary inattention.

A fourth fact shapes strategy rather than opportunity: generic LLMs will commoditize the discovery *interface*. A frontier model with web search retrieves documents, not a constraint-solvable graph — it cannot join live gauges against structured affordances, cannot know today's flow or this week's gate closure, regresses to the top-50 spots, and will not take the liability of hallucinating a swimming hole. Place's answer is to **be the tool LLMs call**: an MCP server exposing `search_experiences` and `get_conditions` within six months of launch, with the freshest tier gated by attribution and rate terms. Perishability is the API leverage — aggregators must keep calling, because last month's copy is worthless.

## 5. The governing design principle: perishability as moat

Most data companies fight decay. Place *maximizes the time-varying share of its graph* on purpose.

Because condition claims rot in weeks, a scraped, bought, or LLM-reconstructed copy of Place's graph is stale almost immediately. The only way to hold a *current* graph is to own an in-field verification flywheel — and the flywheel requires already having the product, the users, and the Sunday-evening one-tap ritual. Freshness converts a small dataset's usual weakness into its defense: 150 places with dense, condition-wired, recently-verified claims beat 400 shallow ones, which is exactly the launch depth bar.

This principle governs every design decision in the sibling docs. It is why the feed is temporal (`now_score`, not static rank). It is why the schema reifies affordances instead of tagging places. It is why saves are standing queries that fire when conditions trigger. It is why the verification prompt and the re-engagement prompt are the same Sunday notification. When a design choice is ambiguous, ask: *does this increase the share of the graph that only a live, verifying operator can hold?* If not, it is a feature, and features are not moats.

## 6. What Place is NOT

Each refusal is load-bearing — it protects a layer of the moat.

**Not a trails app.** Trails are AllTrails' primary key and its kill zone; competing there means competing with a decade of per-trail SEO. Place's affordances — paddle, tide-pool, stargaze, hot-spring, swim-hole — mostly have *no trail primary key at all*. Owning non-trail affordances and "right now" is the counter to AllTrails' most dangerous move (extracting structured conditions from its own review corpus), because that move will always be scoped as a hiking-page upsell.

**Not a review site.** Reviews are prose about the past; the graph needs verdicts about claims under recorded conditions. "How was it?" is a chore; "was the pool swimmable?" is a one-second favor. The moment we accept free-text reviews as the contribution primitive, we're collecting the same unstructured sludge we extract from — and forfeiting M2's labeled pairs. We store atomic claims with citation URLs, never source prose.

**Not a social network.** Below ~5k users a social layer is empty rooms, and gamification pollutes the verification signal — badge-hunters generate verdicts to earn badges, not because they went. The only recognition at launch is named provenance credit for power verifiers, because that recruits exactly the ten people whose ground truth we need and no one else.

**Not a booking engine.** Bookable inventory is Recreation.gov's federal contract and the one place incumbents' data is genuinely good. Place links out to permits (the RIDB crosswalk already captures the Multnomah Falls timed-use permit) and keeps its surface on the vast majority of experiences that are unowned, unbookable, and therefore unstructured by anyone else — which is precisely where the affordance data is scarce.

## 7. Vocabulary

These five terms are used with exactly these meanings in every document. The full formal ontology is in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md).

- **Affordance** — a reified node, not a tag: "you can *wild-swim* at *High Rocks*," carrying difficulty, typical duration, and dog/kid flags. The anchor object for claims, condition windows, and verifications. Activities come from a closed vocabulary of ~120 verbs. (A tag can't carry conditions, provenance, or a verification history — that's AllTrails' ceiling, and the reason we reify.)

- **Condition window** — a typed, *executable* predicate over a named public feed that says when an affordance is live. Types: seasonal, weather_triggered, hydrological, tidal, astronomical, snow. Example: `hydrological: usgs(14210000).discharge_cfs < 1200 AND openmeteo(air_temp_f) > 75`.

- **Claim** — a provenance record asserting an affordance or condition: source type (llm_extracted | user_reported | founder_verified | sensor_derived), source URL, minimal verbatim quote held internally as evidence and never republished, **observed_date** (when the experience happened, not when it was posted), extractor version, confidence. Nothing auto-publishes from a single LLM extraction; standard claims need ≥2 independent sources or a founder/user verification, and hazard-class affordances carry stricter gates.

- **Verification** — a one-tap user verdict (confirm / deny / changed) on a claim, with an automatically attached snapshot of the conditions at visit time. The atomic unit of the moat metric, and the only data layer we own outright from day one.

- **Binding** — a forged join between an affordance and a specific sensor with a learned threshold: gauge 14210000 ↔ High Rocks swimmability at <1,200 cfs. Bindings are hand-made local judgment first (~100 at launch), then tightened continuously by verifications. The bindings program is specified in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md).

## 8. Where this goes

The wedge is Portland's 90-minute drive polygon — the Gorge is the densest concentration of condition-dependent experiences in North America, and Oregon's incumbent corpus (the Oregon Hikers field guide) is an unguarded stale wiki, unlike Seattle's beloved WTA (which becomes the metro-2 *partner*, never a target). Go-to-market is not "launch an app": it is a seasonal cadence of free, no-login condition tools off one graph — the flow-ranked Gorge waterfall tool in October 2026 (public launch #1), the wildflower tracker in April, the swim-holes-ranked-by-today's-water tool in June 2027, three weeks before July 4 — each a legitimate r/Portland post, a daily-regenerated SEO surface, and a reuse of every prior binding. The calendar, gates, and moat checkpoints are [05-ROADMAP.md](05-ROADMAP.md)'s contract; the current repo (a ~140-line FastAPI/Mongo seed) and the path from it are handled honestly in [04-ARCHITECTURE.md](04-ARCHITECTURE.md).

One person, under $50 a month, one drainage at a time — building the only dataset in the category that is worth more *because* it expires.
