"use client";

import { Fragment, type ReactNode } from "react";
import type { ClaimOut } from "@/lib/types";
import { fmtObservedDate, fmtVerified, withData } from "@/lib/format";
import { VerdictControls, type UiVerdict } from "./VerdictControls";
import styles from "./ClaimRow.module.css";

/* The API serves no claim statement text (verbatim quotes are never
   republished, docs/03 §2) — the row leads with a plain-language class
   label and lets the provenance meta carry the story. `word` and `period`
   restate the docs/01 §5 decay half-lives for the "needs a fresh look"
   wording: "access claim — decays in months". */
type ClassInfo = { label: string; word: string; period: string | null };

const CCLASS: Record<string, ClassInfo> = {
  geomorphic: { label: "Permanent feature", word: "feature", period: "decades" },
  seasonal_bio: { label: "Seasonal timing", word: "seasonal", period: "years" },
  access: { label: "Access & approach", word: "access", period: "months" },
  hazard_calibration: { label: "Hazard calibration", word: "hazard", period: "weeks" },
};

function classInfo(cclass: string): ClassInfo {
  const known = CCLASS[cclass];
  if (known) return known;
  const words = cclass.replace(/_/g, " ");
  return {
    label: words.charAt(0).toUpperCase() + words.slice(1),
    word: words,
    period: null,
  };
}

// docs/01 §4 gate 2: the serving-confidence bar. A claim decayed below it
// is due for re-verification — rendered as the fading "needs a fresh look"
// treatment, never as a bare percent badge.
const SERVING_CONFIDENCE_BAR = 0.45;

export function ClaimRow({
  claim,
  answered,
  onVerdict,
}: {
  claim: ClaimOut;
  answered?: UiVerdict | null;
  onVerdict: (
    claimId: string,
    apiVerdict: "confirm" | "refute" | "changed",
  ) => void | Promise<void>;
}) {
  const info = classInfo(claim.cclass);
  const hazard = claim.cclass === "hazard_calibration";
  // The DB enum says "llm_extracted"; fixtures serialize "extracted" —
  // any extracted stype means no human has stood there yet.
  const extractionOnly = claim.source_type.includes("extracted");
  const needsFreshLook = !extractionOnly && claim.confidence < SERVING_CONFIDENCE_BAR;

  const meta: ReactNode[] = [];
  if (hazard) meta.push("hazard-class");
  if (claim.source_domain) {
    meta.push(
      claim.source_url ? (
        <a
          className={styles.srcLink}
          href={claim.source_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {claim.source_domain}
          {" "}→
        </a>
      ) : (
        claim.source_domain
      ),
    );
  }
  if (!needsFreshLook) {
    if (claim.observed_date) {
      // Experience date, never post date (docs/03 §2).
      meta.push(`reported ${fmtObservedDate(claim.observed_date)}`);
    } else if (claim.source_type === "user_reported") {
      meta.push("reported firsthand");
    }
  }
  if (claim.source_type === "founder_verified") meta.push("founder-verified");
  if (claim.source_type === "sensor_derived") meta.push("sensor-derived");

  if (extractionOnly) {
    meta.push("extracted", "never field-verified");
  } else if (needsFreshLook) {
    const noun = hazard ? null : `${info.word} claim`;
    const decay = info.period ? `decays in ${info.period}` : null;
    const phrase = noun && decay ? `${noun} — ${decay}` : (noun ?? decay);
    if (phrase) meta.push(phrase);
    // withData catches durations ("6 days"); dates stay in the UI font.
    meta.push(withData(`last ${fmtVerified(claim.last_evidence_at)}`));
  } else {
    // Non-extraction evidence is field truth; last_evidence_at is the
    // decay clock any confirming evidence resets (docs/01 §5).
    meta.push(
      <span className={styles.ok}>
        ✓ {withData(fmtVerified(claim.last_evidence_at))}
      </span>,
    );
  }

  const chips: { className: string; text: string }[] = [];
  if (hazard) chips.push({ className: styles.chipHazard, text: "hazard-gated" });
  if (needsFreshLook)
    chips.push({ className: styles.chipFading, text: "needs a fresh look" });
  if (extractionOnly)
    chips.push({ className: styles.chipUnknown, text: "unverified" });

  return (
    <div className={styles.row}>
      <div className={styles.copy}>
        <p
          className={
            extractionOnly ? `${styles.claim} ${styles.isUntrusted}` : styles.claim
          }
        >
          {info.label}
        </p>
        <p
          className={
            extractionOnly ? `${styles.meta} ${styles.isUnknown}` : styles.meta
          }
        >
          {meta.map((segment, i) => (
            <Fragment key={i}>
              {i > 0 ? " · " : null}
              {segment}
            </Fragment>
          ))}
        </p>
        {chips.length > 0 ? (
          <div className={styles.chips}>
            {chips.map((chip) => (
              <span key={chip.text} className={`${styles.chip} ${chip.className}`}>
                {chip.text}
              </span>
            ))}
          </div>
        ) : null}
        {/* No assumption-of-risk copy here: the affordance foot's
            SafetyLine renders the SERVER string once per section (decision
            3 — single legal source). A second, client-mirrored copy per
            hazard claim duplicated the legal text and could drift. */}
      </div>
      <VerdictControls
        control={{ claim_id: claim.id, allowed_verdicts: claim.allowed_verdicts }}
        onVerdict={onVerdict}
        answered={answered}
        compact
      />
    </div>
  );
}
