# Vision & Moat Thesis

**In one breath:** Place is the WHEN engine — a perishable-decision-window company whose first product is an outdoor discovery app. Every incumbent answers *where*: find the place, get to the place, book the place. Place answers **when**: it binds real experiences ("you can wild-swim at High Rocks") to executable condition predicates over free public sensors ("swimmable when Clackamas gauge 14210000 reads below 1,200 cfs"), verifies the thresholds in the field, and then *watches the feeds so its users don't have to*. The paid unit is not information — it is **vigilance**: a watcher standing on every window a household cares about, pushing the moment it opens. The moat is deliberately built on perishability: windows rot in hours-to-weeks, so a copied graph is stale on arrival, and only the party running the in-field verification flywheel holds a *current* one. Everything else — the app, the feed, the Almanac, the seasonal tools — exists to feed, exercise, or defend that engine.

*(Naming note: "Windows"/"the WHEN engine" is internal doctrine shorthand for this reframe, never a consumer name — Microsoft owns that word in every consumer's head. The company and the product remain **Place**.)*

---

## 1. The founding inversion

Every incumbent in local discovery answers the same question: *"I already know the place — help me get there, hike it, book it."* AllTrails assumes you picked a trail. Google Maps assumes you picked a destination. Recreation.gov assumes you picked a campground. Even the weather app — the one incumbent that lives in time — knows nothing about what its numbers *mean* for any particular place. The place is the primary key; time is metadata everywhere.

The founding question was outdoor and specific, and it stays as family #1's daily bread: **"I have three hours, a dog, and a hot afternoon — what's the best thing I can do outside right now?"** Today that question is answered by stitching together Google Maps, an AllTrails search, a Reddit thread from 2023, a weather app, and a guess about whether the parking lot is full. No product answers it, because no product's data model can: the answer requires joining *activities* to *places* to *live conditions* to *time budgets*, and nobody structured that join.

But the general form of the question is bigger than the outdoors. The minus tide that exposes the Haystack pools for ninety minutes. The first larch weekend. The chanterelle flush four to ten days after the first two-inch October rain. The aurora bar clearing on a moonless night. The Timothy Lake campsite that just opened up under $30. The first smoke-free morning after a week indoors. None of these is a *place* question — every one is a **when** question, each perishable on its own clock, each answerable only by joining a live public feed against a locally-verified threshold. Nobody owns *when*.

So the primary object in Place is the **window** — the span in which an experience is *actually good* — and the product truth this unlocks, the screen no incumbent and no generic LLM can render, is still:

> **"What's good right now, near you."**

Not "highest-rated." Not "most-reviewed." *Good today*: Tamanawas Falls flowing hard because 1.6 inches of rain fell in the last 72 hours; High Rocks swim-safe because the Clackamas at Estacada (USGS 14210000) is under 1,200 cfs and the air is above 75°F; Dog Mountain balsamroot at peak per three reports this week. Every card carries its live reason with provenance. That line — "verified 6 days ago at 410 cfs" — is the signal no competitor can show, and it is the whole brand.

## 2. The window-engine thesis

Place is not a discovery app with a database; it is **a window-engine company whose first product is a discovery app**. The engine is five parts, all built: executable condition predicates over named public feeds (the DSL in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)), verified local thresholds (the bindings program, [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)), temporal ranking (`now_score`), **watchers** — standing queries that re-evaluate on every sweep — and push. The experience graph — affordances, claims, verifications — is the substrate the engine runs on, and the graph doc remains its engineering contract.

The critical distinction survives the reframe intact: places are commodity data. OSM, GNIS, and RIDB will hand anyone 1,200 canonical waterfalls, viewpoints, and swim areas in the Portland 90-minute polygon in an afternoon. What exists *nowhere* in structured form is the affordance layer — you can cliff-jump here, the larches turn gold here in mid-October — and the **window layer** that makes each affordance true or false on a given day. Structuring that knowledge, wiring it to live sensors, and *ground-truthing* it through use is the asset.

What the reframe adds: **the engine is family-agnostic.** Outdoors is the first of six window families — outdoor, sky, harvest, reservation, health, crowd ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)) — and each new family is one adapter class plus a set of forged bindings; the DSL, the evaluator, watchers, and push carry over unchanged. The marginal vertical is an afternoon of adapter code plus the binding judgment — and the judgment *is* the moat work, so horizontal expansion never leaves the moat's home turf.

