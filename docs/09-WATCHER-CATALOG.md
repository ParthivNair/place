# The Almanac — Watchable Spec, Curation Gates & the Portland Launch Catalog

**In one breath:** The Almanac is the per-metro curated catalog of **watchables** — nameable, screenshot-worthy moments like "Haystack minus tides" and "first larch weekend" — and a watchable is *editorial, not machinery*: a named layer over condition windows that already exist in the graph, carrying a one-line promise, a **backtested expected open-frequency** ("opens ~6× a winter"), and a **published measured hit-rate**, with a retention rule that unpublishes anything crying wolf below ~70% precision. Nothing enters the shelf except through five curation gates that mirror the claim gates — executable predicate, sourced threshold, five-year backtest, full hazard inheritance, regions-never-pins for foraging — because the Almanac's honesty numbers are the product's honesty, rendered where a new user first sees it. This document owns the watchable anatomy, the naming rules, the gates, the ~25-entry Portland launch composition, the tooling gap (named honestly), and the Almanac's second job as the programmatic-SEO surface.

Vocabulary (window, window family, watchable, watcher, the Almanac, Vigilance) per [00-THESIS.md](00-THESIS.md) §8. The family doctrine and admission test are [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md); the thin schema sketch for watchables and watchers lives in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); the surfaces that render the Almanac, and all pricing and tier contents, live in [02-PRODUCT.md](02-PRODUCT.md).

---

## 1. What a watchable is

A watchable is **a curated, nameable moment**: an editorial object pointing at one or more condition windows (and through them, affordances) that already exist in the graph. "Haystack minus tides" is not new machinery — it is a name, a promise line, and two honesty numbers wrapped around the tidal window the evaluator has been executing since the coast bindings shipped. The DSL, the evaluator sweep, window state, and transition detection are untouched; a watchable adds *zero* new predicate machinery, and the moment one seems to need some, it is not a watchable — it is a missing binding, and it goes back to [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)'s forging program first.

Three consequences, committed:

- **A watchable can span windows.** "The Gorge going off" is open while three or more of its member falls' windows are open — a serve-time aggregation over member window states, computed at the editorial layer, never a new predicate class. Per-falls watchables and the grouped watchable coexist; watch either.
- **A watchable can be one-tap watched.** Watching a watchable creates a watcher — the same standing query the evaluator already re-runs on every sweep — that fires on the open transition. Windows open and close; watchers fire on the transition, never on readings.
- **The Almanac is curated — no user-authored predicates, ever.** The threshold *is* the product; the editorial judgment of what deserves a name is the voice. *Losing alternative, one line:* a user-facing predicate builder — IFTTT-for-feeds with no moat, no honesty numbers, and no editorial register ([00-THESIS.md](00-THESIS.md) §7 guardrails).

The Almanac is per-metro by construction — Portland's shelf first, transposed by the metro playbook (§7).

## 2. Anatomy of a watchable

| Field | Rendered? | What it is |
|---|---|---|
| **Name** | Public | Place + phenomenon, per §3. The thing people say out loud. |
| **Promise** | Public | One line stating the join in human words: "Tide under zero in daylight — the pools are out for about ninety minutes." |
| **Predicate refs** | Thresholds public | Pointers to the condition window(s) it names. The card renders satisfied leaves with live readings and provenance, exactly as feed cards do ([02-PRODUCT.md](02-PRODUCT.md)) — "under 1,200 cfs" is shown, because the shown threshold is the trust feature. |
| **Family** | Public | One of the six ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)). The Almanac shelves by family. |
| **Flags** | Public | `hazard` (inherits the full hazard gates, §4d), `dispersal` (regions-never-pins rendering, §4e), `conservative-copy` (health and surf-adjacent watchables state readings, never advice). |
| **Expected open-frequency** | Public | Backtested, stated plainly: "opens ~6× a winter." The honesty line, and the reason gate (c) exists. |
| **Measured hit-rate** | Public | Of pushed opens, the share confirmed worth it by responding watchers ("it was on" verdicts over the open→go→verify funnel). Ships once enough opens have been measured; the backtest frequency stands in until then, labeled as such. |
| **Current state** | Public | Open / closed, since when, last open. The SEO page's headline answer (§7). |
| **Watch count & activation rates** | **Internal only** | How many watchers stand on this watchable and how they respond when it opens — **moat M7, watch exhaust** ([00-THESIS.md](00-THESIS.md) §3). It curates the shelf, sequences the family ladder, and eventually prices Groundwire ([10-GROUNDWIRE.md](10-GROUNDWIRE.md)). **Watch counts never render publicly** — a popularity number on a place-anchored watchable is the Blue Pool failure mode wearing a UI badge. |

