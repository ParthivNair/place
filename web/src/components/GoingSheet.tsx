"use client";

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { FeedCard, TripOut } from "@/lib/types";
import { ApiError, createTrip, postEvent } from "@/lib/api";
import { fmtAsOf, glyphFor, nextSaturday } from "@/lib/format";
import { PrimaryButton, TertiaryButton } from "./Buttons";
import { NearbyAfter, type NearbyItem } from "./NearbyAfter";
import styles from "./GoingSheet.module.css";

/* Measured values in the conditions-at-decision line wear the global .data
   class (docs/00 §1) — same pattern set as ProvenanceLine: unit-bearing
   numbers, comparator thresholds, ranges, clock times, and long station
   ids. Claim words stay in the UI font; unmatched text renders verbatim.
   Duplicated locally because ProvenanceLine does not export withData.
   No lookbehind (Safari < 16.4 throws at construction). */
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

function withData(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MEASURE)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      <span key={start} className="data">
        {match[0]}
      </span>,
    );
    cursor = start + match[0].length;
  }
  if (cursor === 0) return text;
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

/* format.ts keeps its weekday/month tables private; the sheet needs its own
   for the planned-date words. Dates render in the UI font, never .data
   (ClaimRow meta-line precedent). */
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const pad2 = (n: number): string => String(n).padStart(2, "0");

const localIsoDate = (d: Date): string =>
  `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

// Parsed by hand: new Date("YYYY-MM-DD") is UTC midnight, which shifts a day
// back in negative-offset timezones (fmtObservedDate precedent).
function localDate(isoDate: string): Date {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y || 0, (m || 1) - 1, d || 1);
}

function addDays(isoDate: string, days: number): string {
  const d = localDate(isoDate);
  d.setDate(d.getDate() + days);
  return localIsoDate(d);
}

function plannedLabel(planned: string, sat: string, sun: string): string {
  if (planned === sat) return "Saturday";
  if (planned === sun) return "Sunday";
  const d = localDate(planned);
  return `${WEEKDAYS[d.getDay()]} ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

// Mock-only until a PAIRS_WITH endpoint exists (UI-DRAFT-BRIEF gap 16) —
// canon pairing fixture: Steeplejack Brewing.
const NEARBY: NearbyItem[] = [
  { name: "Steeplejack Brewing", type: "brewery", minutes: 12 },
];

// No GET /trips exists (UI-DRAFT-BRIEF API note) — the client is the only
// record of its own trip ids; the Sunday verdict sheet reads this key back.
const TRIPS_KEY = "place.trips";