The product loop that feeds the graph lives in [02-PRODUCT.md](02-PRODUCT.md); the curated catalog users watch from is [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md). This document's job is to fix the thesis and the vocabulary.

## 3. The moat stack

Ranked, structural first. A moat here means: an asset that compounds with use and cannot be bought, scraped, or reconstructed by a well-funded entrant.

**M1 — Sensor bindings (the calibration layer).** The mapping from (place × activity) to a specific public sensor and a learned threshold — "High Rocks is swim-safe below 1,200 cfs on Clackamas gauge 14210000" — appears in no corpus on earth. The feeds themselves (USGS NWIS, NOAA CO-OPS tides, SNOTEL, NWS/Open-Meteo, AirNow, sun/moon ephemeris) are free to everyone; **the joins are earned local judgment**, forged one drainage at a time, then tightened by every verification — a "sketchy at 700 cfs" report narrows the bound. And the same is true in every family: "chanterelles flush 4–10 days after the first 2-inch October rain in the Coast Range" is in no corpus either. A copycat gets the same feeds and none of the joins. We launch on ~100 hand-forged bindings — 60 Gorge waterfalls against 72-hour NWS precipitation plus creek gauges, live at the October 2026 launch; 40 swim holes against gauges 14210000 and 14137000, forged privately through summer 2026 for the June 2027 swim tool — and grow to ~500 in year one.

**M2 — The time-serial verification log.** Every one-tap claim verdict auto-attaches a condition snapshot — flow, temp, tide, date; we never ask users to describe the weather. The result is labeled claim→outcome pairs under recorded conditions. **This layer cannot be backfilled at any price.** Like Waze's incident history, it requires having been there, in product, when it happened. A 2028 entrant can re-run a frontier model over Reddit and clone our claim layer in a weekend; it cannot recreate two years of outcomes.

**M3 — Calibrated confidence with per-claim-class decay.** Confidence = source-type prior × corroboration boost × recency decay, updated by verifications. Decay is per claim class: geomorphic claims (the waterfall exists) decay over decades; access claims (rope swing intact, gate open, log crossing passable) decay in months. The decay parameters are *learned from the verification log* — nobody without the outcome labels can calibrate — and miscalibration is felt directly as product failure: sending a family to a washed-out swimming hole, or pushing a watcher that cries wolf. The math lives in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md).

**M4 — Temporal ranking exhaust.** Every feed impression, "I'm going" tap, and Sunday verdict is a labeled example of "condition vector X made place Y good/bad on date Z" — joint observations of conditions *and* outcomes at decision time. Incumbents' static surfaces structurally cannot emit these labels; collecting them requires making a temporal feed the primary surface, which is exactly what the MVP does.

**M5 — Substitution and pairing edges (accumulating from launch, rendered later).** QUIET_ALTERNATIVE_TO (Elowah Falls ← Multnomah when crowded), PAIRS_WITH_IN_WINDOW (sunrise viewpoint + swim + diner = one 4-hour loop), learned from trip acceptances, co-visits, and — from launch — "nearby after" module taps ([07-USERS.md](07-USERS.md) §4). This is what eventually powers the Trip Builder — which is deferred precisely because it exercises the graph without feeding it (see the deferral table in [02-PRODUCT.md](02-PRODUCT.md)).

**M6 — The conditional taste graph (later).** User × affordance × condition preference labels: "will drive 90 minutes for larches, not for a viewpoint; hikes with a reactive dog." Worthless to a competitor without the condition layer to index into — which is why it stacks *on top of* M1–M4 rather than substituting for them.

**M7 — Watch exhaust (new with the watcher tier).** The demand map of what a metro's households actually *wait for*: which watchables they hold, at what thresholds, with what open→go activation rates. No incumbent can observe this — a bookmark is silent; a watcher is a declared, standing preference with a measurable response to every window it fires on. Watch exhaust sequences the family ladder ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)), curates the Almanac ([09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md)), and eventually prices Groundwire ([10-GROUNDWIRE.md](10-GROUNDWIRE.md)). Like M2, it cannot be backfilled: you need the watchers running to learn what people watch.

### Explicitly NOT moats