The storage is deliberately thin — a watchables table referencing `condition_windows` and `affordances`, sketched in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) — because everything load-bearing (state, transitions, provenance, confidence) already lives in the graph.

## 3. Naming and voice

The Almanac card is the acquisition unit. The October waterfall tool earns one r/Portland post; every watchable card has to be able to earn the next one — which makes **screenshot-worthiness a publication requirement, not a nice-to-have**. A card must stand alone as a screenshot: name, promise, live state, honesty line, provenance. If the screenshot needs a caption to make sense, the card is rewritten.

Rules, committed:

- **Place + phenomenon.** "Haystack minus tides." "First larch weekend." "Timothy Lake under $30." The name says where and what turns on — nothing else. (That last title is a threshold attribute of a reservation window, not pricing; prices and tiers live in [02-PRODUCT.md](02-PRODUCT.md) and nowhere else, including here.)
- **Field-guide register.** Sentences a ranger would say. Numbers beat adjectives: "1.6 in of rain in the last 72 h," not "absolutely roaring."
- **No marketing-speak, no superlatives.** Banned outright: "best," "epic," "ultimate," "hidden gem," "don't miss," "bucket list," urgency copy, exclamation points, emoji. The honesty line does the persuading — "opens ~6× a winter" is more compelling than any adjective because it is checkable.
- **The promise states the join, not the vibe.** Every promise line is a human-words rendering of the predicate, so the user learns what the engine actually watches — the same move as the feed's provenance line, and the same brand.

*Losing alternative, one line:* growth-copy naming ("10 INSANE waterfalls going off RIGHT NOW") — it buys one click and sells the register that makes the hit-rate line believable.

## 4. Curation gates

These mirror the claim publication gates in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §4: nothing auto-publishes, and the gates are code and process, not editorial mood. **A watchable publishes only when all five hold:**

**(a) Its predicate is executable in the DSL today.** No watchable ships waiting on machinery. If the moment can't be expressed as an existing-grammar predicate over feeds the adapters already poll, it isn't curated yet — it's a roadmap item for the family that would carry it.

**(b) Its threshold is sourced or founder-verified.** A watchable inherits the claim standing of the windows it names. A window whose threshold rests on a single unreviewed extraction cannot be dressed up with a nice name and shipped — the name makes the promise *more* prominent, so the evidence bar is the claim bar, never lower.

**(c) Its expected open-frequency is stated from a backtest against five years of historical feed data.** USGS NWIS serves decades of daily values; NOAA CO-OPS predictions and archives, Open-Meteo/NWS reanalysis, SNOTEL history — all free. Replaying a predicate over five years of archive is an afternoon of compute, and **the backtest is the honesty feature**: it produces the "opens ~6× a winter" line, and it catches both failure modes before users do — a predicate that never opened in five years is too tight (or the moment isn't real), and one that was open half the year isn't perishable and fails the spirit of admission gate G3 ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md)). One honest exception, named plainly: **Recreation.gov does not publish historical availability**, so reservation watchables cannot be backtested against a public archive — their frequency lines ship from Place's *own* poll logs, accumulated between the Phase 4 adapter build and the Phase 5 paid launch ([05-ROADMAP.md](05-ROADMAP.md)). No poll history, no published frequency, no reservation watchable.

**(d) Hazard watchables inherit the full hazard gates.** A watchable over a wild-swim, cliff-jump, or snow-travel window carries [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md) §4's gates unreduced: recent confirming verification within the class half-life, currently-true gate window, provenance and last-verified date and assumption-of-risk framing on every render. The Almanac never becomes a side door around the strictest gates in the product.

**(e) Dispersal-class watchables name conditions and regions, never pins.** The chanterelle rule: the watchable is "the flush is on in the Coast Range," never a dot on a map. Foraging watchables inherit the sensitive-sites posture in [02-PRODUCT.md](02-PRODUCT.md) §5 wholesale — the Blue Pool rule applies to mushrooms more than to anything else in the product.

