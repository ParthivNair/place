"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { requestMagicLink } from "@/lib/api";
import { PrimaryButton, TertiaryButton } from "@/components/Buttons";
import styles from "./WaterfallsEmailSheet.module.css";

/* The ranker's conversion moment (UI-DRAFT-BRIEF §4): tapping ♥ on a row
   opens this capture. Pitch verbatim, one field, one button, one line of
   reassurance. Same magic-link machinery as MagicLinkSheet, but that sheet
   is the in-app auth interception — this is the public-page ask with the
   required reassurance line, so it's a sibling, not a reuse. The sent
   phase is state (d), the email-sent interstitial. */

const PITCH = "We’ll tell you when it’s flowing hard.";
const REASSURE = "One email when conditions fire — that’s it.";

export interface WaterfallsEmailSheetProps {
  /* The falls whose ♥ opened the sheet — the sent copy names it. */
  rowName: string;
  open: boolean;
  /* Fires once on a successful send, before the interstitial renders, so
     the row behind the sheet is already ♥ "watching this for you". */
  onSent: () => void;
  onClose: () => void;
}

export function WaterfallsEmailSheet({
  rowName,
  open,
  onSent,
  onClose,
}: WaterfallsEmailSheetProps) {
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<"ask" | "sent">("ask");
  const [sending, setSending] = useState(false);
  const [sendFailed, setSendFailed] = useState(false);
  const fieldRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    if (phase === "ask") fieldRef.current?.focus();
    else titleRef.current?.focus();
  }, [open, phase]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim();
    if (!address || sending) return;
    setSending(true);
    setSendFailed(false);
    try {
      await requestMagicLink(address);
      setPhase("sent");
      onSent();
    } catch {
      setSendFailed(true);
    } finally {
      setSending(false);
    }
  }

  if (!open) return null;

  return (
    <>
      <div className={styles.scrim} onClick={onClose} aria-hidden="true" />
      <section
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 className={styles.title} id={titleId} tabIndex={-1} ref={titleRef}>
          {phase === "ask" ? PITCH : "Check your email"}
        </h2>
        {phase === "ask" ? (
          <form className={styles.form} onSubmit={handleSubmit}>
            <input
              ref={fieldRef}
              className={styles.field}
              type="email"
              name="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              required
              placeholder="you@example.com"
              aria-label="Email address"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            {sendFailed ? (
              <p className={styles.error} role="alert">
                That didn’t send — try again.
              </p>
            ) : null}
            <div className={styles.primaryRow}>
              <PrimaryButton type="submit" disabled={sending}>
                Send magic link
              </PrimaryButton>
            </div>
            <p className={styles.reassure}>{REASSURE}</p>
          </form>
        ) : (
          <div aria-live="polite">
            <p className={styles.note}>
              We emailed a link to{" "}
              <strong className={styles.addr}>{email.trim()}</strong> — tap it
              and we’re watching {rowName} for you.
            </p>
            <p className={styles.meta}>
              From Place · links last <span className="data">15 minutes</span>.
            </p>
            <p className={styles.meta}>{REASSURE}</p>
            <div className={styles.doneRow}>
              <TertiaryButton onClick={onClose}>Done</TertiaryButton>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
