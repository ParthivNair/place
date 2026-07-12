# Window Families — The Doctrine & the Admission Test

**In one breath:** A window family is one adapter class plus a set of forged bindings sharing feeds and a verification story — nothing more, and that invariant is the whole doctrine: **if adding a family requires touching the predicate DSL, the evaluator loop, the watcher machinery, or the push path, it is not a family, it is a different product, and we don't build it.** Six families are named — outdoor (built), sky, harvest, reservation, health, crowd — and none ships by enthusiasm: each must pass a five-gate admission test (free machine-readable feed; verified local threshold that beats a national default; genuine perishability; a one-tap verification story; a holdable metro depth bar), and this document says plainly which families fail which gates today. The ladder climbs one family per season on the calendar in [05-ROADMAP.md](05-ROADMAP.md), because the horizontal is a ladder, not a sprawl.

Vocabulary (window, family, watchable, watcher) per [00-THESIS.md](00-THESIS.md) §8; the Almanac these families populate is [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md); the adapters and forging program are [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)'s to specify.

---

## 1. The invariant

The engine — predicate DSL, evaluator sweep, watchers, push, confidence math, review queue — is **family-agnostic and frozen**. A new family adds exactly two things:

1. **An adapter class**: one subclass of the feed-adapter contract that knows how to poll a new public source into `feeds`/`feed_readings`. An afternoon of code.
2. **Bindings**: the forged joins — which feed governs which watchable, at what threshold — via the same five-step sequence (anecdote → candidate feed → threshold hypothesis → founder verification → verification tightening) committed in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §3. A season of judgment.

The judgment is the expensive part, and that is the point: horizontal expansion never leaves the moat's home turf, because every rung of the ladder is built from M1 bindings and tightened by M2 verifications ([00-THESIS.md](00-THESIS.md) §3). A competitor can copy the family *list* in a press release; they cannot copy a family's thresholds without re-forging them locally, one metro at a time.

## 2. The admission test

Five gates. A family ships in a metro only when all five hold **in that metro** — the test is a gate, not a vibe, and it re-runs per metro because gate 2 and gate 5 are local by construction.

