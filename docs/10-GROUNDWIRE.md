# Groundwire — The Freshness-Certificate Endgame

**In one breath:** Groundwire is the year-2+ API face of the window engine: **signed, expiring freshness certificates** — a claim, its provenance, its last-verified timestamp, a live condition snapshot, a calibrated confidence, and an expiry — served to AI assistants over MCP, with **perishability as the rate card**. It is not a second business; it is the same engine turned outward. Consumer vigilance funds it and manufactures the verification exhaust it sells ([00-THESIS.md](00-THESIS.md) §5), and it ships only when the graph is dense enough that **assistants need it more than users need another app**. Nothing here exists yet beyond its Phase 4 precursor, and this document is written accordingly: it is an endgame doc, not a spec.

---

## 1. Why assistants must call it

2026-class assistants take exactly the queries they cannot keep: local conditional questions ("is the water low enough for the kids this weekend?") and, increasingly, **standing orders** ("tell me when the aurora is worth waking up for"). They fail for the reasons committed in [06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md) §3: no verified local thresholds, no live joins across public feeds, and no answer to the question that decides trust — *was this true recently, according to a human who was there?* Web search retrieves prose; a standing order needs a predicate, and a predicate needs a threshold somebody forged.

The certificate is the only artifact that answers with an audit trail. And the audit trail is a product twice over: it is also **the liability shield platforms need for hazard-adjacent answers**. Scale forces incumbents and frontier labs to suppress exactly the highest-demand local categories — no cliff jumps, no wild-swim endorsements ([06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md) §5) — but a signed certificate carrying a recent human verification, a live condition snapshot, and an expiry is precisely the artifact that lets a platform answer instead of hedge. Groundwire sells the liability asymmetry that was previously only our defensive posture.

## 2. The surface

Groundwire evolves from the **Phase 4 MCP server** ([05-ROADMAP.md](05-ROADMAP.md)) — `search_experiences` / `get_conditions` over the same graph the PWA reads. The committed evolution:

- **Certificates become the response unit.** `get_conditions` returns state today; Groundwire returns a *signed statement about state that expires*. Same join, different artifact.
- **A `get_local_state` generalization follows the family ladder.** One answer-space that grows a family at a time per [08-WINDOW-FAMILIES.md](08-WINDOW-FAMILIES.md) — no family is served over the API before it has passed the admission test and accrued verifications on the consumer surface.
- **The static-pack compiler — already running — is the stale-tier price fence.** Geometry, seasonal windows, the slow-decaying share of the graph: generous to free, because that layer is the drawbridge, not the castle. The fresh tier — `good_now`, last-verified timestamps, certificates — stays gated behind attribution and rate terms, exactly as committed in the tool position ([06-COMPETITIVE-LANDSCAPE.md](06-COMPETITIVE-LANDSCAPE.md) §3).

Losing alternative, one line: a conventional REST developer portal — MCP is where assistant demand actually arrives, and a solo operator ships one machine-facing surface, not two.

## 3. The rate card is perishability

A certificate is priced by how fast it rots. Decades-scale facts (the waterfall exists) are near-free; weeks-scale facts (access claims, seasonal windows) are cheap; the hours-to-minutes tier — swimmable *now*, the window that just opened, the cancellation that will be gone by lunch — is the premium product, because that is the tier no copy of the graph can hold. The caller is not buying data; it is renting freshness, which is why last month's bulk copy is worthless and callers must keep calling.

**M7 watch exhaust sets the rates** ([00-THESIS.md](00-THESIS.md) §3). The demand map of what a metro's households actually wait for — which watchables, at what thresholds, with what open→go activation — is the same demand map of what assistants will be asked. Per-family, per-metro rates get priced from observed standing demand, not guessed: the reservation family's certificates are worth more in July, the sky family's on a clear new-moon weekend, and we will *know*, because the watchers told us. No incumbent can build this rate card, because no incumbent can observe standing demand.

## 4. Why year-2+, honestly

Three reasons, none hand-waved:

1. **Platforms will not pay meaningfully for a one-metro graph.** Groundwire's buyer needs coverage; density in Portland plus a proven transposition playbook ([03-DATA-STRATEGY.md](03-DATA-STRATEGY.md) §6) is the minimum credible offer, and that is a year-2 asset by the calendar in [05-ROADMAP.md](05-ROADMAP.md).
2. **MCP monetization and attribution rails are immature.** As of mid-2026 there is no settled way to meter, attribute, and bill assistant tool calls at platform scale. Building a bespoke billing rail ahead of the ecosystem is founder-hours spent on plumbing that will be standardized under us.
3. **Cold start is real, and the consumer flywheel is the only funding path.** The Vigilance household tier ([02-PRODUCT.md](02-PRODUCT.md)) pays the bills while the graph densifies — and the consumer surface is never outsourced, because **API callers do not generate verifications**. An assistant that consumes a certificate never taps "still swimmable"; households do. Groundwire spends verification exhaust; it cannot manufacture it.

## 5. What Groundwire never does

- **Never bulk-exports the graph.** A one-time dump prices the asset at its stale value — the exact opposite of the perishability thesis. Certificates, not copies.
- **Never signs an exclusive license that starves the consumer surface.** Exclusivity trades the flywheel for a check; the flywheel is the company.
- **Never issues a certificate without an expiry.** An unexpiring certificate is a claim we no longer stand behind wearing a signature we do. Expiry is the product.

## 6. Kill risk, named honestly

The kill risk: **assistants settle for web-search-plus-maps grounding for 95 percent of local queries and will not pay for the last 5.** Good-enough generic grounding, hedged answers accepted by users, no budget for certificates. This is a real scenario, not a strawman.

The counter is empirical, not rhetorical: the **WHEN-form benchmark delta** ([05-ROADMAP.md](05-ROADMAP.md) Phase 0, re-run against current frontier models every year). Standing orders are precisely where generic grounding fails hardest — you cannot web-search a threshold that was never written down, and you cannot keep a "tell me when" without a live join and a watcher standing on it. As long as the benchmark shows frontier assistants failing WHEN-form queries, the last 5 percent is exactly the percent users escalate about, and the certificate is the only fix on the market. If the delta collapses — if generic grounding starts genuinely keeping standing orders — Groundwire dies before it ships, and the consumer business must stand alone. That is survivable by design; the reverse dependency would not be.