**The retention rule:** watchers fire on state transitions only, never on readings; every watchable publishes its measured hit-rate; and **a watchable whose measured hit-rate falls below ~70% precision is unpublished** — pulled from the shelf, its threshold refit against the verification log, republished only when the backtest of the *new* predicate clears. Existing watchers are told why, in the same register: "we pulled this one because it was wrong 2 times in 5 — it comes back when it's right." This is the fifth refusal — not an alert firehose ([00-THESIS.md](00-THESIS.md) §7) — running as a weekly job instead of a slogan. The Sunday one-push cap stands throughout; watchable opens are the standing-query exception it always had.

## 5. The Portland launch composition

This table is Phase 0's "draft Portland watchable list" deliverable in canon form. **Every frequency below is a desk prior and ships only after the backtest replaces it** (gate c); flags: **H** = hazard-gated, **D** = dispersal-gated, **C** = conservative copy. "Ships" is the phase the watchable's family and gates allow, per [05-ROADMAP.md](05-ROADMAP.md).

| Watchable | Promise (one line) | Family | Flags | Expected opens (desk prior) | Ships |
|---|---|---|---|---|---|
| The Gorge going off | Three or more falls over threshold at once — the corridor is worth the drive | outdoor | — | ~6× a winter | P3 (Almanac v1) |
| Tamanawas flowing hard | An inch-plus of rain in 72 h on Cold Spring Creek — best 3–4 days | outdoor | — | ~8–12× Oct–May | P3 |
| Elowah after the rain | The quiet falls at full throat while Multnomah has the crowd | outdoor | — | ~8–12× Oct–May | P3 |
| Haystack minus tides | Tide under zero in daylight — the pools are out for about ninety minutes | outdoor | — | ~20 daylight runs/yr, summer-clustered | P3 |
| King tide mornings | The winter ocean at its biggest, watched from a real bluff, not the beach | outdoor | C | ~3–4 runs a winter | P3 |
| First snowshoe base at Hood | 30 in settled at the SNOTEL, avalanche danger moderate or below — the season is on | outdoor | H | ~1× a winter — and that's the point | P3 |
| Frozen falls cold snap | A hard multi-day freeze turns the Gorge to glass | outdoor | C | ~1–2× a winter | P3 |
| High Rocks swimmable | Clackamas under the verified threshold and genuinely hot | outdoor | H | opens early July most years; ~50 open days a summer | P5 (swim launch) |
| Clackamas–Sandy swim corridor | The corridor's holes over their thresholds, ranked by today's water | outdoor | H | tracks the hot season | P5 |
| Aurora at this latitude | Kp high enough to see it from a dark field at Portland's latitude | sky | — | ~2–5×/yr near solar max | P3 |
| Clear-dark new-moon night | New moon × clear sky × real darkness — worth the drive to a dark site | sky | — | ~1–3 nights per lunation outside the murk months | P3 |
| Perseids peak | The year's most reliable meteor shower, moon permitting | sky | — | 1×/yr (first opens Aug 2027) | P3 |
| Geminids in the cold | Winter's best meteors — if the clouds part | sky | — | 1×/yr (December) | P3 |
| Photographers' light | Gorge fog below, golden hour above | sky | — | a few mornings a month in fall | P3 |
| Balsamroot peak on Dog Mountain | Peak bloom on the permit hill — the yellow weekends, permit-aware | harvest | — | 1×/yr, ~2–3 week window | P4 (bloom tracker) |
| Tom McCall bloom | The plateau in full color, no permit required | harvest | — | 1×/yr | P4 |
| First larch weekend | The gold is on — usually two weekends, then done | harvest | — | 1×/yr (October) | P5.5 (harvest full) |
| Fall color by elevation | Peak color tracked band by band as it walks downhill | harvest | — | ~6-week rolling arc | P5.5 |
| Chanterelle flush, Coast Range | Four to ten days after the first 2-inch October rain — conditions and regions, never pins | harvest | D | ~1–3 flushes a fall | P5.5 |
| First u-pick strawberries | The flats are ready — about three good weeks | harvest | — | 1×/yr (June; first full window Jun 2028) | P5.5 |
| Timothy Lake under $30 | A July weekend site just opened — cancellations go in minutes | reservation | — | from Place's own poll archive (gate c exception) | P5 (paid anchor) |
| Multnomah timed-entry drop | Permits just released for the dates you want | reservation | — | schedule-driven, in season | P5 |
| Trillium Lake weekend opens | A summer Saturday under the mountain just came back | reservation | — | from Place's own poll archive | P5 |
| First smoke-free morning | AQI back under the bar after a bad stretch | health | C | ~2–6× a smoke season | P5.5 (smoke seed) |
| Heat-safe kid hours | The morning window before the heat closes in | health | C | most heat-advisory days | P5.5 |

