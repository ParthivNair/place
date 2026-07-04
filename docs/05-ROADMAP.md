# Roadmap — Seasons, Moat Checkpoints & Gates

**In one breath:** It is July 3, 2026 — the "swim tool three weeks before July 4" window is missed, and we will not fake it. The first public launch is the **October 2026 Gorge waterfall tool**; the swim tool ships in **June 2027**, three weeks before July 4, 2027, off a graph whose bindings and verification log have been accumulating since July 2026. Every phase below ends in a **moat checkpoint** — a named compounding asset that exists at the end of the phase and did not exist before. Verification and expansion gates are quality bars, not dates; seasonal windows are dates: metro 2 opens only when the feed quality gate holds, and no calendar pressure overrides a verification gate. The MCP server ships by April 2027, within six months of public launch.

---

## The transposition rule (read this before the phases)

**The wedge must be where the founder lives.** Sensor bindings are earned local judgment — the founder is verifier #1, and the gold calibration set is the 30–50 places the founder personally ground-truths. Everything below is written in Portland specifics (Clackamas gauge 14210000, Tamanawas Falls, r/Portland) because the founder lives in the Portland 90-minute polygon. If that changes, transpose the playbook, not the plan: the selection criteria are what matter — **condition-density** (many weather/flow/tide-gated experiences), **corpus availability** (an unguarded local trip-report corpus), **incumbent gap** (no beloved WTA-equivalent), and **year-round seasonal variety** (a tool to ship every season). Every Portland specific has a one-to-one analogue in any metro that scores on those four.

## Why October first, not a rushed swim beta

The plan's original canonical date — swim tool live 3 weeks before July 4 — assumed a spring build. Today is July 3. Shipping a swimming-hole ranker *tomorrow* means launching a hazard-class product (wild-swim and cliff-jump are the strictest publication gate in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §gates) with zero founder verifications, no review queue, and no ToS/waiver review. The first r/Portland post is the one shot at "this thing *knows things*" — a stale or wrong swim ranking on a 95°F weekend is the losing move, possibly the fatal one given the liability requirements in [02-PRODUCT.md](02-PRODUCT.md) §5.

**Primary plan: October waterfall window is launch #1.** Waterfalls are the safer claim class (geomorphic + flow-triggered, not hazard-gated), the Gorge is the densest waterfall concentration in North America, and October gives 14 weeks to build correctly. The swim tool ships June 2027 on top of a year of bindings and a live verification log — a categorically better product than anything buildable this week.

**Committed alongside it:** a private late-summer 2026 swim beta (10–15 founder-verified holes only, no hazard-class cliff-jump claims, unlisted link to Oregon Hikers regulars), running July–September 2026 as a founder-only bindings-forging exercise on the Clackamas/Sandy swim corridor — explicitly not a public launch: it never gets the r/Portland post; first impressions are not A/B-testable. It is what puts a year of tightened bounds behind Phase 5's thresholds.

---

## Phase table

| # | Window | Name | Key deliverables | Gate to exit |
|---|--------|------|------------------|--------------|
| 0 | Jul 2026 (4 wks) | Foundation & benchmark | Postgres/PostGIS migration from `src/main.py`; ~1,200 skeleton places seeded; **benchmark-the-enemy: 50 conditional queries vs ChatGPT+search and AllTrails, failure rate recorded** | Schema frozen; benchmark memo written |
| 1 | Aug–Sep 2026 (9 wks) | Forge & extract | ≤$200 batch extraction → 5–10k claims; condition evaluator cron live; 60 waterfall bindings forged; ~40 swim bindings via the private founder beta (Jul–Sep); founder verifies top 30–50; ToS/waiver reviewed | 150 dense places; hazard gates enforced in code |
| 2 | Oct 2026 (launch) | Waterfall tool — public launch #1 | "Gorge waterfalls ranked by current flow" (72-h NWS precip + creek gauges); r/Portland post; daily-regenerated SEO pages | Tool live before first big October rain event |
| 3 | Nov 2026–Mar 2027 | PWA graduation & first-100 gate | Four MVP surfaces ([02-PRODUCT.md](02-PRODUCT.md)); Sunday push; 10 named power verifiers; saves-as-standing-queries | **First-100 gate:** ≥30% of tracked visits verified |
| 4 | Apr 2027 | Wildflower tool + MCP server | Dog Mountain permit-aware bloom tracker; **MCP server (`search_experiences`, `get_conditions`)** — within 6 months of Oct launch | **Feed gate:** ≥60% of feed cards carry a live condition reason |
| 5 | Jun 2027 (hard date: 3 wks before Jul 4) | Swim tool — the delayed flagship | Swim tool on the 40 swim-hole bindings forged Jul–Sep 2026 (gauges 14210000 Clackamas @ Estacada, 14137000 Sandy @ Bull Run); hazard-gated cliff-jump affordances; the definitive r/Portland swim post | **First-1,000 gate:** 20+ verifications/day, 5+ user claims/week |
| 6 | Jul 2027 → | Year 2 horizon | ~500 total bindings; verification overtakes extraction; metro 2 (Seattle, WTA partnership); premium tier | **Expansion gate:** quality bar, never calendar |

