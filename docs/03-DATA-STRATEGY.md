# Data Strategy — Seeding, Extraction & the Bindings Program

**In one breath:** Place seeds ~1,200 canonical Portland-polygon places from free government data, batch-extracts 5,000–10,000 provenance-carrying claims from ~150k cached community documents for ≤$200, and hand-forges ~100 sensor bindings (40 swim, 60 waterfall) that no corpus contains — growing to ~500 in year one, and feeding a family ladder ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)), not just outdoor tools. Extraction is scaffolding, deliberately disposable: within 12–18 months, in-product verification becomes the dominant support for served claims, moving the legal and competitive center of gravity onto data Place owns outright. We store facts with citations, never prose; we scrape no one who would sue or partner; and the whole program is written as a recipe so metro 2 (Seattle, via WTA partnership) reruns it in a season.

This document owns *where the data comes from and how it becomes trustworthy*. The schema those claims land in is [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); the pipeline's runtime architecture is [04-ARCHITECTURE.md](04-ARCHITECTURE.md); the seasonal launch calendar that consumes each dataset is [05-ROADMAP.md](05-ROADMAP.md).

---

## 1. Seed inventory

Three layers, in dependency order: the **skeleton** (canonical places — commodity, free, done once), the **flesh** (affordance and condition claims — extracted from community corpora), and the **pulse** (live sensor feeds — polled forever, stored as predicates not data). The skeleton must exist before extraction because entity resolution needs something to resolve *against*.

| Source | Access method | What it yields | Est. volume (Portland 90-min polygon) |
|---|---|---|---|
| **OpenStreetMap** | Overpass API queries by tag: `natural=waterfall`, `natural=hot_spring`, `natural=peak`, `tourism=viewpoint`, `leisure=swimming_area`, hiking route relations | Skeleton places with geometry + OSM IDs (one half of the crosswalk); trail relations feed AccessPoint candidates | ~600–800 places |
| **GNIS** (USGS Geographic Names) | Bulk file download, filter classes Falls, Summit, Spring, Lake | Canonical names + the other crosswalk half; catches named features OSM missed (many Gorge falls exist in GNIS only) | ~300–500 features |
| **RIDB** (Recreation.gov) | Free REST API, facilities + permit entries | Campgrounds, day-use sites, and **permit requirements as structured data** — captures the Multnomah Falls timed-use permit as a machine-readable access constraint, not a footnote | ~150 facilities |
| **USFS FSGeodata** | Public geodata downloads (Mt. Hood NF + CRGNSA trailhead layers) | AccessPoints: trailheads and parking — where you actually go, distinct from the place itself | ~200 access points |
| **Reddit** (r/Portland, r/oregon, r/PNWhiking, r/OregonCoast) | **Official API only**, within free-tier limits pre-revenue | The affordance gold: "we cliff-jumped at High Rocks in July," "Tamanawas was roaring after that storm" — dated first-person experience reports | ~100k posts + comments |
| **Oregon Hikers** (field guide + forum) | Fetch respecting robots.txt; field guide is a community wiki, forum is dated trip reports | Field guide: dense per-place facts (bridges, fords, seasonal access). Forum: two decades of dated trip reports — the region's richest `observed_date` corpus | ~50k documents |
| **NOAA CO-OPS, USGS NWIS, SNOTEL, NWAC, AirNow, Open-Meteo/NWS** | Free public APIs, polled by the condition evaluator ([04-ARCHITECTURE.md](04-ARCHITECTURE.md)) | The **live layer** — not documents to extract but feeds that ConditionWindow predicates execute against: tides, streamflow, snowpack, avalanche danger, air quality, forecasts | ~40 distinct stations/feeds referenced at launch; grows with bindings |

Total: **~1,200 skeleton places** and **~150k source documents** — this document is the owner of those two constants. Losing alternatives, one line each: Google Places API lost (commercial POI schema, cost, ToS restrictions on storing results); AllTrails lost (bright line — see §5); Instagram/TikTok lost (no API access worth having, undated content, geotag suppression trends).

Every fetched document is **cached raw and permanently** in object storage. This is the single most leveraged storage decision in the company: the corpus appreciates, because re-running a better model over the same cache yields denser claims at lower cost (§2, re-extraction).

## 2. The extraction pipeline, end to end

Five stages. Nothing skips a stage; nothing auto-publishes.

**Stage 1 — Fetch.** Per-source fetchers write raw documents to the cache with `{source, url, fetched_at, robots_ok}`. Reddit through the official API; Oregon Hikers throttled and robots.txt-compliant. Fetchers are dumb on purpose — all intelligence lives downstream, so a fetcher for a new source in metro 2 is an afternoon of work.

