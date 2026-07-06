"use client";

import type { ReasonOut } from "@/lib/types";
import { fmtAsOf, glyphFor, withData } from "@/lib/format";
import { PrimaryButton, TertiaryButton } from "./Buttons";
import styles from "./AlertCard.module.css";

/* Surface 3 (docs/02 §2): a save is a standing query, not a bookmark. The
   condition cron fires this card on a trigger transition — `message` is the
   server-composed trigger copy ("Dog Mountain balsamroot peaking"),
   `savedNote` the memory framing ("you saved this in January"). Two actions
   per the alert-card spec (design/surfaces/alert-card.html): "I'm going"
   filled primary + "see conditions →" quiet tertiary.

   `reason` carries the live provenance for the trigger (source + freshness
   — every card shows its provenance line, constraint block). /saves serves
   none of this (flagged API gap in types.ts / saves page); the owner
   resolves it from the feed where it can, and the card degrades to the
   honest "live trigger detail unavailable" line where it can't. */
export function AlertCard({
  message,
  savedNote,
  reason,
  onGoing,
  onOpen,
}: {
  message: string;
  savedNote?: string;
  reason?: ReasonOut | null;
  onGoing?: () => void;
  onOpen?: () => void;
}) {
  return (
    <section className={styles.alert}>
      <p className={styles.message}>{withData(message)}</p>
      {reason ? (
        <p
          className={`${styles.prov} ${reason.fresh ? styles.isLive : styles.isFading}`}
        >
          <span className={styles.glyph} aria-hidden="true">
            {glyphFor(reason)}
          </span>
          {reason.source ? withData(reason.source) : null}
          {!reason.fresh && reason.as_of ? (
            <> · {withData(fmtAsOf(reason.as_of))}</>
          ) : null}
        </p>
      ) : (
        /* Degraded honestly — never a bare nudge (docs/04 §4). */
        <p className={`${styles.prov} ${styles.isUnknown}`}>
          <span className={styles.glyph} aria-hidden="true">
            ○
          </span>
          live trigger detail unavailable
        </p>
      )}
      {savedNote ? <span className={styles.memory}>{savedNote}</span> : null}
      <div className={styles.actions}>
        {onGoing ? (
          <PrimaryButton onClick={onGoing}>I’m going</PrimaryButton>
        ) : null}
        <TertiaryButton onClick={onOpen}>see conditions →</TertiaryButton>
      </div>
    </section>
  );
}