---

## Phase 0 — Foundation & benchmark (July 2026, 4 weeks)

**Starting point, honestly:** `src/main.py` is a 143-line FastAPI app on Mongo with two collections (`locations`: name/lat/lng/category; `reviews`: rating/content), a hand-rolled bounding-box radius search, no auth, no geo index, no tests. There is no production data, so there is nothing to migrate — we replace, not port.

**Deliverables:**
- Stand up Postgres + PostGIS + pgvector per [04-ARCHITECTURE.md](04-ARCHITECTURE.md); the FastAPI shell survives, the Mongo layer and the `math.cos` bounding-box code do not. `reviews` (rating + prose) is deleted, not migrated — reviews are chores; claims and verifications are the model.
- Seed ~1,200 skeleton places: OSM Overpass (natural=waterfall/hot_spring, tourism=viewpoint, leisure=swimming_area, natural=peak, hiking relations), GNIS (Falls/Summit/Spring/Lake), RIDB facilities/permits (captures the Multnomah Falls timed-use permit), USFS FSGeodata trailheads for Mt. Hood NF + CRGNSA. Crosswalk IDs stored per [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md).
- Swim-corridor field forging starts immediately (July weekends on the Clackamas/Sandy corridor) — formally tracked under Phase 1's binding deliverables; foundation work and field days interleave from week one, because swim season doesn't wait for the schema.
- **Benchmark-the-enemy (explicit early deliverable, not a someday):** run 50 conditional Portland queries — "is Punch Bowl Falls swimmable today?", "where are larches at peak this week?", "which Gorge waterfall is flowing hardest right now?" — through ChatGPT-with-search and AllTrails. Record answers, score failures (wrong, stale, top-50 regression, refused-on-liability), keep the transcript. The recorded failure rate **is** the wedge definition and the October launch narrative ("we asked ChatGPT these 50 questions; here's what it got wrong"). Re-run quarterly; the delta is the moat health check against model improvement.

**MOAT CHECKPOINT 0:** *The benchmark corpus exists* — a dated, reproducible record of exactly which questions the incumbents and frontier models cannot answer, plus a canonical place skeleton with crosswalk IDs. Nothing proprietary yet; the drawbridge is being built, and we know precisely where the wall must go.

## Phase 1 — Forge & extract (Aug–Sep 2026, 9 weeks)

**Deliverables:**
- Extraction pipeline #1 end-to-end: official Reddit API (r/Portland, r/oregon, r/PNWhiking, r/OregonCoast) + Oregon Hikers field guide/forum (robots.txt-respecting) → ~150k cached source docs → Haiku-class batch extraction (≤$200 one-time) → 5,000–10,000 claims through entity resolution and the review queue. **Never auto-publish**; standard claims need ≥2 independent sources or founder/user verification.
- Condition evaluator cron live: every ConditionWindow predicate re-evaluated against USGS NWIS, NOAA CO-OPS, SNOTEL, NWS/Open-Meteo, NWAC, AirNow, sun/moon; `good_now` index materialized. This one script is what makes October's tool temporal instead of static.
- **60 waterfall bindings hand-forged**: each Gorge waterfall bound to 72-h NWS precipitation + the nearest creek gauge, with an initial "flowing hard" threshold from corpus claims, to be tightened by verification.
- **~40 swim bindings forged in parallel (July–September 2026, committed):** the private founder-only beta on the Clackamas/Sandy corridor — bindings-forging only, no public surface; these enter Phase 5 verified through summer 2026 and tightened again in spring 2027.
- Founder verification tour: top 30–50 places ground-truthed in person (the gold calibration set); every visit logged as a Verification with auto conditions snapshot.
- ToS, assumption-of-risk waiver language, and sensitive-sites exclusion list reviewed **before** launch, not after.
- **Depth bar enforced:** 150 places with dense, condition-wired claims beats 400 shallow. Cut deeper, not wider.