**Stage 2 — LLM extraction (provider-pluggable).** Each document goes through an LLM extractor with the **frozen claim JSON schema**. The provider is a config switch (`EXTRACTION_PROVIDER`), and every claim's `extractor_version` records which provider/model produced it, so providers can be changed or mixed without corrupting re-extraction diffs.

> **Decision update (2026-07-04):** pre-revenue, the default provider is **DeepSeek v4 Pro** (`deepseek-v4-pro`: $0.435/M input, $0.87/M output, automatic prefix caching, no batch API — runs as a concurrency-limited loop), which prices the seed run at **~$35** instead of ≤$200. The founder switches to the committed Anthropic path (Haiku-class on the batch API, below) once revenue starts, by setting `EXTRACTION_PROVIDER=anthropic`. Quality gates are unchanged either way: nothing auto-publishes, the review queue and the ≥2-source/verification gates catch extraction errors regardless of extractor, and calibration data per claim-type will tell us empirically whether the cheaper extractor's precision costs more founder review time than it saves in dollars.

```json
{
  "place_ref": "the falls past the second bridge on Eagle Creek",
  "activity": "wild-swim",
  "claim_type": "(class vocabulary owned by 01-EXPERIENCE-GRAPH.md's claim_class enum)",
  "condition_text": "pool deep enough to jump mid-June through September",
  "observed_date": "2019-07-14",
  "verbatim_quote": "…we jumped from the ledge on the right, water was perfect…",
  "source_url": "https://www.oregonhikers.org/forum/…",
  "self_confidence": 0.72
}
```

Two fields are load-bearing. `observed_date` is **when the experience happened, not when it was posted** — a 2014 trip report about a rope swing is a decayed access claim, not a fresh one; the confidence model in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) runs on this date. `verbatim_quote` is minimal evidence held internally for review and audit, **never republished** (§5). The schema is frozen so that claims extracted in 2026 and claims re-extracted in 2028 are row-compatible.

**Cost math.** ~150k documents × ~400 tokens average ≈ **60M input tokens**. At Haiku-class batch pricing with structured, cacheable system prompts, the full corpus extracts for **≤$200 one-time** (~$35 on the pre-revenue DeepSeek default); the incremental crawl (new Reddit threads, new forum posts) runs **~$20/month** (single-digit dollars on DeepSeek). This is why the strategy exists at all: structured extraction at this scale was simply not feasible pre-LLM. That the same $200 is available to a competitor is fine — the extracted layer is the drawbridge, not the moat (§4).

**Re-extraction as models improve.** Every claim stores `extractor_version`. When a materially better model ships, the cached corpus is re-run (another ≤$200-class spend), new claims diffed against old, and improvements flow through the same review queue. The corpus is bought once and harvested repeatedly — extraction quality compounds *without new data acquisition*.

**Stage 3 — Entity resolution.** The model's `place_ref` is free text; the graph needs a canonical place. Resolution is embedding-assisted against the OSM/GNIS crosswalk: embed `place_ref` plus surrounding document context, nearest-neighbor against embedded place records (names, alternate names, containing drainage, nearby trail names), then rerank with hard signals (distance along the named watercourse, elevation sanity). The canonical hard case: **"the falls past the second bridge on Eagle Creek"** — no name, but "Eagle Creek" pins the drainage, "second bridge" is a known trail landmark in the Oregon Hikers field guide, and the candidate set collapses to a single canonical candidate. Matches below the confidence bar go to the human queue rather than guessing; a claim attached to the wrong waterfall is worse than a discarded claim. Ambiguous refs that repeatedly fail resolution are themselves a signal — they name places the skeleton is missing.

**Stage 4 — Review queue.** A single founder-facing queue (highest-value claims first: hazard class, high-traffic places, binding candidates). The founder approves, corrects, merges, or rejects. Pre-launch this is hours per week, not a job — 5,000–10,000 claims arrive over months, and most are corroborations that batch-approve.

**Stage 5 — Publication gates.** Exactly as committed in the graph doc: no single LLM extraction ever auto-publishes. Standard claims need **≥2 independent sources** or a founder/user verification. **Hazard-class affordances** (cliff-jump, wild-swim, snow travel) additionally require a *recent* verification AND a currently-satisfied live condition trigger before they render — and they always render with provenance, last-verified date, and assumption-of-risk framing. The gate doubles as the trust feature: "verified 6 days ago at 410 cfs" is the line no incumbent can print.

## 3. The bindings program

