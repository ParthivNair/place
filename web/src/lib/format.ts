/* Display formatters for canon copy: "41 min drive", "as of Tue 4pm",
   "verified 6 days ago by @gorge_amy", "~2.5 h". Measured values (values
   with units, durations, clock times, station ids) render inside a .data
   span — pass composed strings through withData below. Calendar dates
   ("Jun 27", "May 12") are copy, not sensor readings: they stay in the UI
   font (ClaimRow meta-line precedent). */

import { createElement, type ReactNode } from "react";
import type { VerdictLiteral } from "./types";

/* Measured values wear the global .data class (docs/00 §1): unit-bearing
   numbers, comparator thresholds, ranges, clock times, and long station
   ids. Claim words stay in the UI font; unmatched text renders verbatim —
   the server composes reason.text. No lookbehind (Safari < 16.4 throws at
   construction). Single source: ProvenanceLine, GoingSheet, AlertCard,
   the place page, and /waterfalls all import this — the .data brand rule
   must not drift across surfaces. */
const NUM = "[−-]?\\d[\\d,.]*";
const RANGE = `${NUM}(?:\\s?[–—-]\\s?${NUM})?`;
const UNIT =
  "(?:cfs|°[cf]|ft|in|mi|km|mm|cm|hours?|hrs?|h|min(?:ute)?s?|days?|weeks?|%)";
const MEASURE = new RegExp(
  [
    `[<>≤≥~]\\s?${RANGE}(?:\\s?${UNIT})?(?![a-z0-9])`,
    `${RANGE}\\s?${UNIT}(?![a-z0-9])`,
    `\\d{1,2}:\\d{2}(?:\\s?(?:am|pm))?`,
    `\\d{1,2}\\s?(?:am|pm)(?![a-z0-9])`,
    `\\d{5,}`,
  ].join("|"),
  "gi",
);

export function withData(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MEASURE)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    // createElement, not JSX — this file stays format.ts so every display
    // formatter lives in the one module surfaces already import.
    nodes.push(
      createElement("span", { key: start, className: "data" }, match[0]),
    );
    cursor = start + match[0].length;
  }
  if (cursor === 0) return text;
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const pad2 = (n: number): string => String(n).padStart(2, "0");

/* Clock and calendar renderings of instants are pinned to Pacific time,
   never the viewer's zone: conditions are Portland phenomena ("as of Fri
   4pm" means 4pm at the gauge — the canon mock composes exactly that from
   23:00Z), and /waterfalls SERVER-renders these strings, so a UTC deploy
   and a Portland visitor must produce byte-identical HTML or React logs a
   hydration error and re-renders the whole SEO page client-side. */
const PACIFIC = "America/Los_Angeles";

const CLOCK_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: PACIFIC,
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

// en-CA renders "2026-07-05" — Pacific calendar parts without hand math.
const YMD_PARTS = new Intl.DateTimeFormat("en-CA", {
  timeZone: PACIFIC,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function pacificClock(d: Date): { weekday: string; clock: string } {
  const parts: Partial<Record<Intl.DateTimeFormatPartTypes, string>> = {};
  for (const p of CLOCK_PARTS.formatToParts(d)) parts[p.type] = p.value;
  const ampm = (parts.dayPeriod ?? "").toLowerCase();
  const clock =
    parts.minute === "00"
      ? `${parts.hour}${ampm}`
      : `${parts.hour}:${parts.minute}${ampm}`;
  return { weekday: parts.weekday ?? "", clock };
}

function pacificYmd(d: Date): [number, number, number] {
  const [y, m, day] = YMD_PARTS.format(d).split("-").map(Number);
  return [y || 0, m || 1, day || 1];
}

// Client-side heuristic until the API serves drive time (UI-DRAFT-BRIEF
// decision 5 — flagged API gap): minutes ≈ distance_km / 1.44, rounded to
// the nearest minute, floor 5. Exact rounding keeps the canon copy intact:
// Tamanawas at 59.0 km renders "41 min drive" verbatim (constraint block) —
// rounding to 5s would quietly rewrite canon mock data.
export function fmtDriveMinutes(distanceKm: number): string {
  const minutes = Math.max(5, Math.round(distanceKm / 1.44));
  return `${minutes} min drive`;
}

/* "7:05am" — the bare Pacific clock time (/waterfalls' "updated this
   morning at" line). Exported, unlike its old viewer-zone private
   ancestor: the Pacific pin must stay single-source. */
export function fmtClockTime(iso: string): string {
  return pacificClock(new Date(iso)).clock;
}

// Freshness honesty (docs/04 §4 rule 1): stale readings render "as of Tue 4pm".
export function fmtAsOf(iso: string): string {
  const { weekday, clock } = pacificClock(new Date(iso));
  return `as of ${weekday} ${clock}`;
}

/* One rule for the stamp everywhere a text-composed reason renders (feed
   ProvenanceLine, place-page condition lead, going-sheet conditions —
   §9 state c, designed once): the API composes "(as of …)" into
   reason.text where it applies (cheat sheet), so append a stamp ONLY
   when the text carries none — one stamp, never two. Fresh reasons
   return null unless forced: the offline shell (§9a) stamps EVERY
   reading, because nothing can be re-evaluated without a network and
   "fresh" only describes the moment it was cached. /waterfalls renders
   the provenance READING, not the composed text, so its stamp can't
   collide and it deliberately doesn't route through here. */
export function staleAsOf(
  reason: {
    text: string;
    fresh: boolean;
    as_of: string | null;
    evaluated_at?: string | null;
  },
  force = false,
): string | null {
  if (reason.fresh && !force) return null;
  if (/\bas of\b/i.test(reason.text)) return null;
  const at = reason.as_of ?? reason.evaluated_at ?? null;
  return at === null ? null : fmtAsOf(at);
}

function pacificDayStamp(d: Date): number {
  const [y, m, day] = pacificYmd(d);
  return Date.UTC(y, m - 1, day);
}

function calendarDaysAgo(iso: string, now: Date): number {
  return Math.round(
    (pacificDayStamp(now) - pacificDayStamp(new Date(iso))) / 86_400_000,
  );
}

/* "verified 6 days ago by @gorge_amy" — named provenance credit is the
   only recognition in the product. `now` defaults to the render moment;
   pass a generation instant where the string must be SSR-deterministic:
   /waterfalls renders relative to its fixture's generated_at, so a
   statically prerendered "verified today" can't rot into tomorrow's
   hydration mismatch. */
export function fmtVerified(
  lastVerifiedAt: string,
  verifiedBy?: string | null,
  now: Date = new Date(),
): string {
  const days = calendarDaysAgo(lastVerifiedAt, now);
  let when: string;
  if (days <= 0) {
    when = "today";
  } else if (days === 1) {
    when = "yesterday";
  } else if (days < 14) {
    when = `${days} days ago`;
  } else {
    const [y, m, day] = pacificYmd(new Date(lastVerifiedAt));
    when = `${MONTHS[m - 1]} ${day}`;
    if (y !== pacificYmd(now)[0]) when += `, ${y}`;
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
