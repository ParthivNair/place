/* Fixture for /waterfalls — the seasonal ranker, public launch #1
   (docs/02 §4, UI-DRAFT-BRIEF §4). NO ranker endpoint exists in the API
   yet (flagged gap: a GET /rankers/waterfalls should serve this shape);
   until it does, this file is the page's only data source.

   Ten real Columbia River Gorge waterfalls. Canon figures are reused
   verbatim where they exist: Multnomah Falls' dry-spell reading is the
   canon stale card from mock.ts (0.8 in / 72 h, nws PDX, as of Fri 4pm,
   discharge feed down), and its timed-use permit is the canon permit
   note. Tamanawas Falls is Hood, not Gorge — excluded on purpose.
   Row figures without a canon source are invented and flagged in the
   drafting report. Reasons keep the FeedCard ReasonOut shape so the
   future endpoint slots in without a rerender rewrite.

   Scenario switch (UI-DRAFT-BRIEF §4 states a/b): flip RANKER_SCENARIO
   below — a fixture constant, never a user-visible toggle. */

import type { ReasonOut } from "./types";

export type RankerScenario = "big_rain" | "dry_spell";

/* State (a) big-rain day is the launch/screenshot default; flip to
   "dry_spell" for state (b) honesty. */
export const RANKER_SCENARIO: RankerScenario = "big_rain";

/* Row-level condition colorway — mirrors the token condition states.
   "unknown" is where stale readings land (docs/04 §4: stale tends to
   unknown, never to false). */
export type FlowState = "live" | "fading" | "unknown";

export interface WaterfallRow {
  id: string; // stable slug — rows have no affordance_id yet (API gap)
  name: string;
  creek: string;
  /* Minutes from Portland — measured, wears .data. Invented pending the
     drive-time API (UI-DRAFT-BRIEF decision 5, same gap the feed has). */
  drive_min: number;
  /* Same shape as FeedCard.reasons[0] so the future endpoint is a
     drop-in; provenance[0] carries the number the row renders. */
  reason: ReasonOut;
  /* Compact driver text for reasons with no instrumented reading
     (provenance []) — e.g. "spring-fed". */
  driver_note: string | null;
  /* docs/04 §4 rule 2: degraded feeds render "live flow unavailable",
     never "conditions bad". */
  live_unavailable: string[];
  flow_state: FlowState;
  /* Claim word ("flowing hard", "fading") — UI font, never .data. */
  flow_label: string;
  last_verified_at: string | null;
  verified_by: string | null;
  /* Permit note where real only — canon: Multnomah timed-use permit. */
  permit: string | null;
}

export interface WaterfallsRankerFixture {
  generated_at: string;
  /* The honest count — rows the rank actually stands behind today. */
  worth_count: number;
  rows: WaterfallRow[];
}

/* Reason builders keep the fixtures readable; every field matches what
   the evaluator would serialize. */

function precipReason(
  station: string,
  inches: number,
  text: string,
  observedAt: string,
  fresh = true,
): ReasonOut {
  return {
    window_id: null,
    wtype: "weather_triggered",
    text,
    source: `nws ${station}`,
    fresh,
    as_of: observedAt,
    evaluated_at: GENERATED_AT,
    provenance: [
      {
        feed_id: `nws:${station}:precip_72h`,
        provider: "nws",
        station_ref: station,
        parameter: "precip_72h",
        unit: "in",
        value: inches,
        observed_at: observedAt,
      },
    ],
  };
}

function gaugeReason(
  stationRef: string,
  cfs: number,
  text: string,
  observedAt: string,
): ReasonOut {
  return {
    window_id: null,
    wtype: "hydrological",
    text,
    source: `usgs_nwis ${stationRef}`,
    fresh: true,
    as_of: observedAt,
    evaluated_at: GENERATED_AT,
    provenance: [
      {
        feed_id: `usgs_nwis:${stationRef}:discharge`,
        provider: "usgs_nwis",
        station_ref: stationRef,
        parameter: "discharge",
        unit: "cfs",
        value: cfs,
        observed_at: observedAt,
      },
    ],
  };
}

/* Spring-fed baseline: no instrumented reading — provenance stays empty
   (the canon Dog Mountain seasonal reason does the same). */
