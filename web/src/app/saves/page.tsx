"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { FeedCard, SavedItem, SaveKind } from "@/lib/types";
import { ApiError, getFeed, listSaves, removeSave } from "@/lib/api";
import { withData } from "@/lib/format";
import { AlertCard } from "@/components/AlertCard";
import { PrimaryButton, SaveHeart, TertiaryButton } from "@/components/Buttons";
import { GoingSheet } from "@/components/GoingSheet";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import { Toast, useToast } from "@/components/Toast";
import styles from "./saves.module.css";

/* Surface 3 (docs/02 §2): a save is a standing query, not a bookmark —
   want-to means "watch conditions for me"; been/loved are memory. One
   list, three kind chips, no lists-of-lists. */

const KIND_ORDER: SaveKind[] = ["want_to", "been", "loved"];

const KIND_LABELS: Record<SaveKind, string> = {
  want_to: "want-to",
  been: "been",
  loved: "loved",
};

const EMPTY_COPY: Record<SaveKind, string> = {
  want_to: "Save a place and we’ll watch conditions for you.",
  been: "Nothing here yet.",
  loved: "Nothing here yet.",
};

const SIGNIN_PITCH = "Save a place and we’ll watch conditions for you";
const GOING_PITCH =
  "Sign in to declare the trip — we’ll check conditions before you go.";

/* Value before asks (docs/07): Portland is the default feed origin —
   duplicated from app/page.tsx, which keeps its constant private. */
const PORTLAND = { lat: 45.512, lng: -122.658 };

// "Recent" reaches back a bloom-season: the canon May 12 balsamroot alert
// still tops the view on the Jul 5 reference Sunday.
const ALERT_RECENT_DAYS = 60;

// The alert's trigger copy lives in the server-composed push payload;
// /saves serves only last_alerted_at — flagged API gap (SavedItem wants a
// last_alert_message, plus the trigger's provenance). Canon copy backs the
// mock demo; unknown places fall back to naming the saved activity.
const CANON_ALERT_COPY: Record<string, string> = {
  "Dog Mountain": "Dog Mountain balsamroot peaking",
};

/* Standing-query glyphs, from the single set: ⚡ weather-triggered live ·
   ● other live · ○ unknown. Absent window_state (the real API today —
   flagged gap in types.ts) honestly renders ○. */
const WINDOW_GLYPHS: Record<string, string> = {
  firing: "⚡",
  live: "●",
  unknown: "○",
};

const MONTHS_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const MONTHS_FULL = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// activity_id is a snake_case enum ("wildflower_hike"); /saves carries no
// activity_name — same humanization as place_kind in ExperienceCard.
function activityLabel(activityId: string): string {
  return activityId.replace(/_/g, " ");
}

function daysSince(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 86_400_000;
}

// "alerted May 12" — year appended only across a year boundary, mirroring
// the fmtVerified idiom. A calendar date is copy, not a measured value:
// it renders in the UI font, never .data (ClaimRow meta-line precedent).
function fmtAlertDate(iso: string): string {
  const d = new Date(iso);
  const label = `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`;
  return d.getFullYear() === new Date().getFullYear()
    ? label
    : `${label}, ${d.getFullYear()}`;
}

// "you saved this in January" — memory framing, never a measured value.
function savedNoteFor(createdAt: string): string {
  const d = new Date(createdAt);
  const month = MONTHS_FULL[d.getMonth()];
  return d.getFullYear() === new Date().getFullYear()
    ? `you saved this in ${month}`
    : `you saved this in ${month} ${d.getFullYear()}`;
}

type Status = "loading" | "ready" | "unauthed" | "error";

