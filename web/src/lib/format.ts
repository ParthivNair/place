/* Display formatters for canon copy: "41 min drive", "as of Tue 4pm",
   "verified 6 days ago by @gorge_amy", "~2.5 h". Numbers these produce are
   measured values — render them inside a .data span. */

import type { VerdictLiteral } from "./types";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const pad2 = (n: number): string => String(n).padStart(2, "0");

// Client-side heuristic until the API serves drive time (UI-DRAFT-BRIEF
// decision 5 — flagged API gap): minutes ≈ distance_km / 1.44, rounded to
// the nearest 5, floor 5.
export function fmtDriveMinutes(distanceKm: number): string {
  const minutes = Math.max(5, Math.round(distanceKm / 1.44 / 5) * 5);
  return `${minutes} min drive`;
}

function fmtClockTime(d: Date): string {
  const hours = d.getHours() % 12 || 12;
  const minutes = d.getMinutes();
  const ampm = d.getHours() >= 12 ? "pm" : "am";
  return minutes === 0 ? `${hours}${ampm}` : `${hours}:${pad2(minutes)}${ampm}`;
}

// Freshness honesty (docs/04 §4 rule 1): stale readings render "as of Tue 4pm".
export function fmtAsOf(iso: string): string {
  const d = new Date(iso);
  return `as of ${WEEKDAYS[d.getDay()]} ${fmtClockTime(d)}`;
}

function calendarDaysAgo(iso: string, now: Date): number {
  const d = new Date(iso);
  const then = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((today - then) / 86_400_000);
}

// "verified 6 days ago by @gorge_amy" — named provenance credit is the only
// recognition in the product.
export function fmtVerified(lastVerifiedAt: string, verifiedBy?: string | null): string {
  const now = new Date();
  const days = calendarDaysAgo(lastVerifiedAt, now);
  let when: string;
  if (days <= 0) {
    when = "today";
  } else if (days === 1) {
    when = "yesterday";
  } else if (days < 14) {
    when = `${days} days ago`;
  } else {
    const d = new Date(lastVerifiedAt);
    when = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
    if (d.getFullYear() !== now.getFullYear()) when += `, ${d.getFullYear()}`;
  }
  const by = verifiedBy ? ` by @${verifiedBy.replace(/^@/, "")}` : "";
  return `verified ${when}${by}`;
}

// Claim observed_date renders month + year ("reported May 2026" idiom).
// Parsed by hand: new Date("2026-06-01") is UTC midnight, which shifts a
// month back in negative-offset timezones.
export function fmtObservedDate(isoDate: string): string {
  const [year, month] = isoDate.split("-").map(Number);
  return `${MONTHS[(month || 1) - 1]} ${year}`;
}

export function fmtDurationMin(minutes: number): string {
  if (minutes < 60) return `~${Math.round(minutes)} min`;
  const hours = Math.round((minutes / 60) * 2) / 2;
  return `~${Number.isInteger(hours) ? hours.toFixed(0) : hours.toFixed(1)} h`;
}

// planned_date default (UI-DRAFT-BRIEF decision 9). Returns a local
// calendar date (YYYY-MM-DD); if `from` is a Saturday, that same day.
export function nextSaturday(from: Date = new Date()): string {
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7));
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

// Glyph canon: ⚡ weather-triggered live · ● other live · ○ signal absent.
export function glyphFor(reason: { wtype: string; fresh: boolean }): string {
  if (reason.wtype === "weather_triggered" && reason.fresh) return "⚡";
  if (!reason.fresh) return "○";
  return "●";
}

export function windowGlyph(state: "true" | "false" | "unknown"): string {
  return state === "unknown" ? "○" : "●";
}

// UI copy says confirm / deny / changed; the API verb for deny is "refute"
// (UI-DRAFT-BRIEF decision 2). Map here — never display "refute".
export function verdictApiValue(ui: "confirm" | "deny" | "changed"): VerdictLiteral {
  return ui === "deny" ? "refute" : ui;
}
