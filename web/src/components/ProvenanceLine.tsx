"use client";

import type { ReasonOut } from "@/lib/types";
import { fmtVerified, glyphFor, staleAsOf, withData } from "@/lib/format";
import { useOnline } from "@/lib/online";
import styles from "./ProvenanceLine.module.css";

/* Measured values wear the global .data class (docs/00 §1) via the shared
   lib/format withData — the single source for the brand rule. Claim words
   stay in the UI font; unmatched text renders verbatim — the server
   composes reason.text.

   Freshness stamps come from the shared staleAsOf (lib/format, §9c):
   stale reasons are stamped "as of <time>" exactly once — the API may
   have composed one into the text already. Offline (§9a) EVERY reading
   is stamped: it can't be re-evaluated without a network, so "fresh"
   only describes the moment it was cached. Glyph and tone stay as
   served — the layout banner owns the connection honesty. */

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
  const online = useOnline();
  const showFallback = reasons.length === 0 && !lastVerifiedAt;

  return (
    <div className={compact ? `${styles.root} ${styles.compact}` : styles.root}>
      {reasons.map((reason, i) => {
        const stamp = staleAsOf(reason, !online);
        return (
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
              {stamp ? (
                <>
                  {" — "}
                  {withData(stamp)}
                </>
              ) : null}
            </p>
            {reason.source ? (
              <p className={styles.detail}>{withData(reason.source)}</p>
            ) : null}
          </div>
        </div>
        );
      })}

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
              {/* withData catches the duration ("6 days") — a measured
                  value; calendar dates ("Jun 27") stay in the UI font. */}
              {withData(fmtVerified(lastVerifiedAt))}
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
