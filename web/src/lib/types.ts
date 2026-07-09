/* Mirrors of backend/place/api/schemas.py — the only source of truth.
   UUIDs, datetimes, and dates serialize as strings; field names stay
   snake_case exactly as the API serializes them. */

export type VerdictLiteral = "confirm" | "refute" | "changed";

export const ALLOWED_VERDICTS: VerdictLiteral[] = ["confirm", "refute", "changed"];

// Verbatim schemas.py ASSUMPTION_OF_RISK: the server string is the single
// legal source; this copy exists so mock fixtures match it byte-for-byte.
export const ASSUMPTION_OF_RISK =
  "Conditions change; you are responsible for your own judgment. " +
  "Verify current conditions on arrival.";

// ---------------------------------------------------------------------------
// shared claim / reason fragments
// ---------------------------------------------------------------------------

export interface VerdictControl {
  claim_id: string;
  allowed_verdicts: VerdictLiteral[];
}

export interface ProvenanceReading {
  feed_id: string;
  provider: string | null;
  station_ref: string | null;
  parameter: string | null;
  unit: string | null;
  value: number | string | boolean | null;
  observed_at: string | null;
}

export interface ReasonOut {
  window_id: string | null;
  wtype: string;
  text: string;
  source: string | null;
  fresh: boolean;
  as_of: string | null;
  evaluated_at: string | null;
  provenance: ProvenanceReading[];
}

export interface ClaimOut {
  id: string;
  affordance_id: string;
  cclass: string;
  source_type: string;
  source_domain: string | null;
  source_url: string | null;
  observed_date: string | null;
  confidence: number;
  last_evidence_at: string;
  allowed_verdicts: VerdictLiteral[];
}

export interface WindowOut {
  window_id: string;
  wtype: string;
  is_gate: boolean;
  multiplier: number;
  state: "true" | "false" | "unknown";
  state_since: string | null;
  last_eval: string | null;
  live: ReasonOut | null;
}

// ---------------------------------------------------------------------------
// feed
// ---------------------------------------------------------------------------

export interface FeedCard {
  affordance_id: string;
  place_id: string;
  place_name: string;
  place_kind: string;
  lat: number;
  lng: number;
  distance_km: number;
  activity_id: string;
  activity_name: string;
  hazard_class: boolean;
  difficulty: number | null;
  typical_duration_min: number | null;
  dog_ok: boolean | null;
  kid_ok: boolean | null;
  now_score: number;
  computed_at: string;
  reasons: ReasonOut[];
  // docs/04 §4 rule 2: labels of non-gate live windows currently unknown —
  // render "live … unavailable", never "conditions bad".
  live_unavailable: string[];
  conditions: Record<string, unknown>;
  last_verified_at: string | null;
  verified_by: string | null;
  assumption_of_risk: string | null;
  verdict_controls: VerdictControl[];
}

export interface FeedResponse {
  generated_at: string;
  count: number;
  cards: FeedCard[];
}

// ---------------------------------------------------------------------------
// places
// ---------------------------------------------------------------------------

export interface PlaceSearchResult {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lng: number;
  distance_km: number;
  activities: string[];
}

export interface AffordanceDetail {
  affordance_id: string;
  activity_id: string;
  activity_name: string;
  hazard_class: boolean;
  difficulty: number | null;
  typical_duration_min: number | null;
  dog_ok: boolean | null;
  kid_ok: boolean | null;
  windows: WindowOut[];
  claims: ClaimOut[];
  last_verified_at: string | null;
  verified_by: string | null;
  assumption_of_risk: string | null;
}

export interface PlacePage {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lng: number;
  elev_m: number | null;
  affordances: AffordanceDetail[];
  /* NOT SERVED YET — flagged API gaps (UI-DRAFT-BRIEF cheat sheet "design
     the slot, flag the gap"). permit_note carries the canon per-place
     permit copy (Northwest Forest Pass, Multnomah timed-use) into
     SafetyLine's permit slot. suppressed_hazards names hazard affordances
     the server pre-gated out (needs a recent verification AND a live
     trigger, docs/02 §5.1) so the page can acknowledge them honestly
     instead of rendering them invisible. Optional: the live payload
     serves neither yet. */
  permit_note?: string | null;
  suppressed_hazards?: { activity_name: string }[];
}

// ---------------------------------------------------------------------------
// saves / trips / verdicts
// ---------------------------------------------------------------------------

export type SaveKind = "want_to" | "been" | "loved";

export interface SaveIn {
  affordance_id: string;
  kind: SaveKind;
}

export interface SavedItem {
  affordance_id: string;
  kind: SaveKind;
  place_id: string;
  place_name: string;
  activity_id: string;
  created_at: string;
  last_alerted_at: string | null;
  /* NOT SERVED YET — flagged API gap (UI-DRAFT-BRIEF §6, decision 10).
     A want-to is a standing query and the row must show what the sensor
     watches ("Clackamas < 1,200 cfs") and the watched window's current
     state (⚡/●/○). Optional so the real /saves payload, which omits both,
     still typechecks; mock fixtures carry them so the founder can review
     the treatment. "firing" = weather-triggered live (⚡), "live" = other
     live (●), "unknown" = ○ — stale tends toward unknown, never false. */
  watching?: string | null;
  window_state?: "firing" | "live" | "unknown" | null;
}

export interface TripIn {
  affordance_id: string;
  planned_date: string;
}

export interface TripOut {
  id: string;
  affordance_id: string;
  planned_date: string;
  declared_at: string;
}

export interface VerdictIn {
  claim_id: string;
  verdict: VerdictLiteral;
  trip_id?: string | null;
}

export interface VerdictOut {
  verification_id: string;
  claim_id: string;
  verdict: VerdictLiteral;
  log_odds: number;
  confidence: number;
  conditions_snapshot: Record<string, unknown>;
  superseding_claim_id: string | null;
}

// ---------------------------------------------------------------------------
// auth / push / events
// ---------------------------------------------------------------------------

export interface MagicLinkIn {
  email: string;
}

export interface UserOut {
  id: string;
  email: string;
  display_name: string | null;
  power_verifier: boolean;
  is_founder: boolean;
}

export interface PushKeys {
  p256dh: string;
  auth: string;
}

export interface PushSubscriptionIn {
  endpoint: string;
  keys: PushKeys;
}

// Product verbs → feed_event_t enum values (schemas.py EVENT_ALIASES). The
// server validator maps on ingest; the mock client mirrors the mapping.
export const EVENT_ALIASES: Record<string, string> = {
  shown: "impression",
  saved: "save",
  went: "going",
  verified: "verified",
  impression: "impression",
  card_open: "card_open",
  save: "save",
  going: "going",
  rejected: "rejected",
};

export interface EventIn {
  affordance_id: string;
  etype: string;
  now_score?: number | null;
  conditions_snapshot?: Record<string, unknown> | null;
}

export interface EventOut {
  id: number;
  etype: string;
  affordance_id: string;
}

/* POST /events/impressions — the feed's impression beacon. GET /feed is a
   pure read, so the client reports what it rendered; computed_at is the
   card's sweep timestamp (FeedCard.computed_at) and the SERVER re-attaches
   the conditions snapshot as of it — the log stays server-attested
   (docs/02 §5 requirement 2), never client-supplied. Max 50 items (the
   feed's page-size cap). */
export interface ImpressionItem {
  affordance_id: string;
  now_score: number;
  computed_at: string;
}

export interface ImpressionsOut {
  stored: number;
}