- **The scraped claim layer.** Our 5,000–10,000 LLM-extracted claims are the *drawbridge*, not the castle: 2027-class models will let anyone replicate them in a weekend, and that's fine. Their job is to bootstrap the flywheel that builds M1–M4.
- **The place database.** OSM/GNIS/RIDB commodity. Anyone can have it by Friday.
- **The Almanac's prose.** Watchable names and blurbs are copyable in an afternoon; the executable predicates, backtested open-frequencies, and measured hit-rates behind them are M1/M3/M7, and those are not.
- **Every UI feature.** Natural-language search, trip builder, experience cards — each is a sprint for any competent team. Features exercise the graph; they are not the graph.

### The moat metric

**Percentage of served claims backed by in-product ground truth** (verification events), not raw claim count. Raw claims measure the drawbridge; verified claims measure the castle. Roadmap goal ([05-ROADMAP.md](05-ROADMAP.md)): user verification overtakes extraction as the dominant claim support within 12–18 months of launch.

## 4. Why now

Three curves crossed, and none of them was true in 2019.

**1. LLM extraction over unstructured trip reports became cheap.** The affordance layer has always existed — in twenty years of Reddit threads, Oregon Hikers field-guide pages, and forum trip reports. What changed is that a Haiku-class model on the batch API can now read ~150k source documents and emit 5,000–10,000 structured claims ({place_ref, activity, …} — abbreviated; the frozen schema lives in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)) for **≤$200 one-time, ~$20/month incremental**. When AllTrails and Google built their datasets, structuring this corpus was economically impossible, so they didn't; their schemas fossilized around what was cheap then. And the corpus *appreciates*: we cache it and store an extractor version on every claim, so each model generation re-extracts denser claims from the same documents at lower cost. Pipeline details in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md).

**2. The sensor layer is free and public — and it covers far more than the outdoors.** USGS NWIS streamflow, NOAA CO-OPS tides, SNOTEL snowpack, NWS/Open-Meteo forecasts, NWAC avalanche, AirNow smoke — every feed needed to make the graph *temporal* costs nothing. So do NOAA space weather (aurora), sun/moon ephemeris, and Recreation.gov availability — the feeds behind the next families ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)). The entire why-now burn is under $50/month. The scarce input is not data access; it is the judgment to bind gauge 14210000 to a specific swimming hole at a specific threshold (M1).

**3. Incumbents are locked to their primary keys.** AllTrails' revenue is per-trail SEO pages; a swimming hole at mile 1.2 has no home in its schema, and re-keying the database restructures the pages that drive its organic traffic. Google Maps monetizes commercial POIs; unowned nature earns nothing, and at Google's scale liability forces category suppression — they *cannot* recommend a cliff jump. Recreation.gov is a Booz Allen contract scoped to bookable federal inventory. Nobody's P&L rewards structuring the tail, and for the big two, changing the data model means changing the revenue model. **And nobody's key is the window** — the single-purpose alert utilities (a campsite sniper here, an aurora app there) each own one family with no verified local thresholds, no verification loop, and no household bundle ([06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)). The window is structural white space, not temporary inattention.

A fourth fact shapes strategy rather than opportunity: generic LLMs and OS assistants will commoditize the discovery *interface* — and increasingly they will take standing orders ("tell me when…") that they cannot actually keep, because they hold no verified thresholds and no live joins. Place's answer is unchanged in kind and upgraded in ambition: **be the substrate they call.** An MCP server ships within six months of launch, and its endgame — signed, expiring freshness certificates, with perishability as the rate card — is specified in [10-GROUNDWIRE.md](10-GROUNDWIRE.md). Aggregators must keep calling, because last month's copy is worthless.

## 5. The paid unit is vigilance, not information

The original sin of "information products" is monetizing the lookup. Nobody pays for an answer they could find once — going to sources, comparing notes, even the socializing around it is work people don't actually mind. What people demonstrably pay for is **standing vigilance**: Surfline (~$100/yr over public surf data), Carrot Weather ($20–60/yr over free NWS data), Flighty ($48/yr over data airlines give away), Campnab ($10–30/mo to watch Recreation.gov availability). In every case the paid thing is never the fact — it is the *watching*: continuous monitoring the customer cannot sustain, judgment applied to raw feeds ("is 1,200 cfs safe?"), and a push at exactly the right moment.

Place is built to sell exactly that, because the engine already is that: a watcher is a standing query the evaluator re-runs on every sweep, against thresholds no one else has verified. The free tier browses "what's good now" and holds a starter allowance of watchers; the paid household tier holds unlimited watchers with guaranteed delivery. Pricing, tiers, and the conversion moment are committed in [02-PRODUCT.md](02-PRODUCT.md).

