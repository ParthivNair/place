"use client";

import type { ReactNode } from "react";
import { TertiaryButton } from "./Buttons";
import styles from "./AlertCard.module.css";

/* Measured values in the server-composed alert copy wear the global .data
   class (docs/00 §1) — same pattern set as ProvenanceLine: unit-bearing
   numbers, comparator thresholds, ranges, clock times, and long station
   ids. Claim words stay in the UI font; unmatched text renders verbatim.
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

/* Surface 3 (docs/02 §2): a save is a standing query, not a bookmark. The
   condition cron fires this card on a trigger transition — `message` is the
   server-composed trigger copy ("Dog Mountain balsamroot peaking"),
   `savedNote` the memory framing ("you saved this in January"). The card
   carries one quiet action by contract; "I'm going" lives on the place
   page that `onOpen` leads to. */
export function AlertCard({
  message,
  savedNote,
  onOpen,
}: {
  message: string;
  savedNote?: string;
  onOpen?: () => void;
}) {
  return (
    <section className={styles.alert}>
      <p className={styles.message}>{withData(message)}</p>
      {savedNote ? <span className={styles.memory}>{savedNote}</span> : null}
      <div className={styles.actions}>
        <TertiaryButton onClick={onOpen}>see place →</TertiaryButton>
      </div>
    </section>
  );
}
