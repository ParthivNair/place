"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { requestMagicLink } from "@/lib/api";
import { PrimaryButton, TertiaryButton } from "./Buttons";
import styles from "./MagicLinkSheet.module.css";

export interface MagicLinkSheetProps {
  pitch?: string;
  open: boolean;
  onClose: () => void;
}

/* Auth is interception, not a gate (UI-DRAFT-BRIEF decision 11): this sheet
   opens over the triggering surface at the first save/going/verdict — never
   before value — and the intent resumes after /auth/verify. Sessions run
   ~180 days, so the copy stays calm: one pitch sentence, one field, one
   48px primary. */

const RESEND_AFTER_S = 60;
const DEFAULT_PITCH = "We’ll tell you when it’s flowing hard.";

export function MagicLinkSheet({
  pitch = DEFAULT_PITCH,
  open,
  onClose,
}: MagicLinkSheetProps) {
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<"ask" | "sent">("ask");
  const [sending, setSending] = useState(false);
  const [resent, setResent] = useState(false);
  const [sendFailed, setSendFailed] = useState(false);
  const [resendIn, setResendIn] = useState(RESEND_AFTER_S);
  const fieldRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();

  // The clock keeps running while the sheet is closed — reopening must not
  // hand back a reset 60s wait.
  const counting = phase === "sent" && resendIn > 0;
  useEffect(() => {
    if (!counting) return;
    const timer = setInterval(
      () => setResendIn((s) => Math.max(0, s - 1)),
      1000,
    );
    return () => clearInterval(timer);
  }, [counting]);

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

  async function send(isResend: boolean) {
    const address = email.trim();
    if (!address || sending) return;
    setSending(true);
    setSendFailed(false);
    try {
      await requestMagicLink(address);
      setPhase("sent");
      setResent(isResend);
      setResendIn(RESEND_AFTER_S);
    } catch {
      setSendFailed(true);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(false);
  }

  function handleResend() {
    if (resendIn > 0) return;
    void send(true);
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
          {phase === "ask" ? pitch : "Check your email"}
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
                Email me a link
              </PrimaryButton>
            </div>
            <div className={styles.quietRow}>
              <TertiaryButton onClick={onClose}>Not now</TertiaryButton>
            </div>
          </form>
        ) : (
          <div aria-live="polite">
            <p className={styles.note}>
              {resent ? "Sent another link to " : "We emailed a sign-in link to "}
              <strong className={styles.addr}>{email.trim()}</strong>.
            </p>
            <p className={styles.meta}>
              From Place · links last <span className="data">15 minutes</span>.
            </p>
            {sendFailed ? (
              <p className={styles.error} role="alert">
                That didn’t send — try again.
              </p>
            ) : null}
            <div className={styles.resendRow}>
              <button
                type="button"
                className={styles.resend}
                disabled={resendIn > 0 || sending}
                onClick={handleResend}
              >
                {resendIn > 0 ? (
                  <>
                    Resend in <span className="data">{resendIn}s</span>
                  </>
                ) : (
                  "Resend link"
                )}
              </button>
              <TertiaryButton onClick={onClose}>Done</TertiaryButton>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
