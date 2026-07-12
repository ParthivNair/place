# Product Spec — The Weekly Ritual, the Almanac & the Vigilance Tier

**In one breath:** The weekly ritual survives the reframe untouched — a Thursday "This Weekend" feed ranked by live conditions, a Saturday trip, and one Sunday-6pm push that is *simultaneously* the verification prompt and the re-engagement prompt — but the product around it grows from four surfaces to **five** and gains its paid tier. The five: the **Good Now feed** (the free everyday layer), **the Almanac** (browse this metro's watchables by family, one-tap Watch), **the watcher list** (standing queries in three states: watching / open / recently closed), **claim-based place and window pages**, and **the Sunday push**. The paid unit is **Vigilance**: the free tier browses everything with no login to read and holds two starter watchers; the household tier holds unlimited watchers with guaranteed delivery, anchored by the reservation family — Place's prices live in §3 of this document and nowhere else in the canon. The launch shape is unchanged — free, no-login seasonal tools (the October 2026 waterfall ranker first; Swim Portland in June 2027, sequencing per [05-ROADMAP.md](05-ROADMAP.md)) — except every tool is now an **Almanac seed** whose call to action is *"Watch this — we'll tell you when it's going off."* Everything else — Trip Builder, social, badges, NL search, creator economy, native apps — stays deferred with a stated reason. Success is measured in weekly-active-planners, 4-week streaks, a ≥30% verification rate, active watchers per household, and paying households, because verifications, not users, are the asset — and a paid push manufactures verification ([00-THESIS.md](00-THESIS.md) §5).

Vocabulary (window, window family, watchable, watcher, the Almanac, Vigilance) is fixed in [00-THESIS.md](00-THESIS.md) §8; the schema and confidence math live in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); family doctrine and the admission test in [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md); the Almanac's curation gates in [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md); the pipeline that fills the feed is [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); the systems that serve it are [04-ARCHITECTURE.md](04-ARCHITECTURE.md).

---

## 1. The core loop: own the episodic cadence

Outdoor recreation is episodic. People do not open an outdoors app on Tuesday at lunch; they plan Thursday night, go Saturday, and recover Sunday. Every incumbent fights this cadence with engagement mechanics. Place commits to it and builds the whole product on a three-beat week:

**Thursday evening — the "This Weekend" feed.** Ranked experience cards for the next 48–72 hours, most carrying a live, provenance-backed reason they rank *now* (the ≥60% quality gate, Surface 1): "Tamanawas Falls flowing hard: 1.6 in rain in 72 h," "Balsamroot peaking on Dog Mountain: 3 reports this week," "High Rocks swimmable: Clackamas at 980 cfs (gauge 14210000), verified 6 days ago at 1,010 cfs." The provenance line is load-bearing, not decoration — it teaches the user in one glance that the app *knows things* a static database cannot, and it turns every card into an implicit claim the user can verify after their visit.

**Saturday — the trip.** Tapping "I'm going" on a card records trip intent and snapshots the conditions the recommendation was served under (flow, temp, forecast, tide — logged automatically, per §5's requirement that every served recommendation logs its conditions). No check-in, no tracking, no GPX. The tap is the entire ask.

**Sunday 6:00 pm — the push.** One notification, hard-capped at one per week. It asks at most **two one-tap questions** about the place the user said they were going to — drawn from that place's claims ranked by *lowest confidence × fastest decay* (the two claims whose answers are worth the most, per the decay model in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) — and the same notification surfaces next weekend's top feed card.

The reframe adds one aperiodic beat on top: the **window-open push** from a watcher (Surface 3), which arrives whenever a watched window opens, because windows do not keep office hours. It rides outside the weekly cadence by construction and by consent — the household asked Place to watch — and it is the only thing that does.

### The sharpest insight, stated plainly

**The verification prompt and the re-engagement prompt are the same notification.** In an episodic category you get roughly one push per week before you're muted, so the action that builds the moat (a verification verdict) and the action that drives retention (opening next weekend's feed) must be one tap apart, in one message. This is not a growth hack bolted onto a data pipeline; it is the product's central mechanism.

And it works only because the questions are about **claims, not places**. "Was the pool swimmable?" is a one-second yes/no favor — the user knows the answer instantly and answering feels like helping the next person. "How was it?" is a request for a review, and reviews are chores; one-tap claim verdicts are favors. Place never asks "how was it?" anywhere in the product.

