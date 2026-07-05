# Place design system

Source for the Claude Design project (claude.ai/design). Each `.html` file is one
self-contained preview card; [tokens.css](tokens.css) is the single source of truth
every card inlines. Direction: **"field guide meets instrument panel"** — warm paper
and fir-green ink, with sensor data always in monospace tabular figures, because the
provenance line is the brand (docs/00 §1).

## Rules every card follows

1. First line is the card marker: `<!-- @dsCard group="..." name="..." -->` —
   the Design System pane indexes cards from this comment.
2. Self-contained: tokens inlined in a `<style>` block, no external fonts, images,
   or scripts. Hero photos are placeholder swatches.
3. Colors only from tokens.css. If a component needs a color that isn't a token,
   the token file changes first.
4. Canon constraints are design constraints: no stars, no badges, no point counts
   (docs/00 §6); body text ≥16px, meta ≥13px, touch targets ≥44px (docs/07 P5);
   hazard styling only with assumption-of-risk text (docs/02 §5); every card
   variant shows a provenance line — no bare ranks (docs/02 §2).
5. Mock data is canon data: Tamanawas Falls, High Rocks @ 980 cfs on gauge
   14210000, Dog Mountain balsamroot, @gorge_amy, Steeplejack. Keeps every
   design review doubling as a product review.

## Layout

```
design/
  tokens.css            source of truth — edit here first
  foundations/          colors · typography · spacing
  components/           card parts: provenance line, condition badge, buttons,
                        verdict controls, affordance strip, safety line, claim row
  surfaces/             assembled: experience card, feed filters, place page
                        header, nearby-after, alert card, Sunday push, seasonal
                        ranker
```

## Canonical decisions

- Glyphs: `⚡` weather-triggered live reason · `●` other live (hydro/tidal/seasonal/
  ephemeris) · `○` unknown/signal-absent · `✓` verification only · `♡/♥` saves only
  (hollow = unsaved, filled = saved) · `→` tertiary action / link-out.
- Cards carry exactly two actions: filled-forest primary (48px) + borderless quiet
  tertiary text button. No outlined secondary exists in this system.
- Assumption-of-risk copy is fixed product language: "Conditions change quickly —
  a recent verification is not a guarantee. You are responsible for your own
  judgment." Always in the hazard-tint well from
  [safety-line](components/safety-line.html).
- Surface 3's saved-places list view has no card yet — deliberate. Saves exist as
  controls (buttons, place-page header) and as the condition alert; the list view
  gets designed when PR-8 needs it.

## Workflow

- **Sync up:** done from Claude Code via the DesignSync tool (list → plan →
  write). Sync is incremental — one component at a time, never a wholesale replace.
- **Figma loop:** redesign a component in Figma → translate the result back into
  that one `.html` file (update tokens.css first if the redesign changes
  primitives) → re-sync just that file. The Claude Design project stays the
  living contract between Figma and the Next.js PWA (docs/04 PR-8).
- When PR-8 starts, tokens.css becomes the seed for the PWA's global CSS /
  Tailwind theme — components here are the spec the React components implement.