| # | Gate | The question it answers |
|---|------|------------------------|
| G1 | **A free, machine-readable feed exists** (or Place's own exhaust provides one) | Can the evaluator actually poll this, at <$50/month total burn? |
| G2 | **A verified local threshold beats a national default** | Is there judgment to forge, or would we be a generic frontend on someone else's number? |
| G3 | **The window genuinely perishes** | Does missing it cost the user something felt — a wasted drive, a gone campsite, a missed bloom? Hours-to-weeks clocks only. |
| G4 | **A one-tap verification story exists** | Can a user tighten the threshold in one second? (No verification story → no M2 accrual → fails the "not a review site" refusal.) |
| G5 | **The metro depth bar is holdable** | Are there enough forgeable watchables here to be dense, not token? 150-dense-beats-400-shallow transposes per family × metro. |

A family that fails a gate waits, and the doc that proposes waiving a gate is proposing to spend founder-hours on something that doesn't compound. The founder-hour question from [00-THESIS.md](00-THESIS.md) §6 applies to families exactly as it applies to features.

## 3. The six families

### F1 — Outdoor (built; the founding family)

- **Feeds:** USGS NWIS, NOAA CO-OPS, SNOTEL, NWAC, NWS/Open-Meteo, AirNow, sun/moon — all live in the adapter fleet today.
- **Threshold source:** the bindings program in full — corpus anecdotes, gauge history, founder field verification. The M1 archetype.
- **Hazard class:** yes — wild_swim, cliff_jump, snow_travel carry the strictest publication gates in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §4, unchanged.
- **Verification story:** the Sunday one-tap verdict with auto conditions snapshot — the original.
- **Seasonality:** year-round by design; the seasonal-tool cadence is this family's GTM.
- **Metro portability:** the [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §6 playbook, proven first.
- **Admission test:** passes all five, definitionally — the test was reverse-engineered from what made this family work.

### F2 — Sky (first expansion; ships Phase 3 winter)

- **Watchables:** aurora reaching this latitude; clear-dark stargazing nights (new-moon × clear-sky × real darkness); meteor-shower peaks worth the drive; photographers' light (golden hour × Gorge fog).
- **Feeds:** NOAA SWPC (Kp index / OVATION aurora oval), Open-Meteo cloud cover, the existing sun/moon ephemeris adapter. One new adapter (SWPC); two already running.
- **Threshold source:** mostly physics plus thin-but-real local judgment: *where* is dark enough, which sightlines clear north, which viewpoints beat which for a 2 a.m. drive. Forged in desk-plus-a-few-field-nights, not seasons.
- **Hazard class:** none — the family is hazard-free, which is exactly why it goes first.
- **Verification story:** "Did you see it?" — confirm / refute with the Kp and cloud snapshot auto-attached. Clean G4.
- **Seasonality:** winter-strong (long nights), which plugs the outdoor family's thinnest season — January's feed gets live reasons the year the Watcher MVP ships.
- **Metro portability:** near-total; SWPC is continental, ephemeris is universal, only the dark-site list is local.
- **Admission test:** passes all five today. G2 is the thinnest pass (physics does much of the work), which is why sky is a *first expansion*, not the moat's center.

### F3 — Harvest (seeded by the April 2027 bloom tracker; full in fall 2027)

- **Watchables:** first larch weekend; balsamroot peak; fall color by elevation band; u-pick strawberries/berries ripe; the chanterelle flush after the first 2-inch October rain.
- **Feeds:** Open-Meteo growing-degree-day proxies (the April bloom tracker pioneers this binding type on the existing adapter), precipitation accumulation windows (already in the DSL — same `agg: sum` machinery as waterfalls), plus community claims through the extraction pipeline.
- **Threshold source:** corpus extraction + verification tightening — the GDD-vs-bloom-date join is forgeable from years of dated trip reports, then tightened by "were they at peak?" verdicts. Textbook M1.
- **Hazard class:** no, but a **dispersal class**: foraging spots inherit the sensitive-sites posture ([02-PRODUCT.md](02-PRODUCT.md) §5) — chanterelle watchables name *conditions and regions*, never pins. The Blue Pool rule applies to mushrooms more than to anything else in the product.
- **Verification story:** "At peak / early / done?" — the bloom tracker's exact verdict set, generalized.
- **Seasonality:** April–November arc, complementing sky's winter.
- **Metro portability:** high — every metro has a bloom, a berry, a foliage line; the GDD method transposes wholesale.
- **Admission test:** passes G1–G4 today; G5 is met at the *watchable* level (a dozen dense harvest watchables per metro is plenty — this family is depth-per-watchable, not breadth).

### F4 — Reservation (the paid anchor; adapter build starts Phase 4, ships with the Phase 5 paid launch)

- **Watchables:** campsite cancellations at named, demand-ranked campgrounds ("Timothy Lake under $30, any July weekend"); permit drops; timed-entry releases (the Multnomah permit is already in the graph via RIDB).
- **Feeds:** Recreation.gov availability via RIDB — the ingest adapter exists for facilities; the **availability poller is a genuine gap** ([05-ROADMAP.md](05-ROADMAP.md)): cancellations perish in minutes, so this family needs a fast-lane cadence, a push-latency SLO, and a ToS review before a single watcher ships. Named honestly, not hand-waved.
- **Threshold source:** demand-side judgment rather than safety-side: *which* campgrounds and permit lotteries are worth watching, at what price and lead-time bands — curated first from corpus and founder knowledge, then priced by watch exhaust (M7). G2 holds, but its character differs from F1's, and the doc says so.
- **Hazard class:** none.
- **Verification story:** the outcome is observable in-band — the user taps "got it / gone before I could book," which measures push latency and watchable hit-rate directly. Cleanest G4 in the product.
- **Seasonality:** year-round with a summer spike — peaking exactly when the Phase 5 paid launch lands.
- **Metro portability:** total — Recreation.gov is national, and every metro's Almanac gets a reservation shelf.
- **Admission test:** passes G2–G5 today; **G1 is conditional** on the availability poller and terms review. It is also the family with externally proven willingness to pay (Campnab-class utilities charge $10–30/month for this alone), which is why it anchors the paid tier rather than launching it early: the bundle beats the point-app on price *and* on being one habit instead of five.
- **Refusal boundary, restated from [00-THESIS.md](00-THESIS.md) §7:** watching a cancellation is not booking it. Place pushes; the user transacts on Recreation.gov. No inventory, no booking payment, no auto-booking, ever.

### F5 — Health (opportunistic; smoke seed in the Phase 5.5 window)

- **Watchables:** first smoke-free morning after a bad stretch; heat-safe kid hours this weekend; (later) low-pollen mornings.
- **Feeds:** AirNow — **the adapter already runs** for outdoor gating; NWS heat index via the existing forecast adapter. **Pollen fails G1 today**: there is no free federal pollen feed, and the options (scraped counts, paid APIs) both violate the burn discipline — so pollen waits, stated plainly.
- **Threshold source:** mostly national standards (AQI bands) with thin local judgment (which neighborhoods clear first, inversion behavior) — the weakest G2 in the ladder, which caps this family's Almanac footprint at a few honest watchables rather than a surface.
- **Hazard class:** no, but health claims get conservative copy — Place states readings and thresholds, never medical advice.
- **Verification story:** thin — the feed is itself ground truth, so verdicts add little. G4 is the second weakness, and it is why health is a seed, not a shelf: sensor-derived claims already carry the highest source prior in the confidence model, and a family that can't accrue M2 stays small by rule.
- **Seasonality:** smoke season (Aug–Oct) sells it; the watchable earns its keep two months a year and costs nothing the other ten.
- **Metro portability:** total for smoke and heat (AirNow and NWS are national).
- **Admission test:** smoke and heat pass G1/G3/G5 and scrape through G2/G4 at seed size; pollen fails G1 outright. The family ships small and stays small until either gate strengthens.

### F6 — Crowd (last; only when exhaust supports it)

- **Watchables:** "Multnomah before the mob"; the pumpkin-patch weekday window; trailhead lots with room at 10 a.m.
- **Feeds:** **fails G1 today** — no free machine-readable crowd feed exists. The eventual feed is Place's own verification exhaust: parking-full verdicts accumulating under M2/M4 until crowd state is *derivable*, which converts G1 from "poll someone else's sensor" to "become the sensor." Until then, crowd priors annotate cards ([07-USERS.md](07-USERS.md) §1) but no crowd watchable publishes.
- **Threshold source:** exhaust-calibrated (visits × verdicts × time-of-day), the purest expression of "data only a live operator can hold."
- **Verification story:** already running — parking-full is an access-class verdict today.
- **Admission test:** fails G1, waits, and this document is the record of that decision. Sequencing crowd last is not caution; it is the only honest reading of the gates.

## 4. Sequencing rationale

The ladder order — sky, harvest, reservation, health, crowd — is not taste; it falls out of three constraints:

1. **Seasonal fit.** Sky lands in the Watcher MVP's first winter, when outdoor windows are thinnest and the feed needs live reasons ([05-ROADMAP.md](05-ROADMAP.md) Phase 3). Harvest's full arc lands in fall. Reservation peaks with summer camping demand — the Phase 5 paid launch. Health waits for smoke season. Every family debuts in the season that sells it, exactly as the seasonal-tool cadence always has.
2. **Risk ordering.** Hazard-free and verification-clean families (sky) ship before families with real operational risk (reservation's latency SLO) or thin verification (health). The paid tier launches on the family with *proven* willingness to pay, after two free families have exercised the watcher machinery.
3. **Moat accrual.** Each family must deepen M1/M2/M7 before the next opens — a family that stops accruing (health at seed size) stays small, and the family that needs exhaust (crowd) waits for it. The expansion gate doctrine from [05-ROADMAP.md](05-ROADMAP.md) — quality bars, never calendar pressure — applies to rungs of this ladder exactly as it applies to metros.

## 5. What this doctrine forbids

Restating [00-THESIS.md](00-THESIS.md) §7's guardrails as operating rules for anyone proposing family #7:

- **No user-authored predicates.** The Almanac is curated; the threshold is the product. The moment users write their own predicates, Place is IFTTT with a nicer font and no moat.
- **No family without a verification story** (G4 is not waivable — it is the "not a review site" refusal wearing an engineering hat).
- **No family on paid or scraped feeds.** G1 says *free and machine-readable*; the burn discipline is load-bearing ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)).
- **No family shipped wide.** Every family enters as a handful of dense, backtested watchables in one metro ([09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md) owns the curation gates) and earns its shelf.
- **No family that re-keys the product.** Windows over joins of public feeds and verified thresholds — never raw feed rebroadcast (weather app), never price surfaces (deal tracker), never someone else's transaction path (booking).

One adapter class, one season of judgment, five gates — that is what a rung of the ladder costs, and the price is the strategy.