*Losing alternative:* daily-engagement mechanics (streaks, daily digests, push-per-condition-change) — they fight the category's natural rhythm and burn the one weekly notification budget we have.

---

## 2. The five surfaces

The product is a PWA — installable, push-capable, no app-store gate, one codebase (Next.js, per [04-ARCHITECTURE.md](04-ARCHITECTURE.md)). All five surfaces are live by the end of the Phase 3 Watcher MVP ([05-ROADMAP.md](05-ROADMAP.md)): the feed, pages, and Sunday push carry over from the original four-surface spec; the Almanac and the watcher list are what the Watcher MVP adds. *Losing alternative:* native apps — two more codebases for zero additional moat; deferred (§6), with the honest caveat that §3's delivery telemetry gets a vote.

### Surface 1 — The Good Now feed

The everyday answer to the founding question — **"what's good right now, near you"** — and, on Thursday evenings, the "This Weekend" edition pointed at the next 48–72 hours (§1). Cards ranked by `now_score = base_quality × Π(active condition multipliers) × decayed top-claim confidence` (the three-factor definition committed in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md), so an unverified affordance can't outrank a verified one), materialized by the condition-evaluator cron ([04-ARCHITECTURE.md](04-ARCHITECTURE.md)) that re-runs every ConditionWindow predicate against USGS NWIS, NOAA CO-OPS, SNOTEL, NWS/Open-Meteo, NWAC, AirNow, and sun/moon feeds. A swim hole's multiplier collapses when the Clackamas runs above 1,200 cfs; a Gorge waterfall's spikes after 72-hour precipitation; a tide pool card only exists near a minus tide.

Feed rules, committed:

- **Everyday base layer first ([07-USERS.md](07-USERS.md) §1):** nearby everyday affordances (Forest Park trailheads, walks, viewpoints) with dense claims and light condition annotation — mud state from 72-h precip, daylight remaining vs. typical duration — are always rankable; condition-magic cards rank *on top* when their windows open. Feed-sourced light conditions count as live reasons for the quality gate; crowd priors annotate but don't count until verification exhaust makes them live ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F6).
- **Generic-intent browse:** typing an activity verb ("trail," "swim," "walk") filters the feed to the everyday ranking for that verb — a feed filter at launch scale, not a search engine (NL search stays deferred, §6).
- **Quality gate: ≥60% of served cards must carry a live condition reason.** If the evaluator can't justify 60% of the feed with real-time provenance, the feed shortens. A short honest feed beats a long static one — a static feed is AllTrails, and AllTrails already exists.
- **Every card shows its provenance line** — a live condition reason (source + freshness) where the evaluator has one; static claim provenance plus last-verified date where it doesn't. No card ships with a bare rank.
- **Dispersal by design:** the feed is always "ten good options ranked by conditions," never a single hero pin (the Blue Pool failure mode). Ranking spreads load; virality concentrates it.
- Filters at launch: drive time (the 90-minute polygon is the universe), activity, dog/kid flags. Nothing else — the feed is the query at this scale.

### Surface 2 — The Almanac

The per-metro curated catalog of watchables — the browse surface for *when*, the way the feed is the browse surface for *now*. Shelves are organized by window family (outdoor, sky, harvest, reservation, health — the crowd shelf stays unpublished until exhaust makes it honest, [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F6), and each entry is one nameable, watchable moment: "Haystack minus tides." "First larch weekend." "Aurora over the Gorge." "Timothy Lake under $30, any July weekend."

Committed rules:

- **Every watchable shows an honest expected-frequency line** — "opens ~6× a winter," "opens ~a dozen daylight windows a summer" — computed by backtest against feed history, never guessed ([09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md) owns the backtest requirement). Expectation-setting is the anti-spam design: a household that knows the larch window opens roughly twice a fall treats the push as a gift, not an interruption.
- **Every watchable displays its measured hit-rate** once it has history — the share of its open pushes that verifying users confirmed. The publication floor and its consequences live in §3.
- **One-tap Watch is the only CTA.** Watching from the Almanac costs one tap, plus a magic-link email if it is the user's first watch (§4).
- **Curated, never user-authored.** The threshold *is* the product; an IFTTT-for-feeds has no moat and no editorial voice ([00-THESIS.md](00-THESIS.md) §7). Curation gates, naming and voice rules, and the launch composition (~25 Portland watchables) are committed in [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md).
- **Per-metro by construction.** The Almanac is the unit of metro expansion: transposing the playbook ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §6) means forging a new metro's shelves, family by family, against the depth bar — never syndicating another metro's list.