**MOAT CHECKPOINT 1:** *The bindings exist and the log is live.* 60 waterfall bindings forged, ~40 swim bindings forged privately (place × activity → named gauge + learned threshold — joins that appear in no corpus); verification log running with founder as verifier #1; 30–50 places founder-ground-truthed; every claim carries provenance, observed_date, and extractor version for cheap re-extraction as models improve.

## Phase 2 — October launch: waterfall tool (October 2026)

**Deliverables:**
- "Gorge waterfalls ranked by current flow" — free, no-login, ranked by live 72-h precip + creek gauges, each card with drive time, provenance line, last-verified date, permit note (Multnomah timed-use), Leave No Trace framing. "Ten good options ranked by conditions" spreads load; no viral single pin.
- Posted to r/Portland timed to the first big October rain event (the moment the question "which waterfalls are going off?" is actually asked). The benchmark memo is the narrative hook.
- Daily-regenerated programmatic SEO pages ("best waterfalls near Portland right now") begin compounding.
- Every card carries one-tap confirm/deny/changed from day one — the flywheel is instrumented before there are users to spin it.

**MOAT CHECKPOINT 2:** *Public verification exhaust begins.* First non-founder verifications land with auto-attached condition snapshots; first labeled claim→outcome pairs under recorded flow conditions — the layer that cannot be backfilled at any price starts accumulating on day one of public existence.

## Phase 3 — PWA graduation & first-100 gate (Nov 2026–Mar 2027)

**Deliverables:**
- The seasonal tool graduates into the four-surface PWA ([02-PRODUCT.md](02-PRODUCT.md)): "This Weekend" feed ranked by `now_score`, claim-based place pages, want-to/been/loved taps where **saves are standing queries**, and the Sunday 6 pm verification push (max two one-tap questions + next weekend's top card — the moat action and the retention action in one notification).
- Winter keeps the cadence honest: SNOTEL/NWAC-bound snowshoe and frozen-falls windows added so the feed has live reasons in January, not just October.
- 10 named power verifiers recruited from Reddit/Oregon Hikers — early access + named provenance credit, the only "social" feature at launch (badges deferred: badge-hunting pollutes ground truth).
- Bindings grow toward the ~500 year-one target; decay parameters start being fit from the verification log.

**GO/NO-GO — First-100 gate:** at 100 users, **≥30% of tracked visits produce a verification**. If not, the loop is broken — fix the Sunday push mechanics and card provenance before spending a single hour on growth. If the gate hasn't held by March 2027, it wins for PWA surfaces — feed and push features freeze — but the free seasonal tools (Phases 4–5) proceed on their windows, because they are acquisition surfaces that also feed bindings; the MCP-within-six-months clock is keyed to public launch #1 and does not slide.

**MOAT CHECKPOINT 3:** *The flywheel turns without the founder.* Verification log has multi-user, multi-season coverage; per-claim-class decay is now learned from outcomes rather than assumed; the standing-query save base is the first real switching cost.

## Phase 4 — Wildflower window + MCP server (April 2027)

**Deliverables:**
- April wildflower tracker: Dog Mountain (permit-aware) and Tom McCall bloom state — third claim type on the same graph; the marginal seasonal tool is now measurably cheaper than the last (this is the point of the cadence).
- **MCP server ships** — `search_experiences` / `get_conditions`, within six months of the October launch as committed in [06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md)'s tool position. Freshest tier gated with attribution and rate terms; perishability is the API leverage (last month's copy of the graph is worthless, so callers keep calling). Place keeps its own consumer surface — the verification loop is not outsourceable.
- Re-run the 50-query benchmark against current frontier models; publish the delta.

