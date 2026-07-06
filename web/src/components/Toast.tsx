"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import styles from "./Toast.module.css";

/* The one toast treatment (design/UI-DRAFT-BRIEF.md §9 state e) — every
   surface that leaves a short residue uses this pair, never a per-page
   one-off. A toast is a receipt, not a modal: role=status, quiet card
   chrome, auto-dismissing, one at a time (a second show replaces the
   first). Modal sheets render the same errorToastCopy INLINE instead —
   a toast under their scrim would fight the dialog for attention. */

const TOAST_MS = 4000;

export function useToast(): {
  toast: string | null;
  showToast: (message: string) => void;
} {
  const [toast, setToast] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  return { toast, showToast };
}

/* Shared copy for the API's tellable failures (§9e): 404 the place is
   gone (same words as the place route's own notice), 409 the verdict
   already landed — an honest receipt, canon copy verbatim incl. the ✓
   (prompt 3 state f; 409 is a verdicts-only status per the API cheat
   sheet), 422 a quiet retry. Never a status code on screen. Anything
   else gets the caller's fallback — it knows what was being attempted. */
export function errorToastCopy(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return "This place isn’t available.";
    if (err.status === 409) return "Already logged this week ✓";
    if (err.status === 422) return "That didn’t go through — try again.";
  }
  return fallback;
}

export function Toast({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <div className={styles.toast} role="status">
      {message}
    </div>
  );
}