The Almanac is also **the graduation surface every seasonal tool seeds**: the October 2026 waterfall ranker is the first outdoor shelf wearing a costume, the April 2027 bloom tracker seeds the harvest shelf, and every tool's cards carry the same Watch action (§4). Almanac v1 ships in the Phase 3 Watcher MVP alongside the sky family ([05-ROADMAP.md](05-ROADMAP.md)).

*Losing alternative:* user-authored predicates — an infinite catalog with zero judgment in it; the moat evaporates into a rules engine.

### Surface 3 — The watcher list

The generalization of the old want-to / been / loved surface, and the commitment that matters is unchanged in substance and upgraded in language: **a watcher is a standing query, not a bookmark.** Every watcher — on a place, an affordance, or an Almanac watchable — is re-evaluated by the same evaluator sweep, and the list renders each one in exactly three states:

- **Watching** — the window is closed; the evaluator sweeps on the household's behalf.
- **Open** — the window is open *now*, with its live reason and provenance: "Dog Mountain balsamroot peaking — 3 reports this week; you've been watching since January."
- **Recently closed** — what just ended and what it did: opened Tuesday, closed Friday. The state that teaches users their watchers are real — the hit-rate ledger made personal — and the one that stings usefully when a window was missed.

This remains the cheapest retention feature per line of code in the product (the evaluator already runs; the open push is a join against the watcher table — the schema's `saves`, generalized per [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) and the single biggest switching cost: **your want-to list on AllTrails is a static folder; your list on Place is a sensor network watching on your behalf.** `want_to` saves are grandfathered as watchers on day one. "Been" and "loved" taps survive unchanged — they write User–DID→Affordance edges and preference labels, the M6 taste-graph signal, collected years before the feature that uses it ships.

**Window-open pushes are the one exception to the weekly push cap.** They are user-requested by construction — the household asked Place to watch — and they fire on **open transitions only**: never on raw readings, never repeating while a window stays open. Transitions-only is the fifth refusal wearing an engineering hat — not an alert firehose ([00-THESIS.md](00-THESIS.md) §7).

### Surface 4 — Claim-based place & window pages

A place page is a rendering of the graph, not a wiki article: the place's affordances (each with difficulty, typical duration, dog/kid flags), each affordance's **current condition state** (predicate result, live sensor value, and the binding it comes from), and each claim's provenance and last-verified date. High Rocks' page says: *wild-swim · currently swimmable · Clackamas @ Estacada (14210000) at 980 cfs, threshold <1,200 · last verified June 27 at 1,010 cfs · 3 sources.* Hazard-class affordances (cliff-jump, wild-swim, snow travel) render only when the publication gates in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) pass, always with assumption-of-risk framing (§5 below). A watchable's page is the same rendering pointed at a window: the plain-language predicate ("a daylight tide lower than −1.0 ft"), the live feed value, the backtested expected frequency, the measured hit-rate, and the Watch action.

Every claim rendered anywhere carries one-tap **confirm / deny / changed** controls — the page is a verification surface, not just a read surface.

Place pages and the "I'm going" confirmation also carry the **"nearby after" module** ([07-USERS.md](07-USERS.md) §4): pairing nodes — brewery, diner, soaking pool — attached via PAIRS_WITH edges, never as standalone commercial destinations. Every tap on a suggestion writes a pairing observation, so this module *feeds* moat M5 years before the Trip Builder renders it.

*Losing alternative:* prose descriptions and star ratings — unstructured text feeds nothing back into the graph, and ratings without conditions are noise ("3 stars" in August flood vs. July low water are different places).

### Surface 5 — The Sunday push

Mechanics, committed precisely:

- **Cap: one push per user per week, Sunday 6:00 pm local.** No exceptions except window-open pushes from watchers (Surface 3).
- **Content: at most two one-tap questions**, selected from the visited place's claims by `(1 − confidence) × decay_rate` — the lowest-confidence, fastest-decaying claims are the ones whose verification buys the most information. Access-class claims (rope swing intact, gate open, log crossing passable) will dominate this ranking because they decay in months; geomorphic claims almost never surface.
- Each answer writes a Verification with an auto-attached conditions snapshot (flow, temp, tide, date — the user is never asked to describe the weather; the system already knows).
- **Same notification carries next weekend's top card.** Verify → see what's good next weekend → watch or "I'm going" → the loop closes.
- If the user didn't tap "I'm going" that week, the push is feed-only (no questions — never ask about a trip we don't know happened).