function springReason(text: string): ReasonOut {
  return {
    window_id: null,
    wtype: "spring_baseline",
    text,
    source: "seasonal prior",
    fresh: true,
    as_of: GENERATED_AT,
    evaluated_at: GENERATED_AT,
    provenance: [],
  };
}

/* All dates hang off the canon reference Sunday 2026-07-05 (mock.ts
   rule); 14:05 UTC = 7:05 am PDT — "updated this morning". */
const GENERATED_AT = "2026-07-05T14:05:00Z";
const OBSERVED_AM = "2026-07-05T13:45:00Z";

/* Canon permit note — Multnomah Falls timed-use permit (constraint
   block). The real permit window is seasonal (late May–early Sep);
   rendering it year-round is an open product question. */
const MULTNOMAH_PERMIT = "timed-use permit";

/* ---- State (a): big-rain day — everything firing ---- */

const bigRainRows: WaterfallRow[] = [
  {
    id: "multnomah-falls",
    name: "Multnomah Falls",
    creek: "Multnomah Creek",
    drive_min: 34,
    reason: precipReason(
      "TTD",
      2.1,
      "Flowing hard — 2.1 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "flowing hard",
    last_verified_at: "2026-07-05T15:10:00Z",
    verified_by: "gorge_amy",
    permit: MULTNOMAH_PERMIT,
  },
  {
    id: "elowah-falls",
    name: "Elowah Falls",
    creek: "McCord Creek",
    drive_min: 34,
    reason: precipReason(
      "TTD",
      1.4,
      "Flowing hard — 1.4 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "flowing hard",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "latourell-falls",
    name: "Latourell Falls",
    creek: "Latourell Creek",
    drive_min: 30,
    reason: precipReason(
      "TTD",
      1.2,
      "Strong — 1.2 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "strong",
    last_verified_at: "2026-07-04T21:30:00Z",
    verified_by: "mossy_boots",
    permit: null,
  },
  {
    id: "wahclella-falls",
    name: "Wahclella Falls",
    creek: "Tanner Creek",
    drive_min: 38,
    reason: precipReason(
      "TTD",
      1.1,
      "Strong — 1.1 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "strong",
    last_verified_at: null,
    verified_by: null,
    permit: "NW Forest Pass",
  },
  {
    id: "punch-bowl-falls",
    name: "Punch Bowl Falls",
    creek: "Eagle Creek",
    drive_min: 41,
    reason: gaugeReason(
      "14142800",
      412,
      "Running full — Eagle Ck at 412 cfs",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "running full",
    last_verified_at: null,
    verified_by: null,
    permit: "NW Forest Pass",
  },
  {
    id: "wahkeena-falls",
    name: "Wahkeena Falls",
    creek: "Wahkeena Creek",
    drive_min: 33,
    reason: precipReason(
      "TTD",
      0.9,
      "Steady — 0.9 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "steady",
    last_verified_at: "2026-07-03T19:15:00Z",
    verified_by: "gorge_amy",
    permit: null,
  },
  {
    id: "fairy-falls",
    name: "Fairy Falls",
    creek: "Wahkeena Creek",
    drive_min: 32,
    reason: precipReason(
      "TTD",
      0.9,
      "Steady — 0.9 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "steady",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "horsetail-falls",
    name: "Horsetail Falls",
    creek: "Horsetail Creek",
    drive_min: 35,
    reason: precipReason(
      "TTD",
      0.8,
      "Steady — 0.8 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "steady",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "bridal-veil-falls",
    name: "Bridal Veil Falls",
    creek: "Bridal Veil Creek",
    drive_min: 31,
    reason: precipReason(
      "TTD",
      0.7,
      "Moderate — 0.7 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "moderate",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "starvation-creek-falls",
    name: "Starvation Creek Falls",
    creek: "Starvation Creek",
    drive_min: 47,
    reason: precipReason(
      "CZK1",
      0.6,
      "Moderate — 0.6 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "live",
    flow_label: "moderate",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
];

/* ---- State (b): dry-spell honesty — fading ambers, honest count.
   Spring-fed Wahkeena Creek keeps two rows worth the drive; Multnomah's
   reading is the canon stale card from mock.ts, verbatim, and ranks
   last: stale tends to unknown, never to false. ---- */

const dryRows: WaterfallRow[] = [
  {
    id: "wahkeena-falls",
    name: "Wahkeena Falls",
    creek: "Wahkeena Creek",
    drive_min: 33,
    reason: springReason("Steady — spring-fed, flows year-round"),
    driver_note: "spring-fed",
    live_unavailable: [],
    flow_state: "live",
    flow_label: "steady",
    last_verified_at: "2026-07-04T18:20:00Z",
    verified_by: "gorge_amy",
    permit: null,
  },
  {
    id: "fairy-falls",
    name: "Fairy Falls",
    creek: "Wahkeena Creek",
    drive_min: 32,
    reason: springReason("Steady — spring-fed, flows year-round"),
    driver_note: "spring-fed",
    live_unavailable: [],
    flow_state: "live",
    flow_label: "steady",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "punch-bowl-falls",
    name: "Punch Bowl Falls",
    creek: "Eagle Creek",
    drive_min: 41,
    reason: gaugeReason(
      "14142800",
      128,
      "Fading — Eagle Ck down to 128 cfs",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "fading",
    last_verified_at: null,
    verified_by: null,
    permit: "NW Forest Pass",
  },
  {
    id: "elowah-falls",
    name: "Elowah Falls",
    creek: "McCord Creek",
    drive_min: 34,
    reason: precipReason(
      "TTD",
      0.2,
      "Fading — 0.2 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "fading",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "wahclella-falls",
    name: "Wahclella Falls",
    creek: "Tanner Creek",
    drive_min: 38,
    reason: precipReason(
      "TTD",
      0.2,
      "Fading — 0.2 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "fading",
    last_verified_at: "2026-06-29T20:00:00Z",
    verified_by: "mossy_boots",
    permit: "NW Forest Pass",
  },
  {
    id: "latourell-falls",
    name: "Latourell Falls",
    creek: "Latourell Creek",
    drive_min: 30,
    reason: precipReason(
      "TTD",
      0.1,
      "Low — 0.1 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "low",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "horsetail-falls",
    name: "Horsetail Falls",
    creek: "Horsetail Creek",
    drive_min: 35,
    reason: precipReason(
      "TTD",
      0.1,
      "Low — 0.1 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "low",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "bridal-veil-falls",
    name: "Bridal Veil Falls",
    creek: "Bridal Veil Creek",
    drive_min: 31,
    reason: precipReason(
      "TTD",
      0.1,
      "Low — 0.1 in rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "low",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "starvation-creek-falls",
    name: "Starvation Creek Falls",
    creek: "Starvation Creek",
    drive_min: 47,
    reason: precipReason(
      "CZK1",
      0,
      "Low — no rain in the last 72 h",
      OBSERVED_AM,
    ),
    driver_note: null,
    live_unavailable: [],
    flow_state: "fading",
    flow_label: "low",
    last_verified_at: null,
    verified_by: null,
    permit: null,
  },
  {
    id: "multnomah-falls",
    name: "Multnomah Falls",
    creek: "Multnomah Creek",
    drive_min: 34,
    /* Canon verbatim — mock.ts Multnomah feed card: stale PDX reading,
       discharge feed down. fresh:false renders ○ + "as of Fri 4pm". */
    reason: {
      window_id: "33333333-0000-4000-8000-000000000005",
      wtype: "weather_triggered",
      text: "Rain-fed flow — 0.8 in rain in the last 72 h (as of Fri 4pm)",
      source: "nws PDX",
      fresh: false,
      as_of: "2026-07-03T23:00:00Z",
      evaluated_at: "2026-07-05T13:00:00Z",
      provenance: [
        {
          feed_id: "nws:PDX:precip_72h",
          provider: "nws",
          station_ref: "PDX",
          parameter: "precip_72h",
          unit: "in",
          value: 0.8,
          observed_at: "2026-07-03T23:00:00Z",
        },
      ],
    },
    driver_note: null,
    live_unavailable: ["flow"],
    flow_state: "unknown",
    flow_label: "flow unknown",
    last_verified_at: "2026-06-20T18:00:00Z",
    verified_by: null,
    permit: MULTNOMAH_PERMIT,
  },
];

export const waterfallsRanker: Record<RankerScenario, WaterfallsRankerFixture> = {
  big_rain: {
    generated_at: GENERATED_AT,
    worth_count: 10,
    rows: bigRainRows,
  },
  dry_spell: {
    generated_at: GENERATED_AT,
    worth_count: 2,
    rows: dryRows,
  },
};
