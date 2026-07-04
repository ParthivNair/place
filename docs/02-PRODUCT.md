# Product Spec — The Weekly Ritual & MVP

**In one breath:** Place's product is a weekly planning ritual, not a daily app — a Thursday "This Weekend" feed ranked by live conditions, a Saturday trip, and one Sunday-6pm push that is *simultaneously* the verification prompt and the re-engagement prompt. The MVP is a PWA with exactly four surfaces (temporal feed, claim-based place pages, want-to lists that fire condition alerts, the Sunday push), launched as a free no-login seasonal tool (the October 2026 "Gorge waterfalls by current flow" ranker first; "Swim Portland" follows in June 2027, three weeks before July 4 — sequencing per [05-ROADMAP.md](05-ROADMAP.md)) that graduates users into accounts via the want-to list. Everything else — Trip Builder, social, badges, NL search, creator economy, native apps — is deferred with a stated reason. Success is measured in weekly-active-planners, 4-week streaks, and a ≥30% verification rate, because verifications, not users, are the asset.

Vocabulary (affordance, condition window, claim, verification, binding) is defined in [00-THESIS.md](00-THESIS.md); the schema and confidence math live in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); the pipeline that fills the feed is [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); the systems that serve it are [04-ARCHITECTURE.md](04-ARCHITECTURE.md).

---

## 1. The core loop: own the episodic cadence

Outdoor recreation is episodic. People do not open an outdoors app on Tuesday at lunch; they plan Thursday night, go Saturday, and recover Sunday. Every incumbent fights this cadence with engagement mechanics. Place commits to it and builds the whole product on a three-beat week:

**Thursday evening — the "This Weekend" feed.** Ranked experience cards for the next 48–72 hours, most carrying a live, provenance-backed reason they rank *now* (the ≥60% quality gate, Surface 1): "Tamanawas Falls flowing hard: 1.6 in rain in 72 h," "Balsamroot peaking on Dog Mountain: 3 reports this week," "High Rocks swimmable: Clackamas at 980 cfs (gauge 14210000), verified 6 days ago at 1,010 cfs." The provenance line is load-bearing, not decoration — it teaches the user in one glance that the app *knows things* a static database cannot, and it turns every card into an implicit claim the user can verify after their visit.

**Saturday — the trip.** Tapping "I'm going" on a card records trip intent and snapshots the conditions the recommendation was served under (flow, temp, forecast, tide — logged automatically, per §5's requirement that every served recommendation logs its conditions). No check-in, no tracking, no GPX. The tap is the entire ask.

**Sunday 6:00 pm — the push.** One notification, hard-capped at one per week. It asks at most **two one-tap questions** about the place the user said they were going to — drawn from that place's claims ranked by *lowest confidence × fastest decay* (the two claims whose answers are worth the most, per the decay model in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md)) — and the same notification surfaces next weekend's top feed card.

### The sharpest insight, stated plainly

**The verification prompt and the re-engagement prompt are the same notification.** In an episodic category you get roughly one push per week before you're muted, so the action that builds the moat (a verification verdict) and the action that drives retention (opening next weekend's feed) must be one tap apart, in one message. This is not a growth hack bolted onto a data pipeline; it is the product's central mechanism.

And it works only because the questions are about **claims, not places**. "Was the pool swimmable?" is a one-second yes/no favor — the user knows the answer instantly and answering feels like helping the next person. "How was it?" is a request for a review, and reviews are chores; one-tap claim verdicts are favors. Place never asks "how was it?" anywhere in the product.

*Losing alternative:* daily-engagement mechanics (streaks, daily digests, push-per-condition-change) — they fight the category's natural rhythm and burn the one weekly notification budget we have.

---

## 2. The four MVP surfaces

The MVP is a PWA — installable, push-capable, no app-store gate, one codebase (Next.js, per [04-ARCHITECTURE.md](04-ARCHITECTURE.md)). *Losing alternative:* native apps — two more codebases for zero additional moat; deferred to the premium tier era.

### Surface 1 — The temporal "This Weekend" feed

Cards ranked by `now_score = base_quality × Π(active condition multipliers) × decayed top-claim confidence` (the three-factor definition committed in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md), so an unverified affordance can't outrank a verified one), materialized by the condition-evaluator cron ([04-ARCHITECTURE.md](04-ARCHITECTURE.md)) that re-runs every ConditionWindow predicate against USGS NWIS, NOAA CO-OPS, SNOTEL, NWS/Open-Meteo, NWAC, AirNow, and sun/moon feeds. A swim hole's multiplier collapses when the Clackamas runs above 1,200 cfs; a Gorge waterfall's spikes after 72-hour precipitation; a tide pool card only exists near a minus tide.

Feed rules, committed:

- **Quality gate: ≥60% of served cards must carry a live condition reason.** If the evaluator can't justify 60% of the feed with real-time provenance, the feed shortens. A short honest feed beats a long static one — a static feed is AllTrails, and AllTrails already exists.
- **Every card shows its provenance line** — a live condition reason (source + freshness) where the evaluator has one; static claim provenance plus last-verified date where it doesn't. No card ships with a bare rank.
- **Dispersal by design:** the feed is always "ten good options ranked by conditions," never a single hero pin (the Blue Pool failure mode). Ranking spreads load; virality concentrates it.
- Filters at launch: drive time (the 90-minute polygon is the universe), activity, dog/kid flags. Nothing else — the feed is the query at this scale.

### Surface 2 — Claim-based place pages

A place page is a rendering of the graph, not a wiki article: the place's affordances (each with difficulty, typical duration, dog/kid flags), each affordance's **current condition state** (predicate result, live sensor value, and the binding it comes from), and each claim's provenance and last-verified date. High Rocks' page says: *wild-swim · currently swimmable · Clackamas @ Estacada (14210000) at 980 cfs, threshold <1,200 · last verified June 27 at 1,010 cfs · 3 sources.* Hazard-class affordances (cliff-jump, wild-swim, snow travel) render only when the publication gates in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) pass, always with assumption-of-risk framing (§5 below).

Every claim rendered anywhere carries one-tap **confirm / deny / changed** controls — the page is a verification surface, not just a read surface.

*Losing alternative:* prose descriptions and star ratings — unstructured text feeds nothing back into the graph, and ratings without conditions are noise ("3 stars" in August flood vs. July low water are different places).

### Surface 3 — Want-to / been / loved, where saves are standing queries

Three taps, no lists-of-lists UI. The commitment that matters: **a save is a standing query, not a bookmark.** Every saved place is re-evaluated by the same condition cron, and when a saved place's trigger fires, the user gets an alert: *"Dog Mountain balsamroot peaking — you saved this in January."*

This is the cheapest retention feature per line of code in the product (the evaluator already runs; the alert is a join against the saves table) and the single biggest switching cost: your want-to list on AllTrails is a static folder; your want-to list on Place is a sensor network watching the outdoors on your behalf. Condition alerts are the one exception to the weekly push cap — they are user-requested by construction (the user saved the place), rate-limited to fire only on trigger transitions.

"Been" taps write User–DID→Affordance edges; "loved" writes the same DID edge plus a preference label — the M6 taste-graph signal — all inside the DID/SAVED/REJECTED edge set, collected years before the feature that uses it ships.

### Surface 4 — The Sunday push

Mechanics, committed precisely:

- **Cap: one push per user per week, Sunday 6:00 pm local.** No exceptions except standing-query condition alerts (Surface 3).
- **Content: at most two one-tap questions**, selected from the visited place's claims by `(1 − confidence) × decay_rate` — the lowest-confidence, fastest-decaying claims are the ones whose verification buys the most information. Access-class claims (rope swing intact, gate open, log crossing passable) will dominate this ranking because they decay in months; geomorphic claims almost never surface.
- Each answer writes a Verification with an auto-attached conditions snapshot (flow, temp, tide, date — the user is never asked to describe the weather; the system already knows).
- **Same notification carries next weekend's top card.** Verify → see what's good next weekend → save or "I'm going" → the loop closes.
- If the user didn't tap "I'm going" that week, the push is feed-only (no questions — never ask about a trip we don't know happened).

---

## 3. Experience-card anatomy

The card is the atomic unit of the feed. Every element either feeds the graph, exercises it, or defends it — nothing decorative.

