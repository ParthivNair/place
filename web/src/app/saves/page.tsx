"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { SavedItem, SaveKind } from "@/lib/types";
import { ApiError, listSaves, removeSave } from "@/lib/api";
import { AlertCard } from "@/components/AlertCard";
import { PrimaryButton, SaveHeart, TertiaryButton } from "@/components/Buttons";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
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

// "Recent" reaches back a bloom-season: the canon May 12 balsamroot alert
// still tops the view on the Jul 5 reference Sunday.
const ALERT_RECENT_DAYS = 60;

// The alert's trigger copy lives in the server-composed push payload;
// /saves serves only last_alerted_at — flagged API gap (SavedItem wants a
// last_alert_message). Canon copy backs the mock demo; unknown places fall
// back to naming the saved activity.
const CANON_ALERT_COPY: Record<string, string> = {
  "Dog Mountain": "Dog Mountain balsamroot peaking",
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
// the fmtVerified idiom in @/lib/format.
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

  // The tap IS the confirm: the row disappears immediately; a failed
  // delete restores it — never pretend a delete stuck.
  const handleUnsave = useCallback((item: SavedItem) => {
    setSaves((prev) =>
      prev.filter(
        (s) => !(s.affordance_id === item.affordance_id && s.kind === item.kind),
      ),
    );
    void removeSave(item.affordance_id, item.kind).catch(() => {
      setSaves((prev) => [...prev, item]);
    });
  }, []);

  const handleSheetClose = useCallback(() => {
    setSheetOpen(false);
    // A session may exist now (magic link verified elsewhere) — recheck.
    void load();
  }, [load]);

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

      {status === "ready" ? (
        <>
          {alerted ? (
            <AlertCard
              message={
                CANON_ALERT_COPY[alerted.place_name] ??
                `${alerted.place_name} — conditions alert for your saved ${activityLabel(alerted.activity_id)}`
              }
              savedNote={savedNoteFor(alerted.created_at)}
              onOpen={() => router.push(`/places/${alerted.place_id}`)}
            />
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
                          <p className={styles.watch}>
                            watching conditions for you
                            {item.last_alerted_at ? (
                              <>
                                {" · alerted "}
                                <span className="data">
                                  {fmtAlertDate(item.last_alerted_at)}
                                </span>
                              </>
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
    </div>
  );
}
