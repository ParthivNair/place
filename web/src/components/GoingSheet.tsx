"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { FeedCard } from "@/lib/types";
import { ApiError, createTrip, postEvent } from "@/lib/api";
import { glyphFor, nextSaturday, staleAsOf, withData } from "@/lib/format";
import { clearPendingIntent, rememberTrip, writePendingIntent } from "@/lib/local";
import { PrimaryButton, TertiaryButton } from "./Buttons";
import { NearbyAfter, type NearbyItem } from "./NearbyAfter";
import { errorToastCopy } from "./Toast";
import styles from "./GoingSheet.module.css";

/* Measured values wear the global .data class via the shared lib/format
   withData (single source for the brand rule). */

/* format keeps its weekday/month tables private; the sheet needs its own
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

/* "another day →" reveals quiet day CHIPS, never a date-picker form
   (decision 9). Seven days covers the horizon the feed ranks for. */
const OTHER_DAY_COUNT = 7;

export interface GoingSheetProps {
  card: FeedCard;
  open: boolean;
  onClose: () => void;
  /* 401 interception (decision 11): the sheet hands the owner a retry
     closure so the kept trip intent resumes once the auth sheet closes —
     the user never re-taps. */
  onAuthNeeded: (retry: () => void) => void;
  /* Fired on save success so the owning page can leave a confirmation
     residue (the saved-for-Sunday toast) after the sheet closes. */
  onSaved?: (dayLabel: string) => void;
}

/* The "I'm going" confirmation sheet (docs/02 §2): the tap is the ENTIRE
   ask — no check-in, no tracking, no GPX. Confirms intent, snapshots
   conditions invisibly, sets the Sunday expectation, offers nearby-after. */
