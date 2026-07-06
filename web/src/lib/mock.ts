/* Canon fixtures for NEXT_PUBLIC_MOCK=1 — mock data is canon data
   (design/README.md rule 5), so every mock render doubles as a product
   review. All dates are hardcoded relative to the fixed reference date
   2026-07-05 (a Sunday). */

import {
  ASSUMPTION_OF_RISK,
  type ClaimOut,
  type FeedResponse,
  type PlacePage,
  type PlaceSearchResult,
  type SavedItem,
  type TripOut,
  type UserOut,
  type VerdictOut,
} from "./types";

// Fixed ids: 11… places · 22… affordances · 33… windows · 44… claims ·
// 55… users · 66… verifications · 77… trips.
const PLACE_TAMANAWAS = "11111111-0000-4000-8000-000000000001";
const PLACE_HIGH_ROCKS = "11111111-0000-4000-8000-000000000002";
const PLACE_DOG_MOUNTAIN = "11111111-0000-4000-8000-000000000003";
const PLACE_SPRINGVILLE = "11111111-0000-4000-8000-000000000004";
const PLACE_MULTNOMAH = "11111111-0000-4000-8000-000000000005";
const PLACE_PITTOCK = "11111111-0000-4000-8000-000000000006";
const PLACE_WILDWOOD = "11111111-0000-4000-8000-000000000007";

const AFF_TAMANAWAS_HIKE = "22222222-0000-4000-8000-000000000001";
const AFF_HIGH_ROCKS_SWIM = "22222222-0000-4000-8000-000000000002";
const AFF_DOG_MOUNTAIN_HIKE = "22222222-0000-4000-8000-000000000003";
const AFF_SPRINGVILLE_WALK = "22222222-0000-4000-8000-000000000004";
const AFF_MULTNOMAH_HIKE = "22222222-0000-4000-8000-000000000005";
const AFF_PITTOCK_WALK = "22222222-0000-4000-8000-000000000006";
const AFF_WILDWOOD_RUN = "22222222-0000-4000-8000-000000000007";
const AFF_HIGH_ROCKS_WALK = "22222222-0000-4000-8000-000000000008";

const WIN_TAMANAWAS_RAIN = "33333333-0000-4000-8000-000000000001";
const WIN_HIGH_ROCKS_FLOW = "33333333-0000-4000-8000-000000000002";
const WIN_HIGH_ROCKS_SEASON = "33333333-0000-4000-8000-000000000003";
const WIN_DOG_BLOOM = "33333333-0000-4000-8000-000000000004";
const WIN_MULTNOMAH_RAIN = "33333333-0000-4000-8000-000000000005";

const CLAIM_TAMANAWAS_FLOW = "44444444-0000-4000-8000-000000000001";
const CLAIM_HR_JUMP_DEPTH = "44444444-0000-4000-8000-000000000002";
const CLAIM_HR_ACCESS = "44444444-0000-4000-8000-000000000003";
const CLAIM_HR_ROPE_SWING = "44444444-0000-4000-8000-000000000004";
const CLAIM_HR_WALK_PATH = "44444444-0000-4000-8000-000000000005";
const CLAIM_DOG_BALSAMROOT = "44444444-0000-4000-8000-000000000006";
const CLAIM_SPRINGVILLE_GATE = "44444444-0000-4000-8000-000000000007";
const CLAIM_SPRINGVILLE_SHADE = "44444444-0000-4000-8000-000000000008";
const CLAIM_MULTNOMAH_PERMIT = "44444444-0000-4000-8000-000000000009";
const CLAIM_PITTOCK_PARKING = "44444444-0000-4000-8000-000000000010";
const CLAIM_WILDWOOD_MUD = "44444444-0000-4000-8000-000000000011";

export const mockUser: UserOut = {
  id: "55555555-0000-4000-8000-000000000001",
  email: "amy@example.com",
  display_name: "gorge_amy",
  power_verifier: true,
  is_founder: false,
};

