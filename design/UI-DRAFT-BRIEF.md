# UI first-draft brief — Claude Design prompt pack

Working document for drafting the first full app UI in Claude Design (claude.ai/design,
project "Place"), to be refined in Figma. Compiled July 2026 from the docs canon
(00–07), the design system (this directory), and the live FastAPI surface. This file
extends the canon; it does not re-derive it. When a screen stabilizes in Figma,
translate it back into one `.html` surface card here and re-sync — the loop in
[README.md](README.md) §Workflow.

**The one-sentence steer for every prompt:** the 17 synced cards are components and
card-level surfaces; **no full-page composition exists yet**. Every prompt below asks
Claude Design to *assemble* pages from named existing cards, never to reinvent them.

---

## How to prompt (the method)

1. **One screen per conversation.** Never "design the app." Each chat owns one screen
   and its full state matrix; start fresh per screen so the design system, not chat
   history, is the anchor.
2. **Name the cards.** Every prompt lists which existing preview cards compose the
   screen ("assemble from `experience-card` variant A, `feed-filters`,
   `provenance-line`…"). Claude Design's leverage is the Design System pane — pointing
   at cards by name is what keeps the draft on-system.
3. **Paste the constraint block** (below) into every prompt, verbatim. It reads as
   hard rules, and every one of them is canon, not taste.
4. **Demand states, not screens.** The product's differentiation *is* the degraded
   states (stale-as-of, live-unavailable, short feed, hazard-suppressed, signed-out).
   Every prompt enumerates its state matrix; a happy-path-only draft is a failed draft.
5. **Feed it real data shapes.** Mock data is canon data (README rule 5), and field
   names come from the live API (cheat sheet at the bottom). Never let it invent
   fields the backend doesn't serve — photo URLs and drive-time minutes are the two
   it will want to invent (see Open decisions #4, #5).
6. **Make the open decisions yourself, in the prompt.** Where canon is silent
   (navigation, planned_date default, verdict labels), state the proposal from the
   Open-decisions table and mark it `PROPOSAL` — don't let the model decide product.
7. **Critique in tokens, not vibes.** Iterate with "that amber should be
   `--condition-fading`," "the count line is meta, so 13px floor," "that's a third
   action — cards carry exactly two." Vibes-feedback drifts off-system; token-feedback
   converges.
8. **Screenshot-worthiness is a requirement, not polish.** Condition-magic cards are
   the go-to-market (they get posted to r/Portland). Ask explicitly: "would this card,
   cropped alone, make someone ask what app it is?"

---

## The constraint block (paste into every prompt)

```
HARD CONSTRAINTS (from product canon — not preferences):
- Use the Place design system. tokens.css is law; colors only from tokens.
  Direction: "field guide meets instrument panel" — warm paper, fir-green ink,
  hairline borders as the only chrome, --shadow-card the highest elevation.
- Mobile-first PWA at 400px viewport, cards 368px. Five type sizes only
  (20/18/16/15/13); body ≥16px, meta ≥13px hard floor; touch targets ≥44px;
  4px grid; radii: card 14 / control 10 / chip pill.
- Every measured number (cfs, inches, °F, minutes, times) uses the .data class:
  monospace, tabular figures. Claim words ("moderate") stay in the UI font.
- Glyphs, single source: ⚡ weather-triggered live · ● other live · ○ unknown
  (hollow) · ✓ verification only · ♡/♥ saves only · → tertiary/link-out.
- Every card and claim shows its provenance line — live reason + source +
  freshness where available, claim provenance + last-verified otherwise.
  NO bare ranks, anywhere, ever.
- Cards carry exactly two actions: filled-forest 48px primary + borderless
  quiet tertiary. No outlined secondary exists in this system.
- No stars, no badges, no points, no streaks, no review composer, no "How was
  it?". Recognition is named provenance credit only ("verified Sun by @gorge_amy").
- No hero pins, no map-hero layouts, no spotlight. Every public list is ten
  ranked options — dispersal is designed in at the rendering layer.
- Hazard content renders only with assumption-of-risk copy in the hazard-tint
  well: "Conditions change quickly — a recent verification is not a guarantee.
  You are responsible for your own judgment."
- Freshness honesty: readings older than 2× feed cadence render "as of ⟨time⟩";
  degraded feeds say "live flow unavailable", never "conditions bad"; stale
  tends toward unknown (○), never toward false.
- Mock data is canon data, verbatim: Tamanawas Falls (41 min, ⚡ 1.6 in rain in
  72h, NWS, verified Sun by @gorge_amy) · High Rocks, Clackamas @ Estacada
  (gauge 14210000) at 980 cfs, threshold <1,200, last verified June 27 at
  1,010 cfs · 3 sources · Dog Mountain balsamroot · Springville Trailhead
  (14 min) · Steeplejack Brewing · Northwest Forest Pass · Multnomah Falls
  timed-use permit.
```

---

## Drafting order

Priority follows the loop and the calendar: the **feed** is the product, the
**seasonal ranker** ships publicly first (October 2026), and the **verdict sheet**
carries the First-100 gate (≥30% verification). Admin stays deliberately plain.

| # | Screen | Why this position |
|---|--------|-------------------|
| 1 | "This Weekend" feed (full page) | The home screen; everything else hangs off it |
| 2 | Place page (below the header) | Biggest unstyled surface; where "more conditions →" lands |
| 3 | Sunday verdict sheet + push | The First-100 gate lives here |
| 4 | Seasonal ranker (full page, mobile + desktop) | Public launch #1, October 2026; the only desktop surface |
| 5 | "I'm going" confirmation | Entry point to the Sunday loop; nearby-after telemetry |
| 6 | Saves / want-to-been-loved list | Was deliberately deferred; the full draft now forces it |
| 7 | Magic-link auth flow (3 screens) | The conversion moment; intercepts first save |
| 8 | Onboarding (location → install → push) | P5's trust gate; iOS install-for-push |
| 9 | Cross-cutting states sheet | Offline, degraded, 401, error toasts — design once |

---

## Per-screen prompts

Each prompt = context line + composition + state matrix + decisions + constraint
block. Copy the whole fenced block, then append the constraint block.

### 1 · "This Weekend" feed

```
Design the home screen of Place, a mobile PWA (400px): the Thursday "This
Weekend" feed — ranked experience cards for the next 48–72h within a 90-minute
drive, each carrying a live, provenance-backed reason it ranks now.

Assemble from existing design-system cards: experience-card (variant A
condition-magic, variant B everyday, variant C hazard-gated), feed-filters,
provenance-line, condition-badge, affordance-strip, safety-line, buttons.

Page structure: header ("This Weekend · ranked by live conditions" + honest
count line, e.g. "7 places worth it this weekend") → activity-verb filter field
(hint: "Try 'trail', 'swim', 'walk'") → exactly three filters (drive time
30/60/90 · activity · dogs/kids) → card stack. Everyday cards form the base
layer; condition-magic cards rank on top. The feed SHORTENS when the ≥60%
live-reason quality gate fails — it never pads.

States to design: (a) full feed, 10 cards, mixed magic/everyday; (b) short
honest feed, 3 cards, with the count line owning the honesty; (c) zero-card
state — PROPOSAL copy: "Nothing worth the drive this weekend. We'd rather say
so."; (d) verb-filtered state ("swim") with active chip + clear affordance;
(e) location permission not yet granted — manual location entry; (f) signed-out
(feed is public; only ♡ intercepts to auth).

Decisions made for this draft (render, don't re-decide): PROPOSAL — no tab
bar; feed is home, with a quiet top-right avatar/menu reaching saves and
settings. Cards are photo-less at launch (no image pipeline yet) — the
provenance block is the visual hero. Distance renders as drive-time minutes
per canon copy ("41 min drive").
```

### 2 · Place page

```
Design the Place page for Place (mobile PWA, 400px) — "a rendering of the
graph, not a wiki article." Use High Rocks as the canon example. This is also
a verification surface: every claim row carries one-tap confirm/deny/changed.

Assemble from: place-page-header (exists — design everything BELOW it),
claim-row (all 4 variants), condition-badge, verdict-controls, nearby-after,
safety-line (incl. closure variant), provenance-line.

Page order below the header: (1) "What you can do here" — affordance sections,
each with verb · difficulty · duration · dog/kid flags and its CURRENT window
state with live sensor value: "wild-swim · currently swimmable · Clackamas @
Estacada (14210000) at 980 cfs, threshold <1,200 · last verified June 27 at
1,010 cfs · 3 sources"; (2) claims under each affordance as claim-rows with
provenance, observed date, decayed confidence, inline verdict controls;
(3) access & stewardship (permit, parking note, Leave No Trace); (4) "Nearby
after" module (brewery/diner/soak rows — never standalone destinations);
(5) source citations that link OUT (Oregon Hikers gets traffic, quotes are
never republished).

States: (a) all-live High Rocks; (b) hazard affordance suppressed — "Not shown
— needs a recent verification and a live trigger"; (c) stale reading — "as of
Tue 4pm" treatment; (d) window unknown (○, basalt); (e) a "more conditions"
detail: PROPOSAL — an inline-expanding condition sheet per affordance showing
each window (state, since-when, live ReasonOut provenance popover), not a
separate route; (f) post-verdict claim row: confidence visually refreshed —
verifying should feel like refreshing the place for everyone.
```

### 3 · Sunday push + verdict sheet

```
Design the Sunday 6pm push flow for Place (mobile PWA, 400px): OS notification
→ deep-linked verdict sheet → next-weekend hand-off. One push per week, hard
cap. This screen carries the product's make-or-break metric (≥30% of tracked
visits answer at least one question). Questions are about claims, never
experience: "Was the pool swimmable?" — one-tap favors, not reviews.

Assemble from: sunday-push (notification, verdict sheet, re-engagement
mini-card), verdict-controls (idle / answered-confirm / answered-deny /
compact), experience-card (mini), condition-badge.

Sheet structure: "You went to High Rocks — two taps and you're done" → at most
TWO one-tap claim questions → answered state shows the auto-attached snapshot:
"Thanks — logged with conditions at 990 cfs, 82°F" → "Next weekend" mini-card
+ "see the feed →". Deny framing is no-penalty: "A no is worth as much as a
yes."

States: (a) two questions pending; (b) one answered, one pending; (c) all
answered + next-weekend card; (d) feed-only variant (user never tapped "I'm
going" — zero questions, never ask about a trip we don't know happened);
(e) "changed" tapped — PROPOSAL: single quiet confirmation "Noted — we'll
re-check this claim", no follow-up form; (f) already-answered (409) — "Already
logged this week ✓"; (g) expired session — magic-link re-entry that preserves
the pending verdict.
```

### 4 · Seasonal ranker — "Gorge waterfalls by current flow"

```
Design the public launch surface of Place: a free, no-login page ranking ten
Gorge waterfalls by TODAY's flow (72-h NWS precip + creek gauges). It loads in
two seconds, gets posted to r/Portland timed to the first big October rain,
regenerates daily, and doubles as the SEO page "best waterfalls near Portland
right now". It must be screenshot-worthy — the screenshot IS the acquisition.

Assemble from: seasonal-ranker (exists as a card — design the full page
around it), provenance-line, condition-badge, safety-line, buttons.

Two viewports: 400px mobile AND a desktop rendering (single centered column,
max ~680px — dispersal rules forbid map-hero layouts; this is the app's only
real desktop surface, for SEO traffic).

Page: title treatment worth screenshotting ("Gorge waterfalls, ranked by
current flow — updated this morning") → ten ranked rows, each: rank · name ·
live flow driver (⚡ + .data numbers) · drive time · last-verified · permit
note where real (Multnomah timed-use) → ♡ on each row → footer: "how we know"
methodology line + Leave No Trace + ToS/assumption-of-risk.

The conversion moment: tapping ♡ opens the email capture — pitch verbatim:
"We'll tell you when it's flowing hard." No password. One field, one button,
one line of reassurance ("One email when conditions fire — that's it.").

States: (a) big-rain day (everything firing); (b) dry-spell honesty (rows
carry "fading" amber states, count line honest); (c) post-save confirmed row
(♥ + "watching this for you"); (d) the email-sent interstitial.
```

### 5 · "I'm going" confirmation

```
Design the "I'm going" confirmation sheet for Place (mobile PWA, 400px). The
tap is the ENTIRE ask — no check-in, no tracking, no GPX. The sheet confirms
intent, snapshots conditions invisibly, sets the Sunday expectation, and
offers the nearby-after module.

Assemble from: nearby-after (exists), buttons, condition-badge,
experience-card (header condensed).

Sheet: confirmation ("You're going to Tamanawas Falls — Saturday") with
PROPOSAL: planned_date defaults to next Saturday, editable via two quiet
chips [Sat] [Sun] + a tertiary "another day →" — never a date-picker form →
conditions-at-decision line (what it was served under, .data figures) →
"Nearby after" rows (Steeplejack Brewing · brewery · 12 min · →; tapped state
= forest-tint "✓ noted") → Sunday expectation, one line: "We'll ask two quick
questions Sunday evening." → "Directions →" as the tertiary action, deep-link
to Google Maps (the committed last-mile hand-off — Place never does
navigation).

States: (a) default; (b) nearby row noted; (c) signed-out intercept — the
magic-link ask appears INSIDE the sheet without losing the intent; (d) the
saved-for-Sunday confirmation toast.
```

### 6 · Saves — want-to / been / loved

```
Design the saved-places view for Place (mobile PWA, 400px). Three kinds of
save — want-to, been, loved — with NO lists-of-lists UI. The core concept:
a save is a STANDING QUERY, not a bookmark. Every want-to is a sensor
watching the outdoors on the user's behalf; the view must make that visible.

Assemble from: place-page-header's save triplet, condition-badge,
provenance-line, alert-card, claim-row (compact).

Structure: PROPOSAL — one list, three filter chips (want-to · been · loved),
want-to default. Each want-to row: place · what it's watching ("watching:
Clackamas < 1,200 cfs") · current window state glyph (⚡/●/○) · "alerted
May 12" where last_alerted_at exists. Been/loved rows are quieter — place ·
date · (loved: ♥).

The alert moment: an alert-card at top when a standing query fired —
"Dog Mountain balsamroot peaking — you saved this in January." PROPOSAL:
alerts are push-first with this one in-app echo slot; no inbox.

States: (a) active list with one fired alert; (b) all-quiet (every watched
window ○/dormant — "nothing firing; we're watching 6 places for you");
(c) empty ("Save a place and we'll watch conditions for you"); (d) been-filter
view; (e) signed-out (this surface requires the session — magic-link ask).
```

### 7 · Magic-link auth (three screens)

```
Design the auth flow for Place (mobile PWA, 400px): magic-link email, no
passwords, triggered ONLY by the first save/going/verdict — never before
value. Sessions last ~180 days; auth should feel nearly invisible.

Three screens: (1) email ask — one sentence of pitch, contextual to the
trigger ("We'll tell you when it's flowing hard." for a save), one field, one
48px primary; (2) check-your-email interstitial — sender, 15-minute validity,
quiet resend after 60s; (3) the /auth/verify landing — success ("You're in —
finishing your save…" then intent completion) and failure ("That link
expired — they last 15 minutes" + resend).

States: expired token, invalid token, resent confirmation, and the
returning-user variant (recognized email, same flow, softer copy).
Signed-in identity appears ONLY as display-name provenance credit — there is
no profile page in v1 beyond settings.
```

### 8 · Onboarding — location, install, push

```
Design first-run onboarding for Place (mobile PWA, 400px). Philosophy: value
before asks — the feed renders before any permission. Three asks, sequenced,
each skippable: (1) location — required for the feed to mean anything;
graceful denial path = manual neighborhood entry; (2) PWA install — part of
onboarding, not an afterthought (iOS needs Home-Screen install for push);
(3) push opt-in framed as the cadence promise: "One push a week, Sunday 6pm.
That's the deal." plus standing-query alerts for saved places.

Include the one-screen privacy posture (P5 requirement): plain language, big
type — what's collected (email, saves, one-tap verdicts with auto conditions),
what's never collected (no tracking, no GPS traces, no ad data), one screen,
no legalese.

States: each ask + its denial fallback; the "installed, push granted" done
state lands on the feed.
```

### 9 · Cross-cutting states sheet

```
Design a states reference sheet for Place (one artboard of paired examples,
mobile 400px) covering the degraded modes every screen shares: (a) offline
shell — last-cached feed, every reading stamped "as of ⟨time⟩", banner "You're
offline — showing Thursday's feed"; (b) live-source-down card — "live flow
unavailable" + seasonal-prior rank, NEVER "conditions bad"; (c) stale reading
("as of Tue 4pm"); (d) 401 re-auth interstitial preserving the interrupted
action; (e) error toasts: 404 (place unavailable), 409 (already logged),
422 (quiet retry); (f) loading skeletons that respect the card anatomy (no
spinner-only screens).
```

---

## Open decisions the draft must take a position on

Marked `PROPOSAL` in the prompts above; change here first if you disagree.

| # | Decision | Proposal baked into the prompts |
|---|----------|-------------------------------|
| 1 | Global navigation | No tab bar. Feed = home; avatar/menu → saves, settings. Place pages and sheets by tap/deep-link only. Anti-browse product, anti-browse chrome. |
| 2 | Verdict labels | UI says confirm / **deny** / changed; client maps deny → API `refute`. |
| 3 | Assumption-of-risk copy | Render the server string verbatim (single legal source); reconcile tokens copy to match. |
| 4 | Hero photos | Photo-less card is the launch reality (no image pipeline). Provenance block is the visual hero. Design the photo variant as future state only. |
| 5 | Drive time | Canon copy wins: render minutes. Client converts `distance_km` with a stated heuristic until the backend serves minutes. Flag: API gap. |
| 6 | Zero/short feed copy | "Nothing worth the drive this weekend. We'd rather say so." |
| 7 | Forward-looking windows | A reason-line style ("● minus tide Saturday 7:12 am"), not a date picker. |
| 8 | "more conditions →" | Inline-expanding condition sheet on the place page, not a separate route. |
| 9 | planned_date | Defaults to next Saturday; [Sat]/[Sun] chips; never a form. |
| 10 | Saves list | One list + three filter chips; standing-query state visible per row; no alert inbox (push + one in-app echo slot). |
| 11 | Auth interception | Inline inside the triggering sheet; intent resumes after verify. |
| 12 | Onboarding order | Feed first → location → install → push; each skippable. |
| 13 | Desktop | Only the seasonal ranker/SEO pages; single centered column ~680px. |
| 14 | Maps | No map in v1 anywhere. Text access context + "Directions →" deep link. |
| 15 | Sunday sheet reachable in-app | Yes — the same claim questions are reachable from place-page claim rows, so the surface isn't push-only (push sending is PR-9, not built). |

## API cheat sheet (design real shapes)

- `GET /feed?lat&lng` → `{generated_at, count, cards[]}`. FeedCard: `place_name`,
  `place_kind`, `distance_km` (no drive-time field — see decision 5), activity +
  `difficulty` + `typical_duration_min` + `dog_ok/kid_ok`, `hazard_class`,
  `now_score` (rank by, never print), `reasons[]` (wtype, composed `text` with
  "(as of …)" already handled, `source` like "usgs 14105700", `fresh`,
  `provenance[]` for the popover), `live_unavailable[]`, `last_verified_at` +
  `verified_by`, `assumption_of_risk` (hazard only — must display),
  `verdict_controls[]` `{claim_id, allowed_verdicts}`. **No photo URL.**
- `GET /places/{id}` → affordances with windows (`wtype`, `is_gate`, `state`
  true/false/unknown, `state_since` → "opened Tuesday" copy, `live: ReasonOut`)
  and claims (`cclass`, `source_type`, `source_url`/`source_domain` for
  link-outs, `observed_date`, decayed `confidence`, `allowed_verdicts`). Hazard
  is pre-gated server-side; sensitive places 404.
- `POST /saves {affordance_id, kind}`; `GET /saves` includes `last_alerted_at`.
- `POST /trips {affordance_id, planned_date}` — **no GET /trips**; client keeps ids.
- `POST /verdicts {claim_id, verdict: confirm|refute|changed, trip_id?}` →
  new `confidence` + `conditions_snapshot` (the "logged at 990 cfs, 82°F"
  moment); 409 when already recorded (one per trip per 24h).
- Auth: `POST /auth/magic-link` (always 202) → `POST /auth/verify` (15-min
  token, ~180-day cookie). PWA must host `/auth/verify?token=…`.
- Push: subscribe endpoints exist; **sending is not built (PR-9)** — the
  Sunday push screen ships dark, reachable in-app per decision 15.
- Not served yet (design the slot, flag the gap): photos, drive-time minutes,
  nearby-after/PAIRS_WITH, trips list, logout, name edit, alert history,
  admin metrics, crowd/parking priors.