This is the section that matters most, because it is moat M1 in [00-THESIS.md](00-THESIS.md)'s moat stack: the layer that **appears in no corpus** and therefore cannot be extracted, scraped, or bought.

**What a binding is.** A binding is the join between a specific affordance and a specific public sensor, with a learned threshold: *"High Rocks is swim-safe when USGS gauge 14210000 (Clackamas @ Estacada) reads below 1,200 cfs."* The gauge is free. The knowledge that *this* gauge governs *that* pool, and *that number* is the line between a great afternoon and a drowning risk — that is earned local judgment. Nobody has ever written it down, so no model can extract it. A copycat gets the same feeds and none of the joins.

**Why it is the moat.** Everything else in this document is replicable: a 2027-class model re-runs Reddit in a weekend and clones the claim layer. Bindings are not in Reddit. They are forged in the field, one drainage at a time, and then — the compounding part — **tightened by every verification**: a user reporting "sketchy at 700 cfs" narrows the safe bound below the founder's initial 1,200 cfs hypothesis. The binding gets more precise with use, and the precision lives in Place's verification log, which cannot be backfilled at any price (moat M2).

**How a binding is forged** — the standard five-step sequence:

1. **Anecdote.** Extraction surfaces dated condition language: "Clackamas was way too pushy for the kids last weekend" (June, high-snowmelt year), "perfect at High Rocks by late July."
2. **Candidate gauge.** Pick the governing sensor by hydrology: same watercourse, upstream of the site, no major confluence in between. High Rocks → **14210000 Clackamas @ Estacada**. Sandy River sites → **14137000 Sandy @ Bull Run**.
3. **Threshold hypothesis.** Join the anecdotes' `observed_date`s against the gauge's historical record (USGS NWIS serves decades of daily values, free). "Too pushy" dates cluster above ~1,800 cfs; "perfect" dates sit under ~1,000. Hypothesize the line at 1,200 cfs.
4. **Founder verification.** Drive there. The founder is verifier #1 — this is why the wedge must be where the founder lives ([05-ROADMAP.md](05-ROADMAP.md), transposition rule). Check the pool at a known flow, log a founder-verified claim with the conditions snapshot. The top 30–50 places get this treatment as the gold calibration set.
5. **Verification tightening.** Publish behind the hazard gate. Every subsequent one-tap Sunday verdict arrives with an auto-attached flow snapshot; each confirms, refutes, or narrows the threshold. The binding converges from a founder's estimate to a community-calibrated instrument.

This five-step sequence is the **template every window family instantiates** — a new family is one adapter class plus this exact forging loop run against its own feeds ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) §1); the per-family data specifics are §7 below.

**The launch 100.** Committed composition, per [00-THESIS.md](00-THESIS.md)'s canonical numbers:

- **40 swim-hole bindings** on the Clackamas/Sandy corridors, bound to gauges **14210000** and **14137000** (flow thresholds, plus water-temp where the gauge reports it). These power the "Swim Portland" tool — shipping **3 weeks before July 4** (June 2027, per the re-sequenced calendar in [05-ROADMAP.md](05-ROADMAP.md)).
- **60 Gorge waterfall bindings**, bound to **72-hour NWS precipitation** plus creek gauges where they exist (most Gorge creeks are ungauged; precipitation-in-drainage is the honest proxy, and the binding records which kind it is). These power the October 2026 "waterfalls ranked by current flow" tool — public launch #1 ([05-ROADMAP.md](05-ROADMAP.md)).

Forging pace is the real constraint: steps 1–3 are desk work (a day per drainage, batched); step 4 is founder field time, committed across two seasons ([05-ROADMAP.md](05-ROADMAP.md)): ~60 waterfall bindings forged August–September 2026 ahead of the October launch, and ~40 swim bindings forged July–September 2026 as the private, founder-only exercise on the Clackamas/Sandy corridor — never a public launch — then tightened again in spring 2027 before Swim Portland ships. 100 bindings is roughly 25 field days — feasible for one person across those seasons, which is exactly why the number is 100 and not 1,000.

**The year-one 500.** Growth to ~500 bindings follows the seasonal cadence, each season adding a *binding type* and reusing all prior infrastructure: April adds bloom-state bindings (Dog Mountain balsamroot, Tom McCall — calibrated on growing-degree-day proxies from Open-Meteo plus verification reports, since no government sensor measures wildflowers); winter adds SNOTEL snowpack and NWAC danger-rating bindings for snowshoe affordances; the coast adds NOAA CO-OPS tidal bindings (Haystack Rock tide pools at minus tides). Marginal cost falls every season because the evaluator, the predicate DSL, and the forging recipe already exist. Verification-tightened bindings — not claim count — are the acquisition-grade asset.

