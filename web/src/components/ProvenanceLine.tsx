import type { ReactNode } from "react";
import type { ReasonOut } from "@/lib/types";
import { fmtAsOf, fmtVerified, glyphFor } from "@/lib/format";
import styles from "./ProvenanceLine.module.css";

/* Measured values wear the global .data class (docs/00 §1): unit-bearing
   numbers, comparator thresholds, ranges, clock times, and long station
   ids. Claim words stay in the UI font; unmatched text renders verbatim —
   the server composes reason.text. No lookbehind (Safari < 16.4). */
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

export function ProvenanceLine({
  reasons,
  liveUnavailable = [],
  lastVerifiedAt,
  verifiedBy,
  compact = false,
}: {
  reasons: ReasonOut[];
  liveUnavailable?: string[];
  lastVerifiedAt?: string | null;
  verifiedBy?: string | null;
  compact?: boolean;
}) {
  const showFallback = reasons.length === 0 && !lastVerifiedAt;

  return (
    <div className={compact ? `${styles.root} ${styles.compact}` : styles.root}>
      {reasons.map((reason, i) => (
        <div
          key={reason.window_id ?? `${reason.wtype}-${i}`}
          className={`${styles.prov} ${reason.fresh ? styles.isLive : styles.isFading}`}
        >
          <span className={styles.glyph} aria-hidden="true">
            {glyphFor(reason)}
          </span>
          <div>
            <p className={styles.lead}>
              {withData(reason.text)}
              {!reason.fresh && reason.as_of ? (
                <>
                  {" — "}
                  {withData(fmtAsOf(reason.as_of))}
                </>
              ) : null}
            </p>
            {reason.source ? (
              <p className={styles.detail}>{withData(reason.source)}</p>
            ) : null}
          </div>
        </div>
      ))}

      {liveUnavailable.map((label) => (
        <div key={label} className={`${styles.prov} ${styles.isUnknown}`}>
          <span className={styles.glyph} aria-hidden="true">
            ○
          </span>
          <div>
            <p className={styles.lead}>Live {label} unavailable</p>
          </div>
        </div>
      ))}

      {showFallback ? (
        <div className={`${styles.prov} ${styles.noGlyph} ${styles.isStatic}`}>
          <div>
            <p className={styles.fallback}>
              From community reports · not yet verified
            </p>
          </div>
        </div>
      ) : null}

      {lastVerifiedAt ? (
        <div className={styles.prov}>
          <span
            className={`${styles.glyph} ${styles.check}`}
            aria-hidden="true"
          >
            ✓
          </span>
          <div>
            <p className={styles.credit}>
              {fmtVerified(lastVerifiedAt)}
              {verifiedBy ? (
                <>
                  {" by "}
                  <span className={styles.verifier}>
                    @{verifiedBy.replace(/^@/, "")}
                  </span>
                </>
              ) : null}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
