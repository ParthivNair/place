# Competitive Landscape — Keys, Locks & Bright Lines

**In one breath:** Every incumbent is locked to its primary key — the object its revenue engine indexes — and re-keying the database means restructuring the revenue, so none of them will build a conditions-first affordance graph; and nobody's key is the *window*, which sits even further from every revenue engine than the affordance does. The single-family alert utilities (Campnab-class snipers, Surfline, aurora and AQI apps) are simultaneously the willingness-to-pay proof and the real fight: Place must make cross-family watching one product and one habit, or it is a worse version of five free apps plus one paid one. The #1 threat is AllTrails running LLM extraction over its own review corpus; the counter is owning non-trail affordances and "right now" before they ship a hiking-page upsell. The #2 threat is generic LLMs — and now OS assistants taking standing orders they cannot keep — eating the discovery interface; the counter is becoming the tool they call: an MCP server within 6 months of launch, perishability as the API leverage, Groundwire as the productized endgame. Four structural advantages exist at launch (bindings, verification log, calibration, temporal exhaust), and three more — substitution edges, the conditional taste graph, and watch exhaust — compound later; everything visible on screen is cosmetic and must never be rested on. Bright lines: never scrape AllTrails, WTA is a partner, Reddit via official API only, Recreation.gov polling within published terms only.

---

## 1. The unifying frame: primary keys and the locks on them

State it once, sharply: **every incumbent's database is keyed to the object its revenue depends on, and changing the key means changing the revenue model.** AllTrails is keyed to the trail because per-trail SEO pages are its organic-traffic engine. Google Maps is keyed to the commercial POI because ads monetize businesses, and an unowned swimming hole earns nothing. Strava is keyed to the effort trace. onX is keyed to licensed parcel and GIS layers because the licensing pays. Recreation.gov is keyed to bookable federal inventory because that is the scope of a Booz Allen contract. Komoot is keyed to routes under post-acquisition margin extraction. **Nobody's P&L rewards structuring the long tail of what you can do outside, when, under what conditions** — and for the two giants, the lock is not laziness but load-bearing revenue architecture. Place's key — the reified Affordance bound to executable ConditionWindows ([01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) — is precisely the object none of their schemas can hold without a restructuring their incentives forbid.

And the WHEN reframe ([00-THESIS.md](00-THESIS.md) §1) tightens the lock instead of loosening it: **nobody's key is the window — and re-keying to time is even further from every incumbent's revenue engine than re-keying to affordances.** A trail page could at least grow a conditions widget; a database keyed on perishable spans has no stable page to hang SEO, ads, or a booking flow on — a window opens, pushes, and closes, and every incumbent's monetization needs the object to sit still.

That frame is the whole doc. Each incumbent below is a variation on it.

---

## 2. Per-incumbent analysis

### AllTrails — the #1 threat

**Data model.** Trail objects: geometry, length, elevation gain, difficulty tag, activity *tags* (not reified affordances), photos, and a huge corpus of free-text reviews. "Swimming hole at mile 1.2, good July–September, sketchy above 1,200 cfs" has no home in the schema except a review blob.

**Incentive lock.** The bulk of its acquisition is organic traffic landing on per-trail SEO pages; the subscription upsell hangs off those pages. Re-keying to affordances restructures the exact pages that drive acquisition. Their optimal move is to *enrich the trail page*, never to abandon the trail as key.

**What they COULD do that hurts — the LLM-extraction scenario.** AllTrails points a frontier model at its own review corpus — the largest structured-adjacent trip-report dataset in existence — and ships "Conditions" as a Peak-tier feature: extracted seasonal windows, recent-report summaries, maybe even gauge lookups for river crossings. This is the single most dangerous move on the board because they own the corpus legally, and it converts their moat (reviews) into Place's core feature (structured conditions). Assume they do this; the 2027-class models make it a quarter's work.

**Place's counter — the non-trail-affordance + freshness outflank.** Two structural facts protect Place even in the worst case:

1. **No trail primary key exists for most of Place's graph.** A minus-tide window at Haystack Rock, a paddle put-in on the Willamette, a stargazing site's moon-phase window, a hot spring's snow-gated road, a swim hole judged against Clackamas gauge 14210000 — none of these attach to a trail object. AllTrails' extraction will be *scoped by its key*: conditions **per trail page**, optimized as a hiking upsell by an org whose OKRs are trail-page conversion. It will not re-key.
2. **Freshness beats corpus size.** Their extraction yields historical claims ("reviews mention swimming in July"); Place's condition evaluator yields *current state* ("swimmable now: 890 cfs, verified 6 days ago at 410 cfs"). The verification log (§5 below) cannot be extracted from any corpus at any price — it must be collected in-product, in-field, over time.