## 4. The verification-overtake plan

Extraction is scaffolding. The plan is for it to be *demoted*, on schedule.

At launch, nearly 100% of served claims are supported by LLM extraction (gated per §2). Each Sunday push converts visits into `Verification` rows — claim→outcome pairs with conditions attached. Verified claims outrank extracted ones in feed scoring, so the product naturally routes attention toward the ground-truthed subset, which attracts more verification: the flywheel.

**The moat metric — tracked weekly on the founder dashboard from day one:** *percentage of served claims backed by in-product ground truth.* Target trajectory: verification overtakes extraction as the dominant support for served claims within **12–18 months of launch**. Intermediate gates ([05-ROADMAP.md](05-ROADMAP.md)): 30% of tracked visits verified in the first 100 users; 20+ verifications/day and 5+ user-submitted claims/week at 1,000 users. The 10 named power verifiers (recruited from r/Portland and Oregon Hikers, paid in early access and named provenance credit) exist to make the early curve non-flat.

The overtake matters twice. **Competitively:** once verifications dominate, copying Place's inputs (the same public corpus, the same $200 extraction) no longer reproduces Place's outputs — the ranking is trained on outcomes only Place witnessed. **Legally:** the center of gravity moves off third-party-derived facts onto first-party data Place owns outright, shrinking source risk (§5) on the same 12–18 month clock. Extraction never stops — the $20/month crawl keeps feeding candidates — but it becomes the *nomination* mechanism, while verification becomes the *support* mechanism.

## 5. Source risk & legal posture

**Facts with provenance, never prose.** Place stores atomic claims plus citation URLs. Facts are not copyrightable; expression is. The `verbatim_quote` field is minimal internal evidence for review and audit and is never rendered in any user-facing surface. Citations link back to sources — Place sends traffic to Oregon Hikers, not the reverse of value.

**Concentration cap: no single source >40% of claims.** Enforced as a pipeline metric, not an aspiration. If Reddit approaches the cap, the crawl rebalances toward Oregon Hikers and user submissions. The cap ensures no license negotiation, API change, or takedown can hole the graph below the waterline.

**Reddit: official API, and the license is the first cost of revenue.** Pre-revenue, Place stays within the free tier of the official API — defensible, rate-limited, honest. The committed decision: **the day Place monetizes, a Reddit data license is the first line item in cost of revenue.** Not a contingency — a plan. It converts the largest source risk into a vendor relationship, priced after the verification overtake has already made Reddit-derived claims a shrinking minority.

**Bright lines.** **Do not scrape AllTrails** — ever. Litigation risk, structural dependence on the primary competitor, and their corpus is hiking-only, which is precisely the key Place breaks out of ([06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)). **WTA is a partner, never a target** — their trip-report corpus covers the Washington side of the Gorge today and anchors metro 2 tomorrow; scraping them would burn the single best expansion asset in the region. **Recreation.gov polling stays within published API terms** — the reservation family's availability poller (§7) ships only after the terms-of-use review it requires, and never exceeds documented limits.

**Hazard posture.** Per the requirements in [02-PRODUCT.md](02-PRODUCT.md) §5: hazard claims carry stricter gates, every served recommendation logs its conditions snapshot (the audit trail if anything goes wrong), ToS and waiver language are reviewed before the first public tool ships ([05-ROADMAP.md](05-ROADMAP.md) Phase 1) and re-reviewed before the swim tool, and the sensitive-sites exclusion list plus parking-full downranking are pipeline features, not editorial afterthoughts.

## 6. The per-metro replication playbook

The Portland program above, written as the recipe it is. One season, one person (or one local partner), in order:

1. **Select the metro** by the transposition criteria: condition-density of experiences, unguarded community corpus, incumbent discovery gap, year-round seasonal variety — and a local verifier-in-chief who lives there. The bindings are local judgment; step 8 cannot be done remotely.
2. **Build the skeleton**: run the standard Overpass tag queries, GNIS class filters, RIDB facility pull, and the relevant USFS/state-lands trailhead layers for the 90-minute drive polygon. Target ~1,200 places. (~1 week, mostly automated.)
3. **Identify the corpus**: the metro's Reddit subs plus its Oregon-Hikers-equivalent — every outdoor metro has one dominant community archive. Fetch via official APIs / robots.txt-compliant crawl into the permanent cache. (~150k docs.)
4. **Run extraction** with the frozen schema and current extractor version. Budget ≤$200 batch, ~$20/month incremental. Entity-resolve against the new crosswalk; triage the review queue.
5. **Forge the first ~100 bindings** using the five-step sequence in §3, prioritized by the metro's sharpest seasonal pain (Portland's was summer swim flow; a Salt Lake analogue might be canyon-stream flow or snowpack).
6. **Ship the seasonal tool AND its watchables, not the app**: one free, no-login, condition-ranked tool timed to the metro's peak seasonal question, posted where that question is perennially asked — and publish the tool's bindings as watchables, composing the metro's starter Almanac one seasonal shelf at a time ([09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md)). Losing alternative, one line: launching the full discovery app first — nothing to rank yet, no reason to share it.
7. **Recruit ~10 named power verifiers** from the same communities; instrument verification from the first user.
8. **Founder/partner hand-verifies the top 30–50 places** as the gold calibration set; hold the depth bar — **150 dense, condition-wired places beat 400 shallow ones**.
9. **Expand on the quality gate, not the calendar**: the next seasonal tool ships when the current one meets the verification and feed-quality gates ([05-ROADMAP.md](05-ROADMAP.md)).

