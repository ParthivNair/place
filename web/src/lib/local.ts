/* Client-side records — the browser is the only record of some of its own
   state (no GET /trips, no server-side onboarding flags, and magic-link
   verify opens in a fresh tab that can't see React refs). Every key is
   route-prefixed "place.*"; every reader tolerates missing/garbled storage
   (private mode, quota) by degrading to the server truth. */

import type { SaveKind, TripOut } from "./types";

// ---------------------------------------------------------------------------
// trips — written by the GoingSheet, read back by the Sunday sheet
// ---------------------------------------------------------------------------

export const TRIPS_KEY = "place.trips";

/* TripOut plus the naming context the API doesn't echo back: /sunday must
   render "You went to {place}" from this record alone — nothing maps an
   affordance_id to its place client-side (flagged API gap; the mock
   getPlace serves High Rocks for any id, which hid this). Optional so
   records written before these fields existed still parse. */
export interface TripRecord extends TripOut {
  place_id?: string;
  place_name?: string;
  activity_name?: string;
}

export function rememberTrip(trip: TripRecord): void {
  try {
    window.localStorage.setItem(
      TRIPS_KEY,
      JSON.stringify([...readTripRecords(), trip]),
    );
  } catch {
    // storage unavailable: the trip exists server-side; only the local
    // Sunday deep-link forgets it
  }
}

export function readTripRecords(): TripRecord[] {
  try {
    const raw = window.localStorage.getItem(TRIPS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return (parsed as TripRecord[]).filter(
      (t) =>
        t !== null &&
        typeof t === "object" &&
        typeof t.id === "string" &&
        typeof t.affordance_id === "string" &&
        typeof t.planned_date === "string",
    );
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// pending auth intent — the save/going that hit a 401
// ---------------------------------------------------------------------------

/* Decision 11: auth intercepts the first save/going/verdict and the intent
   resumes after verify. The magic link opens from an email, usually in a
   fresh tab, so the interrupted intent must survive in storage — an
   in-memory ref never reaches /auth/verify. One slot, last-writer-wins:
   auth is triggered by exactly one intercepted action at a time. */

const PENDING_INTENT_KEY = "place.pending-intent";

export type PendingIntent =
  | { type: "save"; affordance_id: string; kind: SaveKind; place_name: string }
  | {
      type: "trip";
      affordance_id: string;
      planned_date: string;
      place_id?: string;
      place_name: string;
      activity_name?: string;
    };

export function writePendingIntent(intent: PendingIntent): void {
  try {
    window.localStorage.setItem(PENDING_INTENT_KEY, JSON.stringify(intent));
  } catch {
    // storage unavailable: verify still signs in; the user re-taps once
  }
}

export function takePendingIntent(): PendingIntent | null {
  try {
    const raw = window.localStorage.getItem(PENDING_INTENT_KEY);
    window.localStorage.removeItem(PENDING_INTENT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const p = parsed as PendingIntent;
    if (p.type === "save" && typeof p.affordance_id === "string") return p;
    if (
      p.type === "trip" &&
      typeof p.affordance_id === "string" &&
      typeof p.planned_date === "string"
    )
      return p;
    return null;
  } catch {
    return null;
  }
}

export function clearPendingIntent(): void {
  try {
    window.localStorage.removeItem(PENDING_INTENT_KEY);
  } catch {
    // nothing to clear
  }
}

// ---------------------------------------------------------------------------
// waterfall hearts — /waterfalls' ♥s, device-local until the API can hold them
// ---------------------------------------------------------------------------

/* The public ranker has no session and its rows carry no affordance_id
   (flagged API gap in lib/waterfallsRanker), so no POST /saves can hold a
   heart yet. This key keeps state (c)'s "watching this for you" rows
   honest across reloads on this device — the standing query the copy
   promises still needs the ranker endpoint to become real server-side. */

const WATERFALL_HEARTS_KEY = "place.waterfalls.hearts";

export function readWatchedFalls(): string[] {
  try {
    const raw = window.localStorage.getItem(WATERFALL_HEARTS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is string => typeof id === "string");
  } catch {
    return [];
  }
}

export function writeWatchedFalls(ids: string[]): void {
  try {
    window.localStorage.setItem(WATERFALL_HEARTS_KEY, JSON.stringify(ids));
  } catch {
    // storage unavailable — hearts last this session only
  }
}

// ---------------------------------------------------------------------------
// returning user — device-side memory only
// ---------------------------------------------------------------------------

/* POST /auth/magic-link always answers 202 and never says whether the email
   is known (by design — no account enumeration; flagged as the reason the
   "recognized email" state can only be device-local). A completed verify on
   this device is the only recognition signal the client has. */

const KNOWN_EMAIL_KEY = "place.auth.known-email";

export function rememberKnownEmail(email: string): void {
  try {
    window.localStorage.setItem(KNOWN_EMAIL_KEY, email);
  } catch {
    // storage unavailable — the softer returning-user copy just won't show
  }
}

export function readKnownEmail(): string | null {
  try {
    return window.localStorage.getItem(KNOWN_EMAIL_KEY);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// onboarding flags — /welcome writes, the feed reads
// ---------------------------------------------------------------------------

export const NEIGHBORHOOD_KEY = "place.welcome.neighborhood";
export const WELCOME_DONE_KEY = "place.welcome.done";
/* Set when the feed's one-time /welcome banner is dismissed without doing
   onboarding — dismissal is a decision too; never nag (docs/07). */
export const WELCOME_SEEN_KEY = "place.welcome.seen";

export function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage unavailable — callers treat flags as best-effort
  }
}