Two-sided honesty, stated up front: **revenue and the moat share one loop.** A paid push produces the "I'm going" tap, which produces the Sunday verdict, which tightens the threshold that made the push accurate. Households pay for vigilance; vigilance manufactures verification; verification is the moat. There is no tension between the business and the dataset — they are the same flywheel, which is exactly what "the first AI service an average person genuinely pays for" has to look like from the inside.

## 6. The governing design principle: perishability as moat

Most data companies fight decay. Place *maximizes the time-varying share of its graph* on purpose.

Because condition claims rot in weeks, a scraped, bought, or LLM-reconstructed copy of Place's graph is stale almost immediately. The only way to hold a *current* graph is to own an in-field verification flywheel — and the flywheel requires already having the product, the users, and the Sunday-evening one-tap ritual. Freshness converts a small dataset's usual weakness into its defense: 150 places with dense, condition-wired, recently-verified claims beat 400 shallow ones, which is exactly the launch depth bar.

**A watcher is perishability productized.** The user is not buying the graph; they are renting its freshness, one window at a time — which is why the paid tier and the moat metric move together.

This principle governs every design decision in the sibling docs. It is why the feed is temporal (`now_score`, not static rank). It is why the schema reifies affordances instead of tagging places. It is why watchers are standing queries that fire when conditions trigger. It is why the verification prompt and the re-engagement prompt are the same Sunday notification. When a design choice is ambiguous, ask: *does this increase the share of the graph that only a live, verifying operator can hold?* If not, it is a feature, and features are not moats.

## 7. What Place is NOT

Each refusal is load-bearing — it protects a layer of the moat.

**Not a trails app.** Trails are AllTrails' primary key and its kill zone; competing there means competing with a decade of per-trail SEO. The general form of this refusal now covers every incumbent: **Place is keyed to no one else's primary key — not the trail, not the pin, not the reservation.** Place's affordances — paddle, tide-pool, stargaze, hot-spring, swim-hole — mostly have *no trail primary key at all*, and owning non-trail affordances and "right now" remains the counter to AllTrails' most dangerous move (extracting structured conditions from its own review corpus), because that move will always be scoped as a hiking-page upsell.

**Not a review site.** Reviews are prose about the past; the graph needs verdicts about claims under recorded conditions. "How was it?" is a chore; "was the pool swimmable?" is a one-second favor. The moment we accept free-text reviews as the contribution primitive, we're collecting the same unstructured sludge we extract from — and forfeiting M2's labeled pairs. We store atomic claims with citation URLs, never source prose. Every window family must have a one-tap verification story of its own, or it fails the admission test ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)).

**Not a social network.** Below ~5k users a social layer is empty rooms, and gamification pollutes the verification signal — badge-hunters generate verdicts to earn badges, not because they went. The only recognition at launch is named provenance credit for power verifiers, because that recruits exactly the ten people whose ground truth we need and no one else.

**Not a booking engine — and watching a cancellation is not booking it.** The refusal's original point survives: bookable inventory is Recreation.gov's federal contract and the one place incumbents' data is genuinely good — at *booking*. It is terrible at telling you the moment a Saturday opened up. Place detects that inventory state changed — a predicate over a public availability feed, the same machinery as a tide — and pushes; the user completes the transaction on Recreation.gov. The precise line: **Place never holds inventory, never takes booking payment, never auto-books, never sits in the transaction path.** Reservation windows are windows; the booking stays someone else's business.

**Not an alert firehose.** Watchers fire on state transitions only, never on readings. Every watchable publishes its measured hit-rate, and one that cries wolf gets unpublished ([09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md)). The Sunday one-push cap stands. A vigilance product that trains its users to swipe away its pushes has sold them nothing.

### What we are not becoming

The horizontal is a ladder, not a sprawl, and these lines keep it one. **No user-authored predicates** — the Almanac is curated, because the threshold *is* the product; a generic IFTTT-for-feeds has no moat and no editorial voice. **Not a price tracker** — "under $30" is an attribute of a reservation window, never a deals surface. **Not a weather app, not a news app** — Place serves *joins* (feed × place × threshold), never raw feeds. **The family admission test is a gate, not a vibe** ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)) — the crowd family waits for verification exhaust; pollen waits for a real feed. **The depth bar transposes per family × metro** — a family ships only with verified local thresholds, never national defaults; six shallow families is the sprawl-death, and "150 dense beats 400 shallow" now applies to every rung of the ladder.