export default function SavesPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("loading");
  const [saves, setSaves] = useState<SavedItem[]>([]);
  const [kind, setKind] = useState<SaveKind>("want_to");
  const [sheetOpen, setSheetOpen] = useState(true);
  const [goingCard, setGoingCard] = useState<FeedCard | null>(null);
  const [goingAuthOpen, setGoingAuthOpen] = useState(false);
  /* The alert's FeedCard, resolved by affordance_id from the live feed —
     the only client-side source for the trigger's provenance and for what
     the GoingSheet needs. Null when the card isn't in this week's feed
     (real-mode possibility); the AlertCard then degrades honestly. */
  const [alertCard, setAlertCard] = useState<FeedCard | null>(null);
  const pendingGoing = useRef<(() => void) | null>(null);
  // §9 state (e): the shared toast treatment — never a per-page one-off.
  const { toast, showToast } = useToast();
  const savedDay = useRef<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setSaves(await listSaves());
      setStatus("ready");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setStatus("unauthed");
      } else {
        setStatus("error");
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      saves
        .filter((s) => s.kind === kind)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [saves, kind],
  );

  const wantToCount = useMemo(
    () => saves.filter((s) => s.kind === "want_to").length,
    [saves],
  );

  // Top slot: the most recently alerted save with a recent alert.
  const alerted = useMemo(() => {
    let best: SavedItem | null = null;
    for (const s of saves) {
      if (!s.last_alerted_at) continue;
      if (daysSince(s.last_alerted_at) > ALERT_RECENT_DAYS) continue;
      if (!best || s.last_alerted_at > (best.last_alerted_at ?? "")) best = s;
    }
    return best;
  }, [saves]);

  useEffect(() => {
    if (!alerted) return;
    let cancelled = false;
    getFeed({ lat: PORTLAND.lat, lng: PORTLAND.lng }).then(
      (res) => {
        if (cancelled) return;
        setAlertCard(
          res.cards.find((c) => c.affordance_id === alerted.affordance_id) ??
            null,
        );
      },
      () => {
        /* feed down: the AlertCard renders its degraded provenance line */
      },
    );
    return () => {
      cancelled = true;
    };
  }, [alerted]);

  // The tap IS the confirm: the row disappears immediately; a failed
  // delete restores it — never pretend a delete stuck.
  const handleUnsave = useCallback(
    (item: SavedItem) => {
      setSaves((prev) =>
        prev.filter(
          (s) => !(s.affordance_id === item.affordance_id && s.kind === item.kind),
        ),
      );
      void removeSave(item.affordance_id, item.kind).catch(() => {
        setSaves((prev) => [...prev, item]);
        // §9e: the row is back; the shared toast says why.
        showToast("Couldn’t remove that save — try again.");
      });
    },
    [showToast],
  );

  const handleSheetClose = useCallback(() => {
    setSheetOpen(false);
    // A session may exist now (magic link verified elsewhere) — recheck.
    void load();
  }, [load]);

  const handleGoingAuthClose = useCallback(() => {
    setGoingAuthOpen(false);
    // One retry on close — the kept trip intent resumes (decision 11).
    const retry = pendingGoing.current;
    pendingGoing.current = null;
    retry?.();
  }, []);

  if (status === "unauthed") {
    return (
      <>
        <section className={styles.signin}>
          <h1 className={styles.title}>Saved</h1>
          <p className={styles.pitch}>{SIGNIN_PITCH}.</p>
          <PrimaryButton onClick={() => setSheetOpen(true)}>Sign in</PrimaryButton>
        </section>
        <MagicLinkSheet
          pitch={SIGNIN_PITCH}
          open={sheetOpen}
          onClose={handleSheetClose}
        />
      </>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Saved</h1>

      {status === "error" ? (
        <div>
          <p className={styles.errorNote}>Couldn&rsquo;t load your saves.</p>
          <div className={styles.errorRow}>
            <TertiaryButton onClick={() => void load()}>
              try again &rarr;
            </TertiaryButton>
          </div>
        </div>
      ) : null}

      {status === "loading" ? <SavesSkeleton /> : null}

      {status === "ready" ? (
        <>
          {alerted ? (
            <AlertCard
              message={
                CANON_ALERT_COPY[alerted.place_name] ??
                `${alerted.place_name} — conditions alert for your saved ${activityLabel(alerted.activity_id)}`
              }
              savedNote={savedNoteFor(alerted.created_at)}
              reason={alertCard?.reasons[0] ?? null}
              onGoing={alertCard ? () => setGoingCard(alertCard) : undefined}
              onOpen={() => router.push(`/places/${alerted.place_id}`)}
            />
          ) : wantToCount > 0 ? (
            /* State (b) all-quiet: the standing queries are still working
               even when nothing fires — say so (UI-DRAFT-BRIEF §6). */
            <p className={styles.allQuiet} role="status">
              <span className={styles.allQuietGlyph} aria-hidden="true">
                ○
              </span>
              nothing firing — we&rsquo;re watching{" "}
              <span className="data">{wantToCount}</span>{" "}
              {wantToCount === 1 ? "place" : "places"} for you
            </p>
          ) : null}

          <div className={styles.chips} role="group" aria-label="Saved as">
            {KIND_ORDER.map((k) => (
              <button
                key={k}
                type="button"
                className={k === kind ? `${styles.chip} ${styles.isOn}` : styles.chip}
                aria-pressed={k === kind}
                onClick={() => setKind(k)}
              >
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>

          <section className={styles.listCard} aria-label="Saved places">
            {visible.length === 0 ? (
              <p className={styles.empty}>{EMPTY_COPY[kind]}</p>
            ) : (
              <ul className={styles.list}>
                {visible.map((item) => (
                  <li key={`${item.affordance_id}:${item.kind}`}>
                    <div
                      className={
                        item.kind === "want_to"
                          ? styles.row
                          : `${styles.row} ${styles.rowQuiet}`
                      }
                    >
                      <div className={styles.copy}>
                        <p className={styles.name}>{item.place_name}</p>
                        <p className={styles.meta}>
                          {activityLabel(item.activity_id)}
                        </p>
                        {item.kind === "want_to" ? (
                          /* The standing query made visible: window-state
                             glyph + what the sensor watches. The threshold
                             is a measured value (.data); absent fields
                             (the real API today) degrade to the honest
                             generic line under ○. */
                          <p className={styles.watch}>
                            <span
                              className={`${styles.watchGlyph} ${
                                item.window_state === "firing" ||
                                item.window_state === "live"
                                  ? styles.watchLive
                                  : styles.watchUnknown
                              }`}
                              aria-hidden="true"
                            >
                              {WINDOW_GLYPHS[item.window_state ?? "unknown"] ??
                                "○"}
                            </span>
                            {item.watching ? (
                              <>watching: {withData(item.watching)}</>
                            ) : (
                              "watching conditions for you"
                            )}
                            {item.last_alerted_at ? (
                              <> · alerted {fmtAlertDate(item.last_alerted_at)}</>
                            ) : null}
                          </p>
                        ) : null}
                      </div>
                      <SaveHeart
                        saved
                        onToggle={() => handleUnsave(item)}
                        label={`Unsave ${item.place_name}`}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}

      {goingCard !== null && (
        <GoingSheet
          card={goingCard}
          open
          onClose={() => {
            setGoingCard(null);
            // Same saved-for-Sunday residue the feed leaves (§9e — one
            // toast treatment; the sheet's promise outlives the sheet).
            const day = savedDay.current;
            savedDay.current = null;
            if (day) {
              showToast(
                `Saved for ${day} — we’ll ask two quick questions Sunday evening.`,
              );
            }
          }}
          onAuthNeeded={(retry) => {
            pendingGoing.current = retry;
            setGoingAuthOpen(true);
          }}
          onSaved={(day) => {
            savedDay.current = day;
          }}
        />
      )}
      <MagicLinkSheet
        pitch={GOING_PITCH}
        open={goingAuthOpen}
        onClose={handleGoingAuthClose}
      />
      <Toast message={toast} />
    </div>
  );
}

/* §9 state (f): loading respects the list anatomy — kind chips, then
   rows of name / meta / standing-query line beside the heart's 44px box.
   Never a spinner-only screen (feed SkeletonCard idiom). */
function SavesSkeleton() {
  return (
    <div
      className={styles.skWrap}
      role="status"
      aria-label="Loading your saves"
    >
      <div className={styles.skChips} aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.skChip} />
        ))}
      </div>
      <div className={styles.listCard} aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.skRow}>
            <div className={styles.skCopy}>
              <div className={`${styles.skBar} ${styles.skName}`} />
              <div className={`${styles.skBar} ${styles.skMeta}`} />
              <div className={`${styles.skBar} ${styles.skWatch}`} />
            </div>
            <div className={styles.skHeart} />
          </div>
        ))}
      </div>
    </div>
  );
}