**Metro 2 is Seattle, and it runs steps 3 and 7 differently.** WTA's trip-report corpus is the best in North America, and it is not scraped — it arrives via a **nonprofit data alliance**: attribution and traffic to WTA, structured conditions and verification signal back to their community, formalized before a single WTA page is fetched. The partnership replaces the cold-corpus crawl AND seeds the power-verifier bench from WTA's existing reporter culture — which is why metro 2 should run *cheaper and faster* than metro 1, not merely as fast. Every subsequent metro then chooses: Portland-style (open corpus, crawl) or Seattle-style (guarded corpus, partner). The playbook supports both.

## 7. Per-family adapter appendix

One short spec per upcoming family — the feeds and adapter deltas that instantiate §3's forging template beyond outdoor. The doctrine, admission gates, and sequencing live in [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md); this appendix owns only the data-side answer: *what do we poll, and what does it cost?* In every family that ships, the answer is free feeds, existing machinery, and at most one new adapter.

**Sky.** NOAA SWPC (Kp index / OVATION aurora oval) + Open-Meteo cloud cover + the existing sun/moon ephemeris adapter. **One new adapter** (SWPC); the other two feeds already run. Threshold work is thin — physics does most of it — so sky's forging season is desk work plus a few field nights, which is why it climbs the ladder first.

**Harvest.** Growing-degree-day proxies computed from Open-Meteo — **the April 2027 bloom tracker pioneers this binding type** (§3, the year-one 500) — plus first-rain precipitation-accumulation triggers: the chanterelle flush is the same `agg: sum` DSL machinery as the waterfall bindings, zero new evaluator code. U-pick crop calendars arrive through the standard extraction pipeline (§2). No new adapter; one new computation over an existing feed.

**Reservation.** Recreation.gov availability polling — **a genuine gap, named honestly:** the RIDB facilities adapter exists (§1), but the availability poller does not. Cancellations perish in minutes, not hours, so this family needs three things no other family does before a single watcher ships: a **fast-lane polling cadence** separate from the evaluator's standard sweep, a **push-latency SLO**, and a **terms-of-use review** ([05-ROADMAP.md](05-ROADMAP.md) Phase 4). The bright line from §5 governs: polling stays within published API terms.

**Health.** AirNow **already runs** — it gates outdoor cards today — and heat index arrives through the existing NWS/Open-Meteo forecast adapter: zero new adapters for the smoke-and-heat seed. **Pollen fails the free-feed gate today, stated plainly:** there is no free federal pollen feed, and both alternatives — scraped counts and paid APIs — violate the burn discipline this document is built on. Pollen waits for a real feed; the family ships without it.

**Crowd.** Exhaust-derived, and therefore last: no free machine-readable crowd feed exists, so the eventual feed is Place's own verification exhaust — parking-full verdicts accumulating until crowd state is derivable from data only Place holds. **Place becomes the sensor.** Until then, crowd priors annotate cards but no crowd watchable publishes ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F6).

## 8. Catalog curation gates

A watchable publishes to the Almanac only if three things hold: its **predicate is executable** — the DSL runs it against a live feed today, not aspirationally; its **threshold is sourced or founder-verified** — a citation trail or a field visit, never a guess; and its **expected open-frequency is stated from a backtest against 5 years of historical feed data**. The backtest is cheap — USGS and NOAA serve decades of history free, so replaying a predicate across the last five years is an afternoon of tooling, not a data purchase — and it is the honesty feature: "opens ~6×/winter" is printed on the watchable before the first user watches it. Full spec in [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md); the backtest tooling is a Phase 1 deliverable ([05-ROADMAP.md](05-ROADMAP.md)).