function rememberTrip(trip: TripOut): void {
  try {
    const raw = window.localStorage.getItem(TRIPS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    const trips = Array.isArray(parsed) ? (parsed as TripOut[]) : [];
    window.localStorage.setItem(TRIPS_KEY, JSON.stringify([...trips, trip]));
  } catch {
    // storage unavailable (private mode / quota): the trip exists
    // server-side; only the local Sunday deep-link forgets it
  }
}

export interface GoingSheetProps {
  card: FeedCard;
  open: boolean;
  onClose: () => void;
  onAuthNeeded: () => void;
}

/* The "I'm going" confirmation sheet (docs/02 §2): the tap is the ENTIRE
   ask — no check-in, no tracking, no GPX. Confirms intent, snapshots
   conditions invisibly, sets the Sunday expectation, offers nearby-after. */
export function GoingSheet({ card, open, onClose, onAuthNeeded }: GoingSheetProps) {
  const titleId = useId();
  const whenId = useId();
  const sheetRef = useRef<HTMLElement>(null);

  // Pinned for the sheet's lifetime so the default can't flip at midnight
  // mid-interaction (UI-DRAFT-BRIEF decision 9: default = next Saturday).
  const satDate = useMemo(() => nextSaturday(), []);
  const sunDate = useMemo(() => addDays(satDate, 1), [satDate]);

  const [planned, setPlanned] = useState(satDate);
  const [anotherDay, setAnotherDay] = useState(false);
  const [phase, setPhase] = useState<"idle" | "saving" | "saved">("idle");
  const [failed, setFailed] = useState(false);
  const [noted, setNoted] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) sheetRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const reason = card.reasons[0];
  const dayLabel = plannedLabel(planned, satDate, sunDate);

  // The committed last-mile hand-off — Place never does navigation
  // (UI-DRAFT-BRIEF decision 14).
  const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${card.lat},${card.lng}`;

  async function submit(): Promise<void> {
    if (phase !== "idle") return;
    setPhase("saving");
    setFailed(false);
    try {
      const trip = await createTrip({
        affordance_id: card.affordance_id,
        planned_date: planned,
      });
      rememberTrip(trip);
      // The invisible conditions snapshot — the Sunday sheet's "logged at
      // 990 cfs" moment starts here. Best-effort: the trip is already saved.
      try {
        await postEvent({
          affordance_id: card.affordance_id,
          etype: "going",
          now_score: card.now_score,
          conditions_snapshot: card.conditions,
        });
      } catch {
        // telemetry only
      }
      setPhase("saved");
    } catch (err) {
      setPhase("idle");
      if (err instanceof ApiError && err.status === 401) {
        // Auth intercepts inside the flow without losing the intent
        // (UI-DRAFT-BRIEF decision 11): date, noted rows, and the sheet
        // itself survive; the user re-taps once signed in.
        onAuthNeeded();
        return;
      }
      setFailed(true);
    }
  }

  return (
    <div className={styles.scrim} role="presentation" onClick={onClose}>
      <section
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={styles.sheet}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className={styles.title}>
          You’re going to {card.place_name}
        </h2>

        {phase !== "saved" ? (
          <div className={styles.when} role="group" aria-labelledby={whenId}>
            <p id={whenId} className={styles.label}>
              when
            </p>
            <div className={styles.chips}>
              <button
                type="button"
                className={
                  planned === satDate ? `${styles.chip} ${styles.isOn}` : styles.chip
                }
                aria-pressed={planned === satDate}
                onClick={() => setPlanned(satDate)}
              >
                Sat
              </button>
              <button
                type="button"
                className={
                  planned === sunDate ? `${styles.chip} ${styles.isOn}` : styles.chip
                }
                aria-pressed={planned === sunDate}
                onClick={() => setPlanned(sunDate)}
              >
                Sun
              </button>
              {!anotherDay ? (
                <TertiaryButton onClick={() => setAnotherDay(true)}>
                  another day →
                </TertiaryButton>
              ) : null}
            </div>
            {anotherDay ? (
              <input
                type="date"
                className={styles.dateInput}
                aria-label="Another day"
                value={planned}
                min={localIsoDate(new Date())}
                onChange={(e) => {
                  if (e.target.value) setPlanned(e.target.value);
                }}
              />
            ) : null}
          </div>
        ) : null}

        {reason ? (
          <div className={styles.conditions}>
            <p className={styles.label}>conditions at decision</p>
            <p
              className={`${styles.reason} ${reason.fresh ? styles.isLive : styles.isFading}`}
            >
              <span className={styles.glyph} aria-hidden="true">
                {glyphFor(reason)}
              </span>
              <span>
                {withData(reason.text)}
                {!reason.fresh && reason.as_of ? (
                  <>
                    {" — "}
                    {withData(fmtAsOf(reason.as_of))}
                  </>
                ) : null}
                {reason.source ? <> · {withData(reason.source)}</> : null}
              </span>
            </p>
          </div>
        ) : null}

        <div className={styles.nearby}>
          <NearbyAfter
            items={NEARBY}
            noted={noted}
            onNote={(name) => setNoted((prev) => new Set(prev).add(name))}
          />
        </div>

        <p className={styles.sunday}>
          We’ll ask two quick questions Sunday evening.
        </p>

        {phase === "saved" ? (
          <div className={styles.saved} role="status">
            <p className={styles.savedLine}>
              Saved for {dayLabel} <span aria-hidden="true">✓</span>
            </p>
            <TertiaryButton href={mapsUrl}>Directions →</TertiaryButton>
          </div>
        ) : (
          <>
            {failed ? (
              <p className={styles.error} role="status">
                Couldn’t save — check your connection and try again.
              </p>
            ) : null}
            <div className={styles.actions}>
              <PrimaryButton
                onClick={() => {
                  void submit();
                }}
                disabled={phase === "saving"}
              >
                I’m going
              </PrimaryButton>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