export const mockFeed: FeedResponse = {
  generated_at: "2026-07-05T13:05:00Z",
  count: 7,
  cards: [
    // 1 · condition-magic: fresh weather-triggered reason (⚡)
    {
      affordance_id: AFF_TAMANAWAS_HIKE,
      place_id: PLACE_TAMANAWAS,
      place_name: "Tamanawas Falls",
      place_kind: "waterfall",
      lat: 45.399,
      lng: -121.573,
      distance_km: 59.0,
      activity_id: "waterfall_hike",
      activity_name: "Waterfall hike",
      hazard_class: false,
      difficulty: 2,
      typical_duration_min: 150,
      dog_ok: true,
      kid_ok: true,
      now_score: 0.94,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [
        {
          window_id: WIN_TAMANAWAS_RAIN,
          wtype: "weather_triggered",
          text: "Flowing hard right now — 1.6 in rain in the last 72 h",
          source: "nws MTHOOD",
          fresh: true,
          as_of: "2026-07-05T12:45:00Z",
          evaluated_at: "2026-07-05T13:00:00Z",
          provenance: [
            {
              feed_id: "nws:MTHOOD:precip_72h",
              provider: "nws",
              station_ref: "MTHOOD",
              parameter: "precip_72h",
              unit: "in",
              value: 1.6,
              observed_at: "2026-07-05T12:45:00Z",
            },
          ],
        },
      ],
      live_unavailable: [],
      conditions: { precip_72h_in: 1.6 },
      last_verified_at: "2026-07-05T15:10:00Z",
      verified_by: "gorge_amy",
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_TAMANAWAS_FLOW, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 2 · hazard-gated: hydrological reason, gauge 14210000 at 980 cfs
    {
      affordance_id: AFF_HIGH_ROCKS_SWIM,
      place_id: PLACE_HIGH_ROCKS,
      place_name: "High Rocks",
      place_kind: "swimming_hole",
      lat: 45.3846,
      lng: -122.607,
      distance_km: 19.5,
      activity_id: "wild_swim",
      activity_name: "Wild swim",
      hazard_class: true,
      difficulty: 3,
      typical_duration_min: 120,
      dog_ok: false,
      kid_ok: false,
      now_score: 0.91,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [
        {
          window_id: WIN_HIGH_ROCKS_FLOW,
          wtype: "hydrological",
          text: "Swimmable now — Clackamas @ Estacada (14210000) at 980 cfs, threshold <1,200",
          source: "usgs_nwis 14210000",
          fresh: true,
          as_of: "2026-07-05T12:30:00Z",
          evaluated_at: "2026-07-05T13:00:00Z",
          provenance: [
            {
              feed_id: "usgs_nwis:14210000:discharge",
              provider: "usgs_nwis",
              station_ref: "14210000",
              parameter: "discharge",
              unit: "cfs",
              value: 980,
              observed_at: "2026-07-05T12:30:00Z",
            },
          ],
        },
      ],
      live_unavailable: [],
      conditions: { discharge_cfs: 980 },
      last_verified_at: "2026-06-27T22:40:00Z",
      verified_by: "gorge_amy",
      assumption_of_risk: ASSUMPTION_OF_RISK,
      verdict_controls: [
        { claim_id: CLAIM_HR_JUMP_DEPTH, allowed_verdicts: ["confirm", "refute", "changed"] },
        { claim_id: CLAIM_HR_ROPE_SWING, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 3 · seasonal_bio: Dog Mountain balsamroot
    {
      affordance_id: AFF_DOG_MOUNTAIN_HIKE,
      place_id: PLACE_DOG_MOUNTAIN,
      place_name: "Dog Mountain",
      place_kind: "peak",
      lat: 45.6994,
      lng: -121.708,
      distance_km: 84.0,
      activity_id: "wildflower_hike",
      activity_name: "Wildflower hike",
      hazard_class: false,
      difficulty: 4,
      typical_duration_min: 240,
      dog_ok: true,
      kid_ok: false,
      now_score: 0.83,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [
        {
          window_id: WIN_DOG_BLOOM,
          wtype: "seasonal_bio",
          text: "Balsamroot meadows in peak color — bloom window open",
          source: "seasonal prior",
          fresh: true,
          as_of: "2026-07-05T13:00:00Z",
          evaluated_at: "2026-07-05T13:00:00Z",
          provenance: [],
        },
      ],
      live_unavailable: [],
      conditions: {},
      last_verified_at: null,
      verified_by: null,
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_DOG_BALSAMROOT, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 4 · everyday: no live reason, nothing degraded — claims-backed
    {
      affordance_id: AFF_SPRINGVILLE_WALK,
      place_id: PLACE_SPRINGVILLE,
      place_name: "Springville Trailhead",
      place_kind: "trailhead",
      lat: 45.5764,
      lng: -122.7963,
      distance_km: 20.2,
      activity_id: "walk",
      activity_name: "Forest walk",
      hazard_class: false,
      difficulty: 1,
      typical_duration_min: 90,
      dog_ok: true,
      kid_ok: true,
      now_score: 0.62,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [],
      live_unavailable: [],
      conditions: {},
      last_verified_at: "2026-05-14T17:00:00Z",
      verified_by: null,
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_SPRINGVILLE_GATE, allowed_verdicts: ["confirm", "refute", "changed"] },
        { claim_id: CLAIM_SPRINGVILLE_SHADE, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 5 · degraded: gauge feed down + a stale (fresh:false) weather reading
    {
      affordance_id: AFF_MULTNOMAH_HIKE,
      place_id: PLACE_MULTNOMAH,
      place_name: "Multnomah Falls",
      place_kind: "waterfall",
      lat: 45.5762,
      lng: -122.1158,
      distance_km: 43.4,
      activity_id: "waterfall_hike",
      activity_name: "Waterfall hike",
      hazard_class: false,
      difficulty: 1,
      typical_duration_min: 60,
      dog_ok: true,
      kid_ok: true,
      now_score: 0.58,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [
        {
          window_id: WIN_MULTNOMAH_RAIN,
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
      ],
      live_unavailable: ["usgs_nwis discharge (hydrological)"],
      conditions: { precip_72h_in: 0.8 },
      last_verified_at: "2026-06-20T18:00:00Z",
      verified_by: null,
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_MULTNOMAH_PERMIT, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 6 · everyday
    {
      affordance_id: AFF_PITTOCK_WALK,
      place_id: PLACE_PITTOCK,
      place_name: "Pittock Mansion Trailhead",
      place_kind: "trailhead",
      lat: 45.5251,
      lng: -122.7162,
      distance_km: 8.6,
      activity_id: "walk",
      activity_name: "Forest walk",
      hazard_class: false,
      difficulty: 2,
      typical_duration_min: 120,
      dog_ok: true,
      kid_ok: true,
      now_score: 0.57,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [],
      live_unavailable: [],
      conditions: {},
      last_verified_at: "2026-06-14T16:30:00Z",
      verified_by: null,
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_PITTOCK_PARKING, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
    // 7 · everyday
    {
      affordance_id: AFF_WILDWOOD_RUN,
      place_id: PLACE_WILDWOOD,
      place_name: "Wildwood Trailhead",
      place_kind: "trailhead",
      lat: 45.535,
      lng: -122.73,
      distance_km: 13.0,
      activity_id: "trail_run",
      activity_name: "Trail run",
      hazard_class: false,
      difficulty: 2,
      typical_duration_min: 60,
      dog_ok: true,
      kid_ok: true,
      now_score: 0.55,
      computed_at: "2026-07-05T13:00:00Z",
      reasons: [],
      live_unavailable: [],
      conditions: {},
      last_verified_at: "2026-07-01T15:00:00Z",
      verified_by: null,
      assumption_of_risk: null,
      verdict_controls: [
        { claim_id: CLAIM_WILDWOOD_MUD, allowed_verdicts: ["confirm", "refute", "changed"] },
      ],
    },
  ],
};

export const mockClaimsHighRocksSwim: ClaimOut[] = [
  {
    id: CLAIM_HR_JUMP_DEPTH,
    affordance_id: AFF_HIGH_ROCKS_SWIM,
    cclass: "hazard_calibration",
    source_type: "user_reported",
    source_domain: null,
    source_url: null,
    observed_date: "2026-06-27",
    confidence: 0.91,
    last_evidence_at: "2026-06-27T22:40:00Z",
    allowed_verdicts: ["confirm", "refute", "changed"],
  },
  {
    id: CLAIM_HR_ACCESS,
    affordance_id: AFF_HIGH_ROCKS_SWIM,
    cclass: "access",
    source_type: "extracted",
    source_domain: "oregonhikers.org",
    source_url: "https://www.oregonhikers.org/field_guide/High_Rocks",
    observed_date: "2026-06-14",
    confidence: 0.87,
    last_evidence_at: "2026-06-14T00:00:00Z",
    allowed_verdicts: ["confirm", "refute", "changed"],
  },
  {
    id: CLAIM_HR_ROPE_SWING,
    affordance_id: AFF_HIGH_ROCKS_SWIM,
    cclass: "geomorphic",
    source_type: "user_reported",
    source_domain: null,
    source_url: null,
    observed_date: "2026-05-20",
    confidence: 0.9,
    last_evidence_at: "2026-06-27T22:40:00Z",
    allowed_verdicts: ["confirm", "refute", "changed"],
  },
];

export const mockPlaceHighRocks: PlacePage = {
  id: PLACE_HIGH_ROCKS,
  name: "High Rocks",
  kind: "swimming_hole",
  lat: 45.3846,
  lng: -122.607,
  elev_m: 20,
  affordances: [
    {
      affordance_id: AFF_HIGH_ROCKS_SWIM,
      activity_id: "wild_swim",
      activity_name: "Wild swim",
      hazard_class: true,
      difficulty: 3,
      typical_duration_min: 120,
      dog_ok: false,
      kid_ok: false,
      windows: [
        {
          window_id: WIN_HIGH_ROCKS_FLOW,
          wtype: "hydrological",
          is_gate: true,
          multiplier: 1.0,
          state: "true",
          state_since: "2026-06-19T20:00:00Z",
          last_eval: "2026-07-05T13:00:00Z",
          live: {
            window_id: WIN_HIGH_ROCKS_FLOW,
            wtype: "hydrological",
            text: "Swimmable now — Clackamas @ Estacada (14210000) at 980 cfs, threshold <1,200",
            source: "usgs_nwis 14210000",
            fresh: true,
            as_of: "2026-07-05T12:30:00Z",
            evaluated_at: "2026-07-05T13:00:00Z",
            provenance: [
              {
                feed_id: "usgs_nwis:14210000:discharge",
                provider: "usgs_nwis",
                station_ref: "14210000",
                parameter: "discharge",
                unit: "cfs",
                value: 980,
                observed_at: "2026-07-05T12:30:00Z",
              },
            ],
          },
        },
      ],
      claims: mockClaimsHighRocksSwim,
      last_verified_at: "2026-06-27T22:40:00Z",
      verified_by: "gorge_amy",
      assumption_of_risk: ASSUMPTION_OF_RISK,
    },
    {
      affordance_id: AFF_HIGH_ROCKS_WALK,
      activity_id: "walk",
      activity_name: "Riverside walk",
      hazard_class: false,
      difficulty: 1,
      typical_duration_min: 45,
      dog_ok: true,
      kid_ok: true,
      windows: [
        {
          window_id: WIN_HIGH_ROCKS_SEASON,
          wtype: "seasonal",
          is_gate: false,
          multiplier: 1.15,
          state: "true",
          state_since: "2026-05-01T07:00:00Z",
          last_eval: "2026-07-05T13:00:00Z",
          live: null,
        },
      ],
      claims: [
        {
          id: CLAIM_HR_WALK_PATH,
          affordance_id: AFF_HIGH_ROCKS_WALK,
          cclass: "access",
          source_type: "extracted",
          source_domain: "oregonhikers.org",
          source_url: "https://www.oregonhikers.org/field_guide/High_Rocks",
          observed_date: "2026-04-02",
          confidence: 0.78,
          last_evidence_at: "2026-04-02T00:00:00Z",
          allowed_verdicts: ["confirm", "refute", "changed"],
        },
      ],
      last_verified_at: "2026-05-14T17:00:00Z",
      verified_by: null,
      assumption_of_risk: null,
    },
  ],
};

export const mockSearchResults: PlaceSearchResult[] = [
  {
    id: PLACE_HIGH_ROCKS,
    name: "High Rocks",
    kind: "swimming_hole",
    lat: 45.3846,
    lng: -122.607,
    distance_km: 19.5,
    activities: ["walk", "wild_swim"],
  },
  {
    id: PLACE_SPRINGVILLE,
    name: "Springville Trailhead",
    kind: "trailhead",
    lat: 45.5764,
    lng: -122.7963,
    distance_km: 20.2,
    activities: ["walk"],
  },
  {
    id: PLACE_TAMANAWAS,
    name: "Tamanawas Falls",
    kind: "waterfall",
    lat: 45.399,
    lng: -121.573,
    distance_km: 59.0,
    activities: ["waterfall_hike"],
  },
];

export const mockSaves: SavedItem[] = [
  {
    affordance_id: AFF_DOG_MOUNTAIN_HIKE,
    kind: "want_to",
    place_id: PLACE_DOG_MOUNTAIN,
    place_name: "Dog Mountain",
    activity_id: "wildflower_hike",
    created_at: "2026-01-18T19:30:00Z",
    last_alerted_at: "2026-05-12T15:00:00Z",
  },
  {
    affordance_id: AFF_TAMANAWAS_HIKE,
    kind: "been",
    place_id: PLACE_TAMANAWAS,
    place_name: "Tamanawas Falls",
    activity_id: "waterfall_hike",
    created_at: "2026-06-07T20:15:00Z",
    last_alerted_at: null,
  },
  {
    affordance_id: AFF_HIGH_ROCKS_SWIM,
    kind: "loved",
    place_id: PLACE_HIGH_ROCKS,
    place_name: "High Rocks",
    activity_id: "wild_swim",
    created_at: "2026-06-28T02:10:00Z",
    last_alerted_at: null,
  },
];

// "Thanks — logged with conditions at 990 cfs, 82°F" (UI-DRAFT-BRIEF §3)
export const mockVerdict: VerdictOut = {
  verification_id: "66666666-0000-4000-8000-000000000001",
  claim_id: CLAIM_HR_JUMP_DEPTH,
  verdict: "confirm",
  log_odds: 3.1,
  confidence: 0.95,
  conditions_snapshot: { discharge_cfs: 990, temp_f: 82 },
  superseding_claim_id: null,
};

export const mockTrip: TripOut = {
  id: "77777777-0000-4000-8000-000000000001",
  affordance_id: AFF_HIGH_ROCKS_SWIM,
  planned_date: "2026-07-11",
  declared_at: "2026-07-05T13:10:00Z",
};

export const mockVapidPublicKey =
  "BPlaceMockVapidKey-0000000000000000000000000000000000000000000000000000000000000000000000";