### Experience-card anatomy

The card is the atomic unit of the feed. Every element either feeds the graph, exercises it, or defends it — nothing decorative.

```
┌─────────────────────────────────────────────────────────┐
│  [hero photo]                                   ◉ watch │
│                                                         │
│  TAMANAWAS FALLS                        41 min drive    │
│  Cold Spring Creek, Mt. Hood NF                         │
│                                                         │
│  ⚡ Flowing hard right now                              │
│     1.6 in rain in the last 72 h (NWS) — best window    │
│     next 3–4 days · verified Sun by @gorge_amy          │
│                                                         │
│  waterfall-view · moderate · ~3 h round trip            │
│  dogs ok (leash) · kids ok · icefall hazard in winter   │
│                                                         │
│  Northwest Forest Pass required · pack it out           │
│                                                         │
│  [ I'm going ]        [ more conditions → ]             │
└─────────────────────────────────────────────────────────┘
```

Reading the card top to bottom: identity (place + access context + drive time from the user's location); **the provenance line** (the ⚡ block — live reason, data source, freshness, and named verifier credit, the only "social" feature at launch); the affordance strip (activity verb, difficulty, duration, dog/kid flags — straight from the reified Affordance node); the safety/stewardship line (permit + Leave No Trace, required on every card per §5); and exactly two actions. "I'm going" is the only conversion the card wants.

The one change the reframe makes: **the save glyph of earlier drafts is now the watch action.** On a condition card, the corner tap creates a watcher on this card's window — the same standing query as an Almanac Watch — instead of filing a bookmark. The two-actions rule stands unchanged; "I'm going" remains the only conversion the card wants.

The named credit (`@gorge_amy`) is deliberate: power verifiers get provenance credit, not points — recognition that reinforces truth-telling instead of volume-gaming.

---

## 3. The Vigilance tier — pricing, committed

**This is the only section in the entire canon where Place's own prices appear.** Every sibling doc says "the Vigilance household tier" and links here; if a Place price shows up anywhere else, it is a bug. (Competitor prices and a watchable's price attribute — "under $30" — are facts about the world, not pricing.)

**Free:** browse everything — the Good Now feed, the full Almanac, every place and window page — **with no login to read**, plus **two starter watchers** on a magic-link account. The free tier is the flywheel's mouth: it must stay generous enough that seasonal tools keep converting strangers into verifiers, because verifications, not subscriptions, are the asset the subscriptions are built on.

**Vigilance — $39/year, per household:** unlimited watchers, **guaranteed delivery**, and the **reservation family included** — campsite cancellations, permit drops, timed-entry releases ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F4), visible to everyone in the Almanac but watchable only on Vigilance. One subscription covers the household: the buyer is P2, the weekend planner ([07-USERS.md](07-USERS.md)) — the person already carrying the family's logistics — and everyone in the house gets the pushes they care about. One payer, everyone benefits, no per-seat arithmetic at the kitchen table.

**What "guaranteed" means, named honestly.** iOS web push for PWAs is real but unreliable in ways a vigilance product cannot shrug at. So the word "guaranteed" ships only when three things exist: per-push **delivery telemetry**, an automatic **email fallback** when a push does not confirm delivery, and a published delivery rate. Until then, the promise is "we push the moment it opens" — strong, but not "guaranteed." This is a launch gate, not a caveat buried in the ToS ([05-ROADMAP.md](05-ROADMAP.md) carries the build). Equally honestly: no billing or entitlement code exists today — Stripe, household seats, and the paywall itself are pre-Phase-5 build items, flagged in [05-ROADMAP.md](05-ROADMAP.md), not hand-waved here.

The pricing psychology, stated plainly:

