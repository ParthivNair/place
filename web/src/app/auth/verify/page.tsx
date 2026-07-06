"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { addSave, createTrip, verifyToken } from "@/lib/api";
import type { UserOut } from "@/lib/types";
import {
  rememberKnownEmail,
  rememberTrip,
  takePendingIntent,
  type PendingIntent,
} from "@/lib/local";
import { PrimaryButton, TertiaryButton } from "@/components/Buttons";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import styles from "./verify.module.css";

/* The magic-link landing. The session cookie is set server-side by
   /auth/verify and lasts ~180 days. The page's job is a calm receipt AND
   finishing the intercepted intent (decision 11): the save/going that hit
   the 401 was parked in storage (lib/local) because this page usually
   opens from the email in a fresh tab — "You're in — finishing your
   save…", then the receipt. Identity appears in the product only as
   provenance credit ("@gorge_amy"), so that is the form it takes here. */

/* The API rejects a bad token without saying WHY (flagged API-shape gap:
   expired and invalid are one 4xx). The client splits what it can know:
   a missing/malformed token is a broken link, not an expired one — never
   assert an expiry we can't observe (freshness honesty). */
type FailKind = "expired" | "invalid";

type VerifyState =
  | { status: "checking" }
  | { status: "finishing"; user: UserOut; intent: PendingIntent }
  | { status: "in"; user: UserOut; note: string | null }
  | { status: "failed"; kind: FailKind };

function intentNote(intent: PendingIntent, ok: boolean): string {
  if (!ok) {
    return intent.type === "save"
      ? `Couldn’t finish saving ${intent.place_name} — the ♡ on its card will land it now that you’re in.`
      : `Couldn’t finish declaring ${intent.place_name} — one more tap on “I’m going” will land it now that you’re in.`;
  }
  return intent.type === "save"
    ? `Saved — we’re watching ${intent.place_name} for you.`
    : `You’re going to ${intent.place_name} — we’ll ask two quick questions Sunday evening.`;
}

function VerifyLanding() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<VerifyState>({ status: "checking" });
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    if (!token) {
      // No token at all — a truncated/mangled link, distinct from expiry.
      setState({ status: "failed", kind: "invalid" });
      setSheetOpen(true);
      return;
    }
    let cancelled = false;
    verifyToken(token)
      .then((user) => {
        if (cancelled) return;
        // Device-side recognition for the returning-user ask (lib/local).
        rememberKnownEmail(user.email);
        const intent = takePendingIntent();
        if (intent) {
          setState({ status: "finishing", user, intent });
        } else {
          setState({ status: "in", user, note: null });
        }
      })
      .catch(() => {
        // The server can't tell us expired-vs-invalid; 15-minute tokens
        // make expiry the likely story — said as likelihood, not fact.
        if (!cancelled) {
          setState({ status: "failed", kind: "expired" });
          setSheetOpen(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Finish the interrupted intent, then settle into the receipt.
  useEffect(() => {
    if (state.status !== "finishing") return;
    const { user, intent } = state;
    let cancelled = false;
    const done = (ok: boolean) => {
      if (!cancelled) setState({ status: "in", user, note: intentNote(intent, ok) });
    };
    if (intent.type === "save") {
      addSave({ affordance_id: intent.affordance_id, kind: intent.kind }).then(
        () => done(true),
        () => done(false),
      );
    } else {
      createTrip({
        affordance_id: intent.affordance_id,
        planned_date: intent.planned_date,
      }).then(
        (trip) => {
          // The Sunday sheet reads this record back (lib/local).
          rememberTrip({
            ...trip,
            place_id: intent.place_id,
            place_name: intent.place_name,
            activity_name: intent.activity_name,
          });
          done(true);
        },
        () => done(false),
      );
    }
    return () => {
      cancelled = true;
    };
  }, [state]);

  if (state.status === "checking") {
    return <CheckingCard />;
  }

  if (state.status === "finishing") {
    return (
      <p className={styles.checking} role="status">
        You’re in — finishing your{" "}
        {state.intent.type === "save" ? "save" : "trip"}…
      </p>
    );
  }

  if (state.status === "in") {
    const { user, note } = state;
    return (
      <section className={styles.card}>
        <h1 className={styles.headline}>You’re in.</h1>
        <p className={styles.identity}>
          {user.display_name ? (
            <>
              <span className={styles.name}>@{user.display_name}</span>
              <span className={styles.sep} aria-hidden="true">
                {" · "}
              </span>
              <span className={styles.addr}>{user.email}</span>
            </>
          ) : (
            <span className={styles.name}>{user.email}</span>
          )}
        </p>
        {note ? (
          <p className={styles.intentNote} role="status">
            {note}
          </p>
        ) : null}
        <p className={styles.session}>
          You’ll stay signed in on this device for about{" "}
          <span className="data">180 days</span>.
        </p>
        <div className={styles.action}>
          {/* No trailing → on a filled primary — the arrow belongs to
              tertiaries/link-outs only (glyph canon). */}
          <PrimaryButton onClick={() => router.push("/")}>
            This weekend’s feed
          </PrimaryButton>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className={styles.card}>
        <h1 className={styles.headline}>
          {state.kind === "invalid" ? (
            <>That link didn’t come through whole.</>
          ) : (
            <>
              That link didn’t work — they last{" "}
              <span className="data">15 minutes</span>, so it has likely
              expired.
            </>
          )}
        </h1>
        {state.kind === "invalid" ? (
          <p className={styles.failNote}>
            Try tapping it straight from the email again — or just get a
            fresh one.
          </p>
        ) : null}
        <div className={styles.action}>
          <PrimaryButton onClick={() => setSheetOpen(true)}>
            Email me a new link
          </PrimaryButton>
        </div>
        <div className={styles.quietRow}>
          <TertiaryButton href="/">back to the feed →</TertiaryButton>
        </div>
      </section>
      <MagicLinkSheet
        pitch="Enter your email and we’ll send a fresh link."
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
      />
    </>
  );
}

/* §9 state (f): the wait wears the receipt card's own anatomy — the
   checking line where the headline lands, identity/session bars, the
   48px primary block. Never a spinner-only screen. */
function CheckingCard() {
  return (
    <section
      className={styles.card}
      role="status"
      aria-label="Checking your link"
    >
      <p className={styles.checkLead}>Checking your link…</p>
      <div aria-hidden="true">
        <div className={`${styles.skBar} ${styles.skIdentity}`} />
        <div className={`${styles.skBar} ${styles.skSession}`} />
        <div className={styles.skPrimary} />
      </div>
    </section>
  );
}

// useSearchParams must sit under a Suspense boundary in the App Router.
export default function VerifyPage() {
  return (
    <Suspense fallback={<CheckingCard />}>
      <VerifyLanding />
    </Suspense>
  );
}
