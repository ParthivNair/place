"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { verifyToken } from "@/lib/api";
import type { UserOut } from "@/lib/types";
import { PrimaryButton, TertiaryButton } from "@/components/Buttons";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import styles from "./verify.module.css";

/* The magic-link landing. The session cookie is set server-side by
   /auth/verify and lasts ~180 days, so this page's whole job is one calm
   receipt: who you are, and the way back to the feed. Identity appears in
   the product only as provenance credit ("@gorge_amy"), so that is the
   form it takes here too. */

type VerifyState =
  | { status: "checking" }
  | { status: "in"; user: UserOut }
  | { status: "failed" };

function VerifyLanding() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<VerifyState>({ status: "checking" });
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    if (!token) {
      setState({ status: "failed" });
      setSheetOpen(true);
      return;
    }
    let cancelled = false;
    verifyToken(token)
      .then((user) => {
        if (!cancelled) setState({ status: "in", user });
      })
      .catch(() => {
        // Expired and invalid tokens land the same way: calm copy plus a
        // fresh link — never an error code.
        if (!cancelled) {
          setState({ status: "failed" });
          setSheetOpen(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (state.status === "checking") {
    return <p className={styles.checking}>Checking your link…</p>;
  }

  if (state.status === "in") {
    const { user } = state;
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
        <p className={styles.session}>
          You’ll stay signed in on this device for about six months.
        </p>
        <div className={styles.action}>
          <PrimaryButton onClick={() => router.push("/")}>
            This weekend’s feed →
          </PrimaryButton>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className={styles.card}>
        <h1 className={styles.headline}>
          That link expired — they last <span className="data">15 minutes</span>.
        </h1>
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

// useSearchParams must sit under a Suspense boundary in the App Router.
export default function VerifyPage() {
  return (
    <Suspense fallback={<p className={styles.checking}>Checking your link…</p>}>
      <VerifyLanding />
    </Suspense>
  );
}