- **$39 is a weather-app-sized fee anchored against one missed thing a year.** The campsite that went to someone with a faster refresh. The larch weekend spent at home. The minus tide discovered a day late. One catch pays for the year, and the household knows it the first time a window opens in their pocket.
- **The reservation shelf alone is worth more than the bundle's asking price.** Campnab-class utilities charge $10–30 *a month* to watch campsite availability — the cheapest of them costs roughly three Vigilances a year, for one family of window, with no verified local thresholds, no verification loop, and no bundle ([06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)). Vigilance beats the point solutions on price *and* on being one habit instead of five.
- **The conversion moment moves from the old spec's "first save" to the third watch.** The first watch costs an email (magic link, §4). The second is free. The third — the tap that exceeds the starter allowance of two — is where the ask lands, and it lands mid-motion, on a user asking Place to watch *more*. That is the only moment a $39 question feels like a favor instead of a toll.

**The hit-rate honesty rule.** Every watchable displays its measured open-rate — the share of its open pushes that verifying users confirmed were real. **Below roughly 70% precision, a watchable is unpublished** until its threshold is re-forged; the measurement and unpublication mechanics live in [09-WATCHER-CATALOG.md](09-WATCHER-CATALOG.md). A vigilance product that cries wolf trains its customers to swipe away the exact push they paid for — the fifth refusal ([00-THESIS.md](00-THESIS.md) §7) is a pricing policy here, not a values statement.

**Paid launches at Phase 5** — June 2027, alongside Swim Portland, anchored by the reservation family at peak camping demand; the calendar and the paying-households gate live in [05-ROADMAP.md](05-ROADMAP.md). Two free seasons exercise the watcher machinery first, so the tier launches on proven delivery and the one family with externally proven willingness to pay.

---

## 4. The graduation path: seasonal tool → Almanac seed → retained app

We do not launch "an app." An empty discovery app has nothing to rank and no reason to be shared. We launch a **free, no-login seasonal conditions tool** off the same graph — and every tool is now an **Almanac seed**: its ranked list is a family shelf wearing a costume, and the app is what heavy users graduate into.

**The front door — demonstrated first by the October 2026 waterfall ranker.** "Gorge waterfalls ranked by current flow" is public launch #1 ([05-ROADMAP.md](05-ROADMAP.md)): waterfalls inside the 90-minute polygon ranked by *today's* flow — 72-hour NWS precipitation plus creek gauges, drive time, provenance line per card. No login, no install, loads in two seconds. Posted to r/Portland timed to the first big October rain event; regenerated daily, it doubles as a programmatic-SEO surface ("best waterfalls near Portland right now").

**The conversion moment is the watch.** The tool needs no account to read. The first time a user taps Watch on Tamanawas or Elowah, we ask for an email (magic link, no password) — because a watcher is a standing query, and standing queries need somewhere to send the push. The pitch is one sentence: *"Watch this — we'll tell you when it's going off."* That is the entire onboarding funnel — tool → watch → open push → Thursday feed → Sunday push — and October 2026 proves it end to end. (The *paid* conversion moment comes later and is different: the third watch, §3.)

**"Swim Portland" is the flagship second instance of the same pattern** — ships June 2027, three weeks before July 4 (hard date; sequencing per [05-ROADMAP.md](05-ROADMAP.md)). Swimming holes ranked by *today's* water: current flow and temp from gauges 14210000 (Clackamas @ Estacada) and 14137000 (Sandy @ Bull Run), drive time, parking-full likelihood, hazard notes per spot — posted to r/Portland as the definitive answer to the perennial swimming-hole thread, with the watch-pitch now *"We'll tell you when it's swimmable."* The cadence continues with the April 2027 wildflower-week tracker (Dog Mountain permit-aware, and the harvest family's seed per [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F3); each seasonal tool reuses all prior bindings, adds a claim type, and stocks a new Almanac shelf, so the marginal tool gets cheaper each season — the full calendar and gates live in [05-ROADMAP.md](05-ROADMAP.md).

*Losing alternative:* launching the general discovery app first — nothing to rank, no reason to share, and every download costs money instead of a Reddit post.

---

## 5. Safety and dispersal as product requirements

These are requirements with acceptance criteria, not values statements:

1. **Hazard gating.** Hazard-class affordances (cliff-jump, wild-swim, snow travel) surface only with (a) a *recent* verification AND (b) a currently-satisfied live condition trigger. No exceptions, including for the founder's favorite spots. Rendered always with provenance, last-verified date, and assumption-of-risk framing ("conditions change; you are responsible for your own judgment").
2. **Conditions snapshot on every served recommendation.** Every card impression, watch, and "I'm going" logs the condition vector it was served under. This is both the legal record and moat M4's training data.
3. **Dispersal mechanics.** Parking-full verification spikes downrank a place in the same week's feed. A curated sensitive-sites exclusion list (active-restoration closures) is checked at publish time — excluded places cannot appear in any feed or tool, period.
4. **Permits and Leave No Trace on every card.** The Multnomah Falls timed-use permit (via RIDB) and Northwest Forest Pass requirements render on the card, not behind a tap.
5. **Never a single viral pin.** Every public surface — feed, Almanac, seasonal tools, SEO pages — is a *ranked list of ten options*, structurally. The Blue Pool pattern (one pin, one crowd, one damaged place) is designed out at the rendering layer.
6. **ToS and waiver language reviewed before the first public tool ships** ([05-ROADMAP.md](05-ROADMAP.md) Phase 1), not after — and re-reviewed before the swim tool, which recommends wild swimming to strangers: the highest-liability thing Place will ever do.
7. **Harvest dispersal.** Foraging watchables name *conditions and regions*, never pins — "chanterelles are flushing in the Coast Range," never a trailhead ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F3). The Blue Pool rule applies to mushrooms more than to anything else in the product.

---

## 6. The deferral table

Each row is a real feature from the original vision, deferred with its one-line reason. Deferred ≠ rejected: the graph is built so each becomes a rendering of data already accumulating. The reframe wakes nothing up early — everything stays deferred.

| Feature | Deferred because | Wakes up when |
|---|---|---|
| Trip Builder | Exercises the graph but doesn't feed it; needs claim density first | PAIRS_WITH edges exist (moat M5), post claim-density bar |
| Social layer (friends, shared lists) | Empty rooms below ~5k users | ~5k WAP in one metro |
| Gamification / badges | Badge-hunting pollutes verification ground truth; only recognition at launch is named provenance credit for power verifiers | Possibly never — credit may be strictly better |
| Natural-language search | At launch scale the feed IS the query; search earns its place when the graph outgrows a scrollable feed | Graph > scrollable-feed scale (pgvector already provisioned) |
| Creator economy | Supply-side before demand | Post-retention, post-revenue |
| Offline maps / native apps | Paid-tier polish, not loop-critical — though if §3's delivery telemetry shows iOS PWA push cannot be made honest, native jumps the queue | Post-Vigilance traction ([05-ROADMAP.md](05-ROADMAP.md) year-2 horizon) |

---

## 7. North-star metrics

Chosen so that the product team and the moat cannot drift apart — each metric is a moat layer wearing a product hat:

- **Weekly-active-planners (WAP)** — users who open the Thursday feed or receive-and-open the Sunday push in a week. *Not DAU:* a weekly-ritual product measured in DAU will be "fixed" into a worse product.
- **4-week planning streaks** — consecutive weeks with a planning action (feed open, watch, "I'm going"). The retention number that predicts whether the ritual took.
- **Verification rate ≥30% of tracked visits** — of "I'm going" taps, the share answering at least one Sunday question. Gate for the first 100 users; at 1,000 users the gates become 20+ verifications/day and 5+ user-submitted claims/week (gates per [05-ROADMAP.md](05-ROADMAP.md)).
- **The moat metric: % of served claims backed by in-product ground truth** — the headline number from [00-THESIS.md](00-THESIS.md). Target: user verification overtakes extraction as dominant claim support within 12–18 months of launch.
- **Feed quality gate: ≥60% of feed cards carrying a live condition reason** — the honesty check on Surface 1; if it fails, we fix bindings ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)), not the ranking.

The watcher tier adds three, all M7 wearing a product hat:

- **Active watchers per household** — the depth of declared demand, and the raw material of watch exhaust ([00-THESIS.md](00-THESIS.md) M7). The Phase 3 gate is committed in [05-ROADMAP.md](05-ROADMAP.md): **the median activated user holds ≥3 watchers.**
- **The watch → open → go funnel** — of watchers held, the share whose windows opened this season; of open pushes, the share producing an "I'm going"; of those trips, the share verified. The catalog's honesty ledger, and the input to §3's hit-rate publication floor.
- **Paying households** — counted from the Phase 5 launch ([05-ROADMAP.md](05-ROADMAP.md)). Revenue is a moat metric here, not just a business one: a paid push manufactures the verification that tightens the threshold that made the push accurate ([00-THESIS.md](00-THESIS.md) §5).

What we deliberately don't track as goals: downloads, MAU, session length, cards-per-session. In an episodic category, all four are vanity or perverse.