Two composition notes, honest ones:

- **Almanac v1's shelf reaches ~25 at Phase 3 by splitting, not by rushing.** Only the outdoor and sky rows above are gate-passable in November 2026 — so v1 fills its shelf by splitting "The Gorge going off" into per-falls watchables for the most-asked members (Wahclella, Latourell, Punch Bowl, Multnomah and their neighbors), whose bindings already exist from the Phase 2 launch ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md)). The harvest, reservation, and health rows stage in on [05-ROADMAP.md](05-ROADMAP.md)'s calendar as their families ship. The shelf is never padded with watchables whose gates don't pass.
- **What's deliberately absent.** No pollen watchable — there is no free machine-readable pollen feed, so it fails family admission gate G1 outright ([08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) F5). No crowd watchable — "Multnomah before the mob" waits until Place's own verification exhaust can *be* the feed (F6). The empty slots are the gates working.

## 6. Curation tooling — the honest gap

**The admin queue covers claims, not watchables.** The review queue in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §2 drains extracted claims to published or suppressed; nothing in the stack today can create a watchable, run its backtest, or watch its hit-rate. Three tools are named roadmap deliverables, not hand-waves ([05-ROADMAP.md](05-ROADMAP.md)):

1. **Backtest runner (Phase 1, with the bindings program):** replay a predicate over five years of archived feed history — USGS/NOAA/Open-Meteo/SNOTEL archives are free, which is why this is an afternoon of compute per watchable, not a project — emitting open transitions, durations, and the expected-frequency line that gate (c) requires.
2. **Editorial CRUD (Phase 3, with Almanac v1):** create/edit/publish/unpublish watchables — name, promise, predicate refs, flags — with gate checks enforced at publish time, the same way claim gates are enforced in code, not memory.
3. **Hit-rate dashboard (Phase 3, with funnel telemetry):** pushed opens × responding verdicts × per-watchable precision, feeding the ~70% retention rule as a weekly job, plus the internal watch-exhaust view (M7): watchers held, activation on open, the demand map that curates next season's shelf.

Until Phase 1, watchable curation is the founder, SQL, and a spreadsheet — stated plainly so nobody mistakes the Phase 0 desk-draft above for a shipped system.

## 7. The Almanac as SEO surface

Every watchable is also **a daily-regenerated public page whose headline is the question and whose answer is live state**: "Is the larch window open right now?" — open/closed, since when, last open, expected frequency, measured hit-rate, provenance. This generalizes the October waterfall tool's programmatic-SEO play ([02-PRODUCT.md](02-PRODUCT.md) §4, [05-ROADMAP.md](05-ROADMAP.md) Phase 2) from one seasonal tool to the whole shelf: each of the perennial questions — "are the Gorge waterfalls flowing," "aurora forecast Portland tonight," "when is chanterelle season" — is a question with a perishable answer, and a page regenerated daily with live sensor state structurally beats every static listicle competing for it. The page's one call to action is the graduation funnel's first step: *Watch this — we'll tell you when it opens.*

The product rules follow the pages: dispersal watchables get region pages with conditions and no pins; hazard watchables render only through their full gates, with the assumption-of-risk framing intact; every page is a ranked list or a single honest state line, never a viral single pin.

Per metro, the Almanac slots into **step 6 of the metro playbook** ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §6): the metro's first seasonal tool ships *with its watchables* — the tool is the front door, the watchables are what a visitor can leave holding, and the SEO pages start compounding from the metro's first week. A new metro's shelf starts from this catalog as a template — every metro has a first-snow, a bloom, a flush, a cancellation worth watching — with local bindings forged before a single name is published, because the gates transpose with everything else.

---

*Siblings: thesis and vocabulary in [00-THESIS.md](00-THESIS.md); family doctrine and admission test in [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md); schema sketch in [01-EXPERIENCE-GRAPH.md](01-EXPERIENCE-GRAPH.md); surfaces, pricing, and the Vigilance household tier in [02-PRODUCT.md](02-PRODUCT.md); feeds and the metro playbook in [03-DATA-STRATEGY.md](03-DATA-STRATEGY.md); the calendar in [05-ROADMAP.md](05-ROADMAP.md); the endgame these numbers eventually price in [10-GROUNDWIRE.md](10-GROUNDWIRE.md).*