So the mandate is temporal: **own non-trail affordances and "right now" before AllTrails ships extraction.** This is why the seasonal cadence opens with the October 2026 waterfall ranker (public launch #1, [05-ROADMAP.md](05-ROADMAP.md)), holds the swim tool to its June 2027 hard date three weeks before July 4, and why the launch depth bar is 150 dense condition-wired places, not 400 shallow ones — depth in exactly the categories their key can't reach.

### Google Maps / Apple Maps

**Data model.** Commercial POI records: name, category, hours, reviews, photos. A dispersed larch grove, an unnamed swimming hole, a tide pool — either absent or a bare pin with no schema for when it's good.

**Incentive lock.** For Google: ads and local commerce. Unowned nature has no advertiser, so it earns nothing and gets no data investment. And at Google's scale, **liability forces category suppression** (§6): Google structurally *cannot* recommend a cliff jump. Apple's lock is different but converges: Maps carries no ads — it exists to sell devices — so there is even less revenue reason to structure unowned nature, and the same platform-scale liability suppression applies.

**What they COULD do.** Fold Gemini into Maps discovery ("hikes near me") — this hurts generic discovery apps badly. It surfaces the top-50 famous spots with static summaries.

**Place's counter.** Don't compete on navigation or ubiquity; Google is the *last-mile partner* (Place cards deep-link to Maps for driving). The contested ground — conditional, hazard-adjacent, long-tail — is exactly what their scale forbids them to touch.

### Strava

**Data model.** GPS effort traces + a segment leaderboard graph. Places exist only as substrate for efforts.

**Incentive lock.** Subscription revenue from training features; the social graph is athletes comparing efforts. "Where should a family swim this Saturday?" is not a Strava query and never will be — their users come to record, not to discover.

**What they COULD do.** Heatmap-derived discovery ("popular routes near you"). Popularity data, not affordance data — it tells you where people go, not what's good there now.

**Place's counter.** Different job entirely; overlap is near zero. If anything, Strava heatmaps are a future *signal* for access-point popularity. No defensive posture needed beyond speed.

### onX (including Mountain Project)

**Data model.** Licensed GIS verticals — land ownership parcels, hunting units, offroad trails — plus, via the Mountain Project acquisition, the deepest crowd-built climbing database (routes, grades, seasonal beta).

**Incentive lock.** Vertical subscriptions priced on licensed data (parcel boundaries) that only pays in high-willingness-to-pay niches: hunters, climbers, offroaders. Mountain Project shows they *understand* community affordance data — but they monetize verticals, not a horizontal experience graph.

**What they COULD do.** Launch "onX Adventure" — a horizontal outdoor discovery vertical, seeded with Mountain Project's community model. This is the most graph-literate incumbent.

**Place's counter.** Their playbook is acquire-a-community-then-charge; they build per-vertical, one expensive licensed layer at a time, and none of their verticals emit *temporal* data. Place's condition evaluator and verification log are horizontal from day one. Watch them; don't fear them this year. (Year-3 note: onX is also the most plausible acquirer profile — they buy structured community data.)

### Recreation.gov

**Data model.** RIDB — bookable federal inventory: campgrounds, permits (including the Multnomah Falls timed-use permit), facilities.

**Incentive lock.** A Booz Allen contract scoped to reservations. It will never rank a free swimming hole by today's flow; nothing outside the bookable inventory exists to it.

**What they COULD do.** Nothing offensive. It is a *data source*, not a competitor — RIDB is in Place's seed inventory ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)).

**Place's counter.** Consume the API; surface permit requirements on every card (a trust and safety feature, per the requirements in [02-PRODUCT.md](02-PRODUCT.md) §5).

### Komoot

**Data model.** Route planning: sport-specific routing profiles, Highlights (user-pinned POIs with photos), collections.

**Incentive lock.** Post-acquisition (Bending Spoons) margin extraction — monetize the existing base, cut costs, not multi-year data-model rebuilds. Highlights are the closest incumbent object to an affordance, but they carry no conditions, no provenance, no verification, and Europe is the center of gravity.

**What they COULD do.** Little, in this ownership phase, in this geography.

**Place's counter.** Ignore operationally; treat Highlights as design prior-art for what an affordance card should *not* be (a static pin with photos).

### TikTok / Instagram as discovery

**Data model.** Engagement-ranked video with geotags. This is where the *demand* actually lives — "hidden swimming hole near Portland" TikToks get millions of views.

**Incentive lock.** Watch-time. The algorithm's job is to keep you scrolling, not to get you outside; it structurally over-concentrates attention on a handful of photogenic spots (the Blue Pool pattern) and attaches zero conditions, safety, or freshness. A viral swim-hole video plays identically in January.

**What they COULD do that hurts.** Keep owning inspiration — they already have it. The hurt is upstream: users form desires there.

**Place's counter.** Don't fight for inspiration; **be the resolution layer.** The TikTok viewer's next question — "is it actually good this weekend, and where do I park?" — is Place's exact query. The seasonal condition tools (the waterfall ranker, Swim Portland) are shareable answers to social-media-generated demand, and "ten good options ranked by conditions" is the dispersal counter-pattern to the viral pin.

---

## 3. The single-family alert utilities — the competitors the reframe makes relevant

The WHEN reframe ([00-THESIS.md](00-THESIS.md)) redraws the competitor map. Once the product is vigilance over windows rather than an outdoor database, a class of companies the old frame never counted becomes directly relevant — and, at the same time, the best willingness-to-pay evidence in existence. They are competitor and proof at once:

- **Campnab / Arvie-class reservation snipers.** They charge per-booking or by monthly subscription to watch Recreation.gov cancellations — one family, one feed, no bundle — and people pay it. That is the proof that the reservation family *alone* covers a household bundle, which is exactly why that family anchors the Vigilance household tier at the Phase 5 paid launch ([02-PRODUCT.md](02-PRODUCT.md); [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F4).
- **Surfline — the category archetype.** Premium-priced vigilance over public surf data, decades old, still growing. It settled the question of whether people pay for someone to watch a free feed and apply judgment; it also never left its one family.
- **Aurora apps.** Kp-threshold push at national defaults — no local sightline judgment, no cloud-cover join, no "was it actually visible from here" loop.
- **Smoke/AQI apps.** Feed rebroadcast with a map: useful, undifferentiated, and structurally unable to say which mornings clear first in *your* valley.
- **IFTTT-class generic triggers.** User-authored predicates over arbitrary feeds: no editorial layer, no verified thresholds, no hit-rates, no opinion. The anti-Almanac — and the reason "no user-authored predicates" is a standing guardrail ([00-THESIS.md](00-THESIS.md) §7).

The gaps are the same four every time. None of them has **verified local thresholds** (they serve the feed's number or a national default, never "swim-safe below 1,200 cfs *here*"). None has a **verification loop** (no in-field verdict ever tightens their trigger). None publishes **calibrated hit-rates** (none could — they hold no outcome labels). None offers a **household bundle** (each is a lane, not a ladder: one family, one price, one narrow habit).

**The honest risk, named, not hand-waved: the bundle-vs-point-apps fight.** These utilities are individually beatable and collectively dangerous, because the failure mode is not losing a feature war — it is failing to cohere. Place must make cross-family watching feel like **one product and one habit** — one Almanac to browse, one watcher list, one push voice, one Sunday ritual across every family — or it is a worse version of five free apps plus one paid one, and households will rationally assemble the pile instead. The bundle wins on one condition only: the seams never show.

---

## 4. The generic-LLM threat (its own section, because it's a different kind)

ChatGPT-with-search answering "where should I swim near Portland tomorrow?" is the commoditization of the discovery *interface*. Take it seriously and locate exactly where it fails:

1. **Documents vs. a constraint-solvable graph.** Web search retrieves prose; it cannot solve "dog-friendly wild-swim, <60 min drive, swimmable at current flow, uncrowded" as a constraint query, because no constraint-shaped substrate exists on the open web. Place's schema *is* that substrate.
2. **No live joins.** A frontier model cannot join USGS NWIS (14210000, 14137000), NOAA CO-OPS tides, SNOTEL, NWS point forecasts, and AirNow against structured affordances in one answer. Place's condition-evaluator cron materializes exactly this join into `good_now`.
3. **Never-written-down facts.** This week's gate closure, today's flow, current balsamroot bloom stage on Dog Mountain — these exist in Place's verification log and sensor bindings, not in any indexed document. You cannot retrieve what was never written.
4. **Top-50 regression.** LLM answers regress to the most-written-about places — Multnomah, Punch Bowl, Ramona Falls — because corpus frequency is their ranking function. The long tail Place structures is invisible to them.
5. **Hallucination liability.** OpenAI will not carry the liability of inventing a swimming hole or asserting a cliff jump is safe; hedged, generic answers are their rational output for hazard-adjacent queries.

The proof is empirical, not rhetorical: the **benchmark-the-enemy exercise** ([05-ROADMAP.md](05-ROADMAP.md)) runs 50 conditional Portland queries ("is Punch Bowl Falls swimmable today?", "where are larches at peak this week?") plus 15 WHEN-form standing orders ("tell me when Timothy Lake has a cancellation under $30") through ChatGPT-with-search and AllTrails; the recorded failure rate is both the wedge definition and the launch narrative, and the standing-order failures seed Groundwire's sales deck ([10-GROUNDWIRE.md](10-GROUNDWIRE.md)).

And the threat is escalating from lookups to standing orders. The OS assistants — Siri, Gemini-in-Android, the ChatGPT apps — will happily *accept* "tell me when the Clackamas is swimmable" or "tell me when a Timothy Lake Saturday opens up," because accepting costs them nothing. They cannot keep the order: no verified local thresholds (what number means swimmable *here*?), no live joins across public feeds, no push infrastructure with calibrated hit-rates standing behind the promise — and a standing order is a promise, graded every time a window opens without a push or a push arrives without a window. Every broken "tell me when…" is category education Place doesn't have to pay for. The counter is unchanged in kind: **be the substrate they call.**

### The tool position — the committed strategy

The conclusion is not "LLMs lose"; it is **"LLMs become the interface, so Place must be the tool they call."** Commitment: an **MCP server within 6 months of launch**, exposing `search_experiences` and `get_conditions` over the same graph the PWA reads. That server is the precursor; the productized endgame is **Groundwire** ([10-GROUNDWIRE.md](10-GROUNDWIRE.md)) — signed, expiring freshness certificates sold to assistants over MCP, with perishability itself as the rate card. Losing alternative (one line): competing with LLM apps on conversational UX — a solo dev cannot out-interface OpenAI, and doesn't need to.

Perishability is the API leverage. A one-time scrape or bulk purchase of Place's graph is worthless within weeks because condition claims rot; aggregators must *keep calling*. Therefore the pricing surface is freshness itself: stale-tier data (geometry, seasonal windows) can be generous; the **freshest tier — `good_now`, live condition state, last-verified timestamps — stays gated behind attribution and rate terms.** And Place always retains its own consumer surface, because the verification flywheel (the Sunday push, the one-tap verdicts — [02-PRODUCT.md](02-PRODUCT.md)) is the moat's fuel and API callers don't generate it.

---

## 5. Structural vs. cosmetic advantages

| Advantage | Class | Why | Copy time for a funded competitor |
|---|---|---|---|
| Sensor bindings (place×activity → gauge + learned threshold, e.g. High Rocks ↔ 14210000 < 1,200 cfs) | **Structural** | Earned local judgment, in no corpus; tightened by every verification | Must re-forge per drainage, ~1 founder-year per metro |
| Verification log (claim→outcome pairs with auto condition snapshots) | **Structural** | Cannot be backfilled at any price; requires having been in-product when it happened | Cannot be bought; only accumulated |
| Calibrated confidence / per-claim-class decay | **Structural** | Decay parameters are learned *from* the verification log | Blocked without the outcome labels |
| Temporal ranking exhaust (condition vector × outcome at decision time) | **Structural** | Requires a temporal feed as the primary surface; static incumbents can't emit it | Requires a product pivot, not a feature |
| Substitution & pairing edges (QUIET_ALTERNATIVE_TO, PAIRS_WITH_IN_WINDOW) | **Structural (later)** | Learned from trip acceptances and co-visits; needs the usage exhaust first | Blocked without the usage data |
| Conditional taste graph (user × affordance × condition preferences) | **Structural (later)** | Worthless to a competitor without the condition layer to index into | Blocked without the condition layer |
| Watch exhaust (what a metro's households wait for, at what thresholds, with what activation — M7) | **Structural (later)** | A bookmark is silent; a watcher is a declared standing preference — requires the watcher base running | Blocked without watchers; cannot be surveyed into existence |
| Extracted claim layer (5,000–10,000 claims) | Cosmetic (the drawbridge) | Any 2027-class model + the same public corpus reproduces it in a weekend | ~1 weekend |
| Place database (~1,200 places) | Cosmetic | Commodity: OSM/GNIS/RIDB | ~1 day |
| NL search, Trip Builder, experience cards, feed UI | Cosmetic | A sprint for any competent team | ~1 sprint each |

**The implication, and it is an operating rule: never rest on cosmetic.** Every roadmap phase must end with more of the structural four ([05-ROADMAP.md](05-ROADMAP.md)'s moat checkpoints); a quarter spent polishing cards while the verification rate stalls is a quarter donated to AllTrails. The moat metric — **share of served claims backed by in-product ground truth**, with verification overtaking extraction within 12–18 months — is the scoreboard, not claim count and not UI parity.

---

## 6. The liability asymmetry

Scale forces suppression of exactly the highest-demand affordances. At Google's or AllTrails' volume, one drowning traceable to a recommendation is an existential legal and PR event, so their rational policy is categorical: no cliff jumps, no wild swimming endorsements, no snow-travel calls. The result is a demand vacuum — the queries people most want answered (swim holes, jumps, hot springs, minus-tide scrambles) are the ones incumbents are structurally forbidden to answer well. TikTok fills the vacuum with zero safety information, which is worse than silence.

Place handles the same risk at small scale **per-claim instead of per-category**, via the hazard gates ([01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)): a hazard-class affordance (cliff jump, wild swim, snow travel) surfaces only with a *recent* verification AND a currently-satisfied live condition trigger, always rendered with provenance, last-verified date, and assumption-of-risk framing — and every recommendation served logs its condition snapshot as an audit trail. "Verified 6 days ago at 410 cfs" is simultaneously the legal posture and the trust feature no incumbent can show. The asymmetry cuts both ways, though: one incident can kill a solo project, which is why ToS/waiver language is reviewed **before** launch and the gates are non-negotiable engineering, not policy prose.

---

## 7. Bright lines

1. **Never scrape AllTrails.** Litigation risk, structural dependence on the #1 threat, and it's hiking-only anyway — the corpus wouldn't even cover Place's differentiating categories. No exceptions, including "just difficulty ratings."
2. **WTA is a partner, never a target.** Washington Trails Association owns Washington's trip-report culture and covers the WA side of the Gorge (Dog Mountain, Dougan Falls). It is the planned metro-2 nonprofit data alliance for the Seattle expansion ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)); scraping it would burn the single most valuable partnership in the sector for a weekend of claims.
3. **Reddit via the official API only**, within free-tier limits pre-revenue; a Reddit data license is the first cost of revenue if monetization arrives. Corollary posture: store atomic claims + citation URLs, never republish source prose, no single source above 40% of claims — the legal center of gravity moves onto Place-owned verifications within 12–18 months regardless.
4. **Recreation.gov availability polling stays within published API terms.** The reservation family's availability watching runs on RIDB's published API under its stated terms and rate limits — no scraping the booking site, no synthetic-user tricks — and the family ships only after the terms review ([05-ROADMAP.md](05-ROADMAP.md) Phase 4). The paid tier's anchor cannot stand on a feed accessed at someone else's forbearance.

---

## 8. How Place dies

Honestly: the incumbents above mostly don't kill Place — inertia protects it from them for years. The real kill scenarios are fewer and closer to home. **(1) AllTrails ships extracted conditions before Place owns "right now" in even one metro** — the outflank window closes; this is why the seasonal launch dates (the October 2026 waterfall tool first, the swim tool 3 weeks before July 4, 2027) and the 150-dense-places depth bar outrank every other priority. **(2) The verification flywheel never ignites** — if the first 100 users don't hit 30% of visits verified, Place is just a cleverer scrape, and the drawbridge layer is replicable in a weekend; the Sunday push mechanics and the 10 named power verifiers are therefore not growth features but survival features. **(3) One safety incident pre-waiver, pre-gates** — a solo project has no legal ballast; the hazard gates and ToS review are launch blockers, not post-launch polish. **(4) MCP/LLM disintermediation without the tool position** — if LLM apps become the outdoor-discovery front door and Place isn't the callable substrate within 6 months, the interface layer captures the user and Place's consumer surface starves; ship the MCP server on schedule even if it feels premature. **(5) The bundle never coheres** — if cross-family watching feels like five point apps stapled together, households rationally keep the free single-family utilities plus one point subscription, and Place has rebuilt Campnab with worse focus (§3); one Almanac, one watcher list, one push voice, one Sunday ritual is survival design, not polish. Each scenario points at the same conclusion the moat table already forced: spend every scarce founder-hour on the structural four and the calendar dates that protect them, and let the cosmetic layer stay ugly for as long as it takes.