## 8. Vocabulary

These terms are used with exactly these meanings in every document. The full formal ontology is in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md).

The graph five:

- **Affordance** — a reified node, not a tag: "you can *wild-swim* at *High Rocks*," carrying difficulty, typical duration, and dog/kid flags. The anchor object for claims, condition windows, and verifications. Activities come from a closed vocabulary of ~120 verbs. (A tag can't carry conditions, provenance, or a verification history — that's AllTrails' ceiling, and the reason we reify.)

- **Condition window** — a typed, *executable* predicate over a named public feed that says when an affordance is live. Windows **open** and **close** — never "alert fired." Example: `hydrological: usgs(14210000).discharge_cfs < 1200 AND openmeteo(air_temp_f) > 75`.

- **Claim** — a provenance record asserting an affordance or condition: source type (llm_extracted | user_reported | founder_verified | sensor_derived), source URL, minimal verbatim quote held internally as evidence and never republished, **observed_date** (when the experience happened, not when it was posted), extractor version, confidence. Nothing auto-publishes from a single LLM extraction; standard claims need ≥2 independent sources or a founder/user verification, and hazard-class affordances carry stricter gates.

- **Verification** — a one-tap user verdict (confirm / deny / changed) on a claim, with an automatically attached snapshot of the conditions at visit time. The atomic unit of the moat metric, and the only data layer we own outright from day one.

- **Binding** — a forged join between an affordance and a specific sensor with a learned threshold: gauge 14210000 ↔ High Rocks swimmability at <1,200 cfs. Bindings are hand-made local judgment first (~100 at launch), then tightened continuously by verifications. The bindings program is specified in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md).

The product six:

- **Window family** — a set of windows sharing feeds, an adapter class, and a verification story: outdoor, sky, harvest, reservation, health, crowd. The doctrine, per-family specs, and admission test are [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md).

- **Watchable** — one curated, nameable moment in the Almanac ("Haystack minus tides," "first larch weekend"): an editorial layer over one or more condition windows, carrying a backtested expected open-frequency and a measured hit-rate. Spec in [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md).

- **Watcher** — a user's standing query on a window or watchable; the verb is **watch**. Product language for what the schema calls a save — every watcher is re-evaluated by the same sweep, and fires on the open transition. `want_to` saves are grandfathered as watchers.

- **The Almanac** — the per-metro curated catalog of watchables; the browse-and-watch surface ([02-PRODUCT.md](02-PRODUCT.md)). Internal docs may say "watcher catalog"; the product says Almanac.

- **Vigilance** — the paid unit: the free tier browses and holds starter watchers; the paid household tier holds unlimited watchers with guaranteed delivery. Pricing lives in [02-PRODUCT.md](02-PRODUCT.md), nowhere else.

- **Groundwire** — the year-2+ API product: signed, expiring freshness certificates over MCP, priced on perishability. Specified in [10-GROUNDWIRE.md](10-GROUNDWIRE.md).

## 9. Where this goes

The wedge is unchanged: Portland's 90-minute drive polygon — the Gorge is the densest concentration of condition-dependent experiences in North America, and Oregon's incumbent corpus (the Oregon Hikers field guide) is an unguarded stale wiki, unlike Seattle's beloved WTA (which becomes the metro-2 *partner*, never a target). Go-to-market is unchanged in shape and upgraded in destination: a seasonal cadence of free, no-login condition tools off one graph — the flow-ranked Gorge waterfall tool in October 2026 (public launch #1), the wildflower tracker in April, the swim tool in June 2027, three weeks before July 4 — except that every tool is now an **Almanac seed**, and every card's call to action is *"Watch this — we'll tell you when it's going off."*

From there the ladder climbs one family per season, each admitted by the test in [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md), each an afternoon of adapter code plus a season of binding judgment: sky windows in the first winter, harvest and reservation windows through 2027 — the reservation family is the paid tier's anchor, per the calendar in [05-ROADMAP.md](05-ROADMAP.md) — health windows when smoke season sells them, crowd windows only when verification exhaust makes them honest. The metro playbook in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) then transposes the whole ladder, not just the outdoor rung. And when the graph is dense enough that assistants need it more than users need another app, the same engine turns its API face outward as Groundwire ([10-GROUNDWIRE.md](10-GROUNDWIRE.md)).

One person, under $50 a month, one window at a time — building the only dataset in the category that is worth more *because* it expires.