**GO/NO-GO — Feed quality gate:** **≥60% of feed cards carry a live condition reason** with provenance. This is the bar that makes the feed a product instead of a listicle, and it is the prerequisite the expansion gate reuses.

**MOAT CHECKPOINT 4:** *Place is a tool LLMs call.* The graph is exposed as infrastructure with attribution flowing back; three seasonal claim types (waterfall, winter, wildflower) prove the tool cadence compounds off one graph.

## Phase 5 — The swim tool, done right (June 2027; hard date: 3 weeks before July 4, 2027)

**Deliverables:**
- "Swim Portland — swimming holes ranked by today's water": 40 swim-hole bindings on Clackamas @ Estacada (14210000) and Sandy @ Bull Run (14137000) — forged July–September 2026 in the private founder beta, verified through summer 2026, tightened again in spring 2027 — flow/temp thresholds, drive time, parking-full likelihood, hazard notes per spot. High Rocks ships with a year of tightened bounds behind its threshold, not a guess.
- Hazard-class affordances (cliff-jump, wild-swim) surface only through the full gate: recent verification AND currently-satisfied live trigger, always with provenance, last-verified date, assumption-of-risk framing.
- The definitive r/Portland swimming-hole post, one year late and one year better.

**GO/NO-GO — First-1,000 gate:** **20+ verifications/day and 5+ user-submitted claims/week.** Passing means the community, not the extraction pipeline, is the marginal source of graph growth.

**MOAT CHECKPOINT 5:** *The hazard-gated layer is live and trusted.* "Verified 6 days ago at 410 cfs" renders on real cards — the trust line no incumbent can show and no generic LLM will risk. Swim verifications under recorded flow begin calibrating the most liability-sensitive, highest-demand claim class.

## Phase 6 — Year-2 horizon (from July 2027)

**The expansion gate, stated as the rule it is:** metro 2 opens **only** when Portland holds the 60% feed quality gate *and* verification is on track to overtake extraction as the dominant claim support (the 12–18-month moat metric). Calendar pressure never opens a metro; a metro opened before its graph is dense enough burns the one first impression it gets. *One line on the alternative:* expanding on a funding-narrative timeline was rejected because a shallow metro 2 damages the brand that metro 1 earned.

- **Seattle via WTA partnership.** WTA is a partner, never a scraping target: a nonprofit data alliance — Place structures WTA's trip-report corpus into condition-bound affordances with attribution and traffic back; WTA's community becomes the verification seed. Portland already exercises the WA-side Gorge (Dog Mountain, Dougan Falls), so the bindings playbook has proven cross-state transfer before the partnership conversation starts.
- **MCP-driven distribution** becomes a real channel: aggregators and assistants calling `get_conditions` are recurring demand that cannot be satisfied by copying, because the copy rots in weeks.
- **Premium tier** (offline maps, advanced condition alerts beyond the free standing-query saves) ships when the retention base supports it; **Trip Builder** ships only once claim density supports the PAIRS_WITH_IN_WINDOW edges it needs — it exercises the graph but does not feed it, so it waits (per the deferral table in [02-PRODUCT.md](02-PRODUCT.md)).
- Burn discipline holds: <$50/month, one VPS, free government feeds, ~$20/month incremental extraction. The cached corpus appreciates — each model generation re-extracts denser claims from the same documents.

**MOAT CHECKPOINT 6 (the year-2 test):** *User verification is the dominant support for served claims.* The legal and strategic center of gravity now sits on data Place owns outright — the outcome log a 2028 entrant cannot recreate at any price, in any metro Place has lived in.

---

*Sibling docs: thesis and moat stack in [00-THESIS.md](00-THESIS.md); ontology and gates in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); loop and deferrals in [02-PRODUCT.md](02-PRODUCT.md); extraction and bindings program in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); migration and deployment in [04-ARCHITECTURE.md](04-ARCHITECTURE.md); incumbent analysis in [06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md).*
