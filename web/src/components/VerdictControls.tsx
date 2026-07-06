"use client";

import { useState } from "react";
import type { VerdictControl } from "@/lib/types";
import { verdictApiValue } from "@/lib/format";
import styles from "./VerdictControls.module.css";

export type UiVerdict = "confirm" | "deny" | "changed";

const UI_VERDICTS: readonly UiVerdict[] = ["confirm", "deny", "changed"];

const LABELS: Record<UiVerdict, string> = {
  confirm: "Confirm",
  deny: "Deny",
  changed: "Changed",
};

const CHOSEN_CLASS: Record<UiVerdict, string> = {
  confirm: styles.isConfirm,
  deny: styles.isDeny,
  changed: styles.isChanged,
};

// Deny/changed carry the no-penalty framing: a no is worth as much as a
// yes — confidence drops and the claim re-enters the queue, nothing more.
// The conditions snapshot auto-attaches server-side, so the confirm line
// never asks the user to describe the weather.
// Receipt marks come from the single glyph set only (constraint block):
// ✓ is verification; deny/changed receipts are tinted text with no glyph —
// ✕ and ~ don't exist in this system, and ● is reserved for "other live".
const MICRO: Record<UiVerdict, { mark: string | null; markClass: string; text: string }> = {
  confirm: { mark: "✓", markClass: styles.ok, text: "Thanks — logged with today’s conditions" },
  deny: { mark: null, markClass: styles.re, text: "Noted — this claim gets re-checked" },
  changed: { mark: null, markClass: styles.ch, text: "Noted — this claim gets re-checked" },
};

export function VerdictControls({
  control,
  onVerdict,
  answered,
  compact,
}: {
  control: VerdictControl;
  onVerdict: (claimId: string, apiVerdict: "confirm" | "refute" | "changed") => void | Promise<void>;
  answered?: UiVerdict | null;
  compact?: boolean;
}) {
  const [pending, setPending] = useState(false);

  const options = UI_VERDICTS.filter((v) =>
    control.allowed_verdicts.includes(verdictApiValue(v)),
  );

  const locked = pending || answered != null;

  const tap = (v: UiVerdict) => {
    if (locked) return;
    const result = onVerdict(control.claim_id, verdictApiValue(v));
    if (result) {
      setPending(true);
      const settle = () => setPending(false);
      result.then(settle, settle);
    }
  };

  const chipClass = (base: string, v: UiVerdict) =>
    answered == null
      ? base
      : `${base} ${answered === v ? CHOSEN_CLASS[v] : styles.isReceded}`;

  if (compact) {
    // Word labels, not invented glyphs: the single glyph set has no deny/
    // changed mark, so the compact cluster spells its verdicts out at the
    // 13px meta floor (labels are UI copy, not measured values).
    return (
      <div className={styles.miniVerdicts}>
        {options.map((v) => (
          <button
            key={v}
            type="button"
            className={chipClass(styles.mini, v)}
            aria-pressed={answered != null ? answered === v : undefined}
            disabled={locked}
            onClick={() => tap(v)}
          >
            {LABELS[v]}
          </button>
        ))}
      </div>
    );
  }

  const micro = answered != null ? MICRO[answered] : null;

  return (
    <>
      <div className={styles.verdicts}>
        {options.map((v) => (
          <button
            key={v}
            type="button"
            className={chipClass(styles.btn, v)}
            aria-pressed={answered != null ? answered === v : undefined}
            disabled={locked}
            onClick={() => tap(v)}
          >
            {LABELS[v]}
            {v === "confirm" && <span className={styles.glyph}>✓</span>}
          </button>
        ))}
      </div>
      {micro && (
        <p className={styles.micro}>
          {micro.mark ? (
            <span className={`${styles.microMark} ${micro.markClass}`}>{micro.mark}</span>
          ) : null}
          <span>{micro.text}</span>
        </p>
      )}
    </>
  );
}