```
┌─────────────────────────────────────────────────────────┐
│  [hero photo]                                    ♥ save │
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

The named credit (`@gorge_amy`) is deliberate: power verifiers get provenance credit, not points — recognition that reinforces truth-telling instead of volume-gaming.

---

## 4. The graduation path: seasonal tool → retained app

We do not launch "an app." An empty discovery app has nothing to rank and no reason to be shared. We launch a **free, no-login seasonal conditions tool** off the same graph, and the app is what heavy users graduate into.

**The front door — demonstrated first by the October 2026 waterfall ranker.** "Gorge waterfalls ranked by current flow" is public launch #1 ([05-ROADMAP.md](05-ROADMAP.md)): waterfalls inside the 90-minute polygon ranked by *today's* flow — 72-hour NWS precipitation plus creek gauges, drive time, provenance line per card. No login, no install, loads in two seconds. Posted to r/Portland timed to the first big October rain event; regenerated daily, it doubles as a programmatic-SEO surface ("best waterfalls near Portland right now").

**The conversion moment is the save.** The tool needs no account to read. The first time a user taps ♥ on Tamanawas or Elowah, we ask for an email (magic link, no password) — because a save is a standing query, and standing queries need somewhere to send the alert. The pitch is one sentence: *"We'll tell you when it's flowing hard."* That is the entire onboarding funnel — tool → save → alert → Thursday feed → Sunday push — and October 2026 proves it end to end.

**"Swim Portland" is the flagship second instance of the same pattern** — ships June 2027, three weeks before July 4 (hard date; sequencing per [05-ROADMAP.md](05-ROADMAP.md)). Swimming holes ranked by *today's* water: current flow and temp from gauges 14210000 (Clackamas @ Estacada) and 14137000 (Sandy @ Bull Run), drive time, parking-full likelihood, hazard notes per spot — posted to r/Portland as the definitive answer to the perennial swimming-hole thread, with the save-pitch now *"We'll tell you when it's swimmable."* The cadence continues with the April 2027 wildflower-week tracker (Dog Mountain permit-aware); each seasonal tool reuses all prior bindings and adds a claim type, so the marginal tool gets cheaper each season — the full calendar and gates live in [05-ROADMAP.md](05-ROADMAP.md).

*Losing alternative:* launching the general discovery app first — nothing to rank, no reason to share, and every download costs money instead of a Reddit post.

---

## 5. Safety and dispersal as product requirements

These are requirements with acceptance criteria, not values statements:

1. **Hazard gating.** Hazard-class affordances (cliff-jump, wild-swim, snow travel) surface only with (a) a *recent* verification AND (b) a currently-satisfied live condition trigger. No exceptions, including for the founder's favorite spots. Rendered always with provenance, last-verified date, and assumption-of-risk framing ("conditions change; you are responsible for your own judgment").
2. **Conditions snapshot on every served recommendation.** Every card impression, save, and "I'm going" logs the condition vector it was served under. This is both the legal record and moat M4's training data.
3. **Dispersal mechanics.** Parking-full verification spikes downrank a place in the same week's feed. A curated sensitive-sites exclusion list (active-restoration closures) is checked at publish time — excluded places cannot appear in any feed or tool, period.
4. **Permits and Leave No Trace on every card.** The Multnomah Falls timed-use permit (via RIDB) and Northwest Forest Pass requirements render on the card, not behind a tap.
5. **Never a single viral pin.** Every public surface — feed, seasonal tools, SEO pages — is a *ranked list of ten options*, structurally. The Blue Pool pattern (one pin, one crowd, one damaged place) is designed out at the rendering layer.
6. **ToS and waiver language reviewed before the first public tool ships** ([05-ROADMAP.md](05-ROADMAP.md) Phase 1), not after — and re-reviewed before the swim tool, which recommends wild swimming to strangers: the highest-liability thing Place will ever do.

---

## 6. The deferral table

Each row is a real feature from the original vision, deferred with its one-line reason. Deferred ≠ rejected: the graph is built so each becomes a rendering of data already accumulating.

| Feature | Deferred because | Wakes up when |
|---|---|---|
| Trip Builder | Exercises the graph but doesn't feed it; needs claim density first | PAIRS_WITH edges exist (moat M5), post claim-density bar |
| Social layer (friends, shared lists) | Empty rooms below ~5k users | ~5k WAP in one metro |
| Gamification / badges | Badge-hunting pollutes verification ground truth; only recognition at launch is named provenance credit for power verifiers | Possibly never — credit may be strictly better |
| Natural-language search | At launch scale the feed IS the query; search earns its place when the graph outgrows a scrollable feed | Graph > scrollable-feed scale (pgvector already provisioned) |
| Creator economy | Supply-side before demand | Post-retention, post-revenue |
| Offline maps / native apps | Premium later, not loop-critical | Premium tier ([05-ROADMAP.md](05-ROADMAP.md) year-2 horizon) |

---

## 7. North-star metrics

Chosen so that the product team and the moat cannot drift apart — each metric is a moat layer wearing a product hat:

- **Weekly-active-planners (WAP)** — users who open the Thursday feed or receive-and-open the Sunday push in a week. *Not DAU:* a weekly-ritual product measured in DAU will be "fixed" into a worse product.
- **4-week planning streaks** — consecutive weeks with a planning action (feed open, save, "I'm going"). The retention number that predicts whether the ritual took.
- **Verification rate ≥30% of tracked visits** — of "I'm going" taps, the share answering at least one Sunday question. Gate for the first 100 users; at 1,000 users the gates become 20+ verifications/day and 5+ user-submitted claims/week (gates per [05-ROADMAP.md](05-ROADMAP.md)).
- **The moat metric: % of served claims backed by in-product ground truth** — the headline number from [00-THESIS.md](00-THESIS.md). Target: user verification overtakes extraction as dominant claim support within 12–18 months of launch.
- **Feed quality gate: ≥60% of feed cards carrying a live condition reason** — the honesty check on Surface 1; if it fails, we fix bindings ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)), not the ranking.

What we deliberately don't track as goals: downloads, MAU, session length, cards-per-session. In an episodic category, all four are vanity or perverse.