export function GoingSheet({
  card,
  open,
  onClose,
  onAuthNeeded,
  onSaved,
}: GoingSheetProps) {
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
  /* §9 state (e): the sheet is modal, so the shared errorToastCopy
     renders INLINE (a toast would fight the scrim) — same copy source
     as every toast, different placement. */
  const [failNote, setFailNote] = useState<string | null>(null);
  const [noted, setNoted] = useState<Set<string>>(new Set());

  // The "another day" chips: today through the next week, minus the two
  // days the Sat/Sun chips already own.
  const otherDays = useMemo(() => {
    const today = localIsoDate(new Date());
    const days: { iso: string; label: string }[] = [];
    for (let i = 0; i <= OTHER_DAY_COUNT && days.length < OTHER_DAY_COUNT; i += 1) {
      const iso = addDays(today, i);
      if (iso === satDate || iso === sunDate) continue;
      const d = localDate(iso);
      days.push({
        iso,
        label: i === 0 ? "Today" : `${WEEKDAYS[d.getDay()]} ${d.getDate()}`,
      });
    }
    return days;
  }, [satDate, sunDate]);

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
  /* Shared staleAsOf (§9c): the server may have composed "(as of …)" into
     the text already — stamp once, never twice (ProvenanceLine parity). */
  const reasonStamp = reason ? staleAsOf(reason) : null;
  const dayLabel = plannedLabel(planned, satDate, sunDate);

  // The committed last-mile hand-off — Place never does navigation
  // (UI-DRAFT-BRIEF decision 14).
  const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${card.lat},${card.lng}`;

  async function submit(isRetry: boolean): Promise<void> {
    if (phase === "saving" || phase === "saved") return;
    setPhase("saving");
    setFailNote(null);
    try {
      const trip = await createTrip({
        affordance_id: card.affordance_id,
        planned_date: planned,
      });
      // The Sunday sheet renders "You went to {place}" from this record
      // alone — the API echoes no place context back (flagged gap).
      rememberTrip({
        ...trip,
        place_id: card.place_id,
        place_name: card.place_name,
        activity_name: card.activity_name,
      });
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
      // A 401 earlier in this flow parked the intent for /auth/verify;
      // the same-tab retry just completed it — don't complete it twice.
      if (isRetry) clearPendingIntent();
      onSaved?.(plannedLabel(planned, satDate, sunDate));
    } catch (err) {
      setPhase("idle");
      if (!isRetry && err instanceof ApiError && err.status === 401) {
        // Auth intercepts inside the flow without losing the intent
        // (decision 11): date, noted rows, and the sheet itself survive.
        // The intent goes to storage for /auth/verify (the link opens in
        // a fresh tab) AND to the owner as a one-shot retry closure for
        // the same-tab path — whichever completes first wins.
        writePendingIntent({
          type: "trip",
          affordance_id: card.affordance_id,
          planned_date: planned,
          place_id: card.place_id,
          place_name: card.place_name,
          activity_name: card.activity_name,
        });
        onAuthNeeded(() => void submit(true));
        return;
      }
      setFailNote(
        errorToastCopy(err, "Couldn’t save — check your connection and try again."),
      );
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
              /* More quiet chips, one per day — never a date-picker form
                 (decision 9). Day-of-month numerals are dates, so they
                 stay in the UI font. */
              <div
                className={`${styles.chips} ${styles.moreDays}`}
                role="group"
                aria-label="Another day"
              >
                {otherDays.map((day) => (
                  <button
                    key={day.iso}
                    type="button"
                    className={
                      planned === day.iso
                        ? `${styles.chip} ${styles.isOn}`
                        : styles.chip
                    }
                    aria-pressed={planned === day.iso}
                    onClick={() => setPlanned(day.iso)}
                  >
                    {day.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {reason || card.live_unavailable.length > 0 ? (
          <div className={styles.conditions}>
            <p className={styles.label}>conditions at decision</p>
            {reason ? (
              <p
                className={`${styles.reason} ${reason.fresh ? styles.isLive : styles.isFading}`}
              >
                <span className={styles.glyph} aria-hidden="true">
                  {glyphFor(reason)}
                </span>
                <span>
                  {withData(reason.text)}
                  {reasonStamp ? (
                    <>
                      {" — "}
                      {withData(reasonStamp)}
                    </>
                  ) : null}
                  {reason.source ? <> · {withData(reason.source)}</> : null}
                </span>
              </p>
            ) : null}
            {/* §9 state (b): a down feed is named here too — the decision
                deserves the same honesty as the card ("live … unavailable",
                never "conditions bad", docs/04 §4 rule 2). */}
            {card.live_unavailable.map((label) => (
              <p key={label} className={`${styles.reason} ${styles.isUnknown}`}>
                <span className={styles.glyph} aria-hidden="true">
                  ○
                </span>
                <span>live {label} unavailable</span>
              </p>
            ))}
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
          <>
            {/* No ✓ here — the glyph means verification only; saving a
                trip verifies nothing. */}
            <div className={styles.saved} role="status">
              <p className={styles.savedLine}>Saved for {dayLabel}</p>
              <TertiaryButton href={mapsUrl}>Directions →</TertiaryButton>
            </div>
            {/* Decision 15: the Sunday sheet is reachable in-app (push
                sending is PR-9). The confirmation that promises the
                questions is the least-chrome doorway to them. */}
            <div className={styles.sundayLink}>
              <TertiaryButton href="/sunday">Sunday questions →</TertiaryButton>
            </div>
          </>
        ) : (
          <>
            {failNote ? (
              <p className={styles.error} role="status">
                {failNote}
              </p>
            ) : null}
            {/* Two actions, per the sheet composition: filled primary +
                the Directions tertiary (the committed last-mile hand-off
                exists before commitment too — checking the drive is part
                of deciding). */}
            <div className={styles.actions}>
              <PrimaryButton
                onClick={() => {
                  void submit(false);
                }}
                disabled={phase === "saving"}
              >
                I’m going
              </PrimaryButton>
              <TertiaryButton href={mapsUrl}>Directions →</TertiaryButton>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
