"use client";

/* Surface 8 — first-run onboarding (design/UI-DRAFT-BRIEF.md §8, decision
   12): value before asks. The feed renders before any permission, so this
   route is reachable FROM it and never gates it. The one-screen privacy
   posture (docs/07 §2 P5) fronts three sequenced asks — location, install,
   push — each skippable, each with a graceful denial path. Done lands back
   on the feed. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { PushSubscriptionIn } from "@/lib/types";
import { getVapidPublicKey, subscribePush } from "@/lib/api";
import {
  clearInstallPrompt,
  peekInstallPrompt,
  type BeforeInstallPromptEvent,
} from "@/lib/installPrompt";
import { NEIGHBORHOOD_KEY, WELCOME_DONE_KEY, writeLocal } from "@/lib/local";
import { PrimaryButton, TertiaryButton } from "@/components/Buttons";
import styles from "./welcome.module.css";

const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

type Step = "privacy" | "location" | "install" | "push" | "done";
type LocState = "idle" | "locating" | "granted" | "manual" | "set";
type InstallState = "idle" | "prompting" | "installed" | "dismissed";
type PushState =
  | "idle"
  | "requesting"
  | "subscribing"
  | "on"
  | "denied"
  | "unsupported"
  | "failed";

const STEP_META: Record<Step, string> = {
  privacy: "before the asks",
  location: "ask 1 of 3 — skippable",
  install: "ask 2 of 3 — skippable",
  push: "ask 3 of 3 — skippable",
  done: "all set",
};

// applicationServerKey wants raw bytes; VAPID keys travel base64url. The
// explicit ArrayBuffer keeps the view assignable to BufferSource.
function vapidKeyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = window.atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/* Real browser subscription, best-effort: resolves null instead of
   throwing so the caller decides what a failure means per mode. The 4s race
   guards against a service worker that never activates (SwRegister is
   silent on failure by design). */
async function browserSubscription(
  vapidKey: string,
): Promise<PushSubscriptionIn | null> {
  try {
    const reg = await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 4000)),
    ]);
    if (!reg) return null;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKeyBytes(vapidKey),
    });
    const json = sub.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) return null;
    return {
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    };
  } catch {
    return null;
  }
}

export default function WelcomePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("privacy");

  const [loc, setLoc] = useState<LocState>("idle");
  const [neighborhood, setNeighborhood] = useState("");

  const [installEvt, setInstallEvt] = useState<BeforeInstallPromptEvent | null>(
    null,
  );
  const [install, setInstall] = useState<InstallState>("idle");
  const [standalone, setStandalone] = useState(false);
  const [ios, setIos] = useState(false);

  const [push, setPush] = useState<PushState>("idle");

  // Environment reads once on mount; all three asks branch on them.
  useEffect(() => {
    const nav = navigator as Navigator & { standalone?: boolean };
    setStandalone(
      window.matchMedia("(display-mode: standalone)").matches ||
        nav.standalone === true,
    );
    // iPadOS reports MacIntel; touch points tell it apart from a Mac.
    setIos(
      /iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
    );
    // beforeinstallprompt fires once per document load — usually while the
    // user is still on the feed. InstallPromptCapture (root layout) parked
    // it; the listener below only catches a late re-fire on this route.
    setInstallEvt(peekInstallPrompt());
    const onPrompt = (e: Event) => {
      e.preventDefault(); // hold the browser's own banner; the ask is placed
      setInstallEvt(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setInstall("installed");
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  useEffect(() => {
    if (step !== "done") return;
    // Best-effort flag (lib/local): the feed's one-time banner stands down.
    writeLocal(WELCOME_DONE_KEY, new Date().toISOString());
  }, [step]);

  const requestLocation = () => {
    // The permission ask happens here, on tap — never on load (docs/07).
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setLoc("manual");
      return;
    }
    setLoc("locating");
    navigator.geolocation.getCurrentPosition(
      // The grant itself is the prize: the feed's "use my location" now
      // resolves without a prompt. Coordinates are read there, not kept
      // here — never a GPS trace (P5).
      () => setLoc("granted"),
      () => setLoc("manual"), // denial fallback: manual neighborhood entry
      { timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const confirmNeighborhood = () => {
    const name = neighborhood.trim();
    if (!name) return;
    // Best-effort (lib/local): the feed labels its origin from this key.
    writeLocal(NEIGHBORHOOD_KEY, name);
    setLoc("set");
  };

  const promptInstall = async () => {
    const evt = installEvt;
    if (!evt || install === "prompting") return;
    setInstall("prompting");
    try {
      await evt.prompt();
      const choice = await evt.userChoice;
      setInstall(choice.outcome === "accepted" ? "installed" : "dismissed");
    } catch {
      setInstall("dismissed");
    } finally {
      // A BeforeInstallPromptEvent prompts once — spent here and in the
      // layout-level stash.
      setInstallEvt(null);
      clearInstallPrompt();
    }
  };

  const enablePush = async () => {
    if (push === "requesting" || push === "subscribing") return;
    if (
      !("Notification" in window) ||
      !("PushManager" in window) ||
      !("serviceWorker" in navigator)
    ) {
      setPush("unsupported");
      return;
    }
    setPush("requesting");
    let permission: NotificationPermission;
    try {
      permission = await Notification.requestPermission();
    } catch {
      permission = Notification.permission;
    }
    if (permission !== "granted") {
      // Real-permission denial is a quiet state, not an error — the
      // Thursday feed carries the product without push.
      setPush("denied");
      return;
    }
    setPush("subscribing");
    try {
      const key = await getVapidPublicKey();
      let sub = await browserSubscription(key);
      if (!sub) {
        if (!MOCK) {
          setPush("failed");
          return;
        }
        // The mock VAPID fixture is not a valid P-256 point, so the
        // browser refuses it; mock subscribePush records the opt-in
        // all the same.
        sub = {
          endpoint: "https://mock.place.invalid/push",
          keys: { p256dh: "mock-p256dh", auth: "mock-auth" },
        };
      }
      await subscribePush(sub);
      setPush("on");
    } catch {
      setPush("failed");
    }
  };

  const installed = standalone || install === "installed";
  // iOS delivers web push only to the Home-Screen app — the reason install
  // sits inside onboarding at all (UI-DRAFT-BRIEF §8).
  const pushNeedsInstall = ios && !installed;

  return (
    <div className={styles.page}>
      <p className={styles.stepMeta}>{STEP_META[step]}</p>

      {step === "privacy" ? (
        <section className={styles.card} aria-labelledby="welcome-privacy">
          <h1 id="welcome-privacy" className={styles.title}>
            What Place knows
          </h1>
          <p className={styles.lead}>One screen, plain words. This is everything.</p>
          <div className={styles.well}>
            <p className={styles.wellLabel}>collected</p>
            <ul className={styles.facts}>
              <li>Your email — it&rsquo;s how you sign in.</li>
              <li>Your saves — so we can watch conditions for them.</li>
              <li>
                Your one-tap verdicts — with the conditions at that moment
                attached automatically.
              </li>
            </ul>
          </div>
          <div className={`${styles.well} ${styles.wellNever}`}>
            <p className={`${styles.wellLabel} ${styles.wellLabelNever}`}>
              never collected
            </p>
            <ul className={styles.facts}>
              <li>No tracking.</li>
              <li>No GPS traces.</li>
              <li>No ad data.</li>
            </ul>
          </div>
          <div className={styles.actions}>
            <PrimaryButton onClick={() => setStep("location")}>
              Sounds fair
            </PrimaryButton>
          </div>
          <div className={styles.quietRow}>
            <TertiaryButton onClick={() => router.push("/")}>
              back to the feed →
            </TertiaryButton>
          </div>
        </section>
      ) : null}

      {step === "location" ? (
        <section className={styles.card} aria-labelledby="welcome-location">
          <h1 id="welcome-location" className={styles.title}>
            Start from where you are
          </h1>
          <p className={styles.lead}>
            The feed only shows what&rsquo;s worth the drive —{" "}
            <span className="data">30/60/90 min</span> from you. Read once to
            rank the feed; never stored.
          </p>

          {loc === "granted" ? (
            <>
              <p className={styles.confirm} role="status">
                Got it — the feed will rank from where you are.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("install")}>Next</PrimaryButton>
              </div>
            </>
          ) : loc === "set" ? (
            <>
              <p className={styles.confirm} role="status">
                Got it — starting near {neighborhood.trim()}.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("install")}>Next</PrimaryButton>
              </div>
            </>
          ) : loc === "manual" ? (
            <>
              <p className={styles.fallback}>
                No problem — name a neighborhood instead and we&rsquo;ll rank
                from there.
              </p>
              <form
                className={styles.form}
                onSubmit={(e) => {
                  e.preventDefault();
                  confirmNeighborhood();
                }}
              >
                <input
                  className={styles.field}
                  type="text"
                  name="neighborhood"
                  autoComplete="off"
                  autoCapitalize="words"
                  spellCheck={false}
                  placeholder="e.g. St. Johns, Sellwood, Hood River"
                  aria-label="Neighborhood"
                  value={neighborhood}
                  onChange={(e) => setNeighborhood(e.target.value)}
                />
                <div className={styles.actions}>
                  <PrimaryButton type="submit" disabled={!neighborhood.trim()}>
                    Use this neighborhood
                  </PrimaryButton>
                </div>
              </form>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("install")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          ) : (
            <>
              <div className={styles.actions}>
                <PrimaryButton
                  onClick={requestLocation}
                  disabled={loc === "locating"}
                >
                  {loc === "locating" ? "locating…" : "Use my location"}
                </PrimaryButton>
              </div>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("install")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          )}
        </section>
      ) : null}

      {step === "install" ? (
        <section className={styles.card} aria-labelledby="welcome-install">
          <h1 id="welcome-install" className={styles.title}>
            Put Place on your home screen
          </h1>
          <p className={styles.lead}>
            Opens like an app, keeps Thursday&rsquo;s feed offline — and on
            iPhone it&rsquo;s the only way push can reach you.
          </p>

          {installed ? (
            <>
              <p className={styles.confirm} role="status">
                Already on your home screen.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("push")}>Next</PrimaryButton>
              </div>
            </>
          ) : install === "dismissed" ? (
            <>
              <p className={styles.fallback}>
                No worries — the browser works too. &ldquo;Install app&rdquo;
                lives in the browser menu whenever you want it.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("push")}>Next</PrimaryButton>
              </div>
            </>
          ) : installEvt || install === "prompting" ? (
            <>
              <div className={styles.actions}>
                <PrimaryButton
                  onClick={() => void promptInstall()}
                  disabled={install === "prompting"}
                >
                  {install === "prompting"
                    ? "waiting on the browser…"
                    : "Add to home screen"}
                </PrimaryButton>
              </div>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("push")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          ) : ios ? (
            <>
              <ol className={styles.steps}>
                <li>Tap Share in Safari&rsquo;s toolbar.</li>
                <li>Choose &ldquo;Add to Home Screen.&rdquo;</li>
                <li>Open Place from the new icon.</li>
              </ol>
              <p className={styles.metaNote}>
                iOS only delivers push to the installed app.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("push")}>Next</PrimaryButton>
              </div>
            </>
          ) : (
            <>
              <p className={styles.fallback}>
                This browser doesn&rsquo;t offer an install prompt here — look
                for &ldquo;Install app&rdquo; in its menu, or keep using the
                site. Nothing is locked behind the install.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("push")}>Next</PrimaryButton>
              </div>
            </>
          )}
        </section>
      ) : null}

      {step === "push" ? (
        <section className={styles.card} aria-labelledby="welcome-push">
          {/* The cadence promise, verbatim (UI-DRAFT-BRIEF §8) — 6pm is a
              clock time, so it wears .data like every measured value. */}
          <h1 id="welcome-push" className={styles.title}>
            One push a week, Sunday <span className="data">6pm</span>.
            That&rsquo;s the deal.
          </h1>
          <p className={styles.lead}>
            Two quick questions about where you went — never more. Save a
            place and we&rsquo;ll also tell you when its conditions fire.
          </p>

          {push === "on" ? (
            <>
              <p className={styles.confirm} role="status">
                You&rsquo;re on the Sunday cadence.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("done")}>Next</PrimaryButton>
              </div>
            </>
          ) : push === "denied" ? (
            <>
              <p className={styles.fallback}>
                That&rsquo;s okay — no pushes. The feed still refreshes every
                Thursday. Changed your mind later? Push lives in your
                browser&rsquo;s site settings.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("done")}>Next</PrimaryButton>
              </div>
            </>
          ) : push === "unsupported" ? (
            <>
              <p className={styles.fallback}>
                This browser can&rsquo;t do web push. The Thursday feed works
                everywhere all the same.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("done")}>Next</PrimaryButton>
              </div>
            </>
          ) : push === "failed" ? (
            <>
              <p className={styles.fallback} role="status">
                Couldn&rsquo;t finish subscribing — worth one more try.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => void enablePush()}>
                  Try again
                </PrimaryButton>
              </div>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("done")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          ) : pushNeedsInstall ? (
            <>
              <p className={styles.fallback}>
                On iPhone, push only reaches the Home-Screen app — add Place
                from the install step first.
              </p>
              <div className={styles.actions}>
                <PrimaryButton onClick={() => setStep("install")}>
                  Back to install
                </PrimaryButton>
              </div>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("done")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          ) : (
            <>
              <div className={styles.actions}>
                <PrimaryButton
                  onClick={() => void enablePush()}
                  disabled={push === "requesting" || push === "subscribing"}
                >
                  {push === "requesting"
                    ? "asking your browser…"
                    : push === "subscribing"
                      ? "subscribing…"
                      : "Turn on the Sunday push"}
                </PrimaryButton>
              </div>
              <div className={styles.quietRow}>
                <TertiaryButton onClick={() => setStep("done")}>
                  skip for now →
                </TertiaryButton>
              </div>
            </>
          )}
        </section>
      ) : null}

      {step === "done" ? (
        <section className={styles.card} aria-labelledby="welcome-done">
          <h1 id="welcome-done" className={styles.title}>
            You&rsquo;re set.
          </h1>
          <ul className={styles.recap}>
            <li className={styles.recapRow}>
              <span className={styles.recapKey}>feed</span>
              <span className={styles.recapVal}>
                {loc === "granted"
                  ? "ranking from where you are"
                  : loc === "set"
                    ? `starting near ${neighborhood.trim()}`
                    : "starting from Portland"}
              </span>
            </li>
            <li className={styles.recapRow}>
              <span className={styles.recapKey}>home screen</span>
              <span className={styles.recapVal}>
                {installed ? "installed" : "in the browser for now"}
              </span>
            </li>
            <li className={styles.recapRow}>
              <span className={styles.recapKey}>sunday push</span>
              <span className={styles.recapVal}>
                {push === "on" ? (
                  <>
                    on — Sunday <span className="data">6pm</span>
                  </>
                ) : (
                  "off for now"
                )}
              </span>
            </li>
          </ul>
          <div className={styles.actions}>
            {/* No trailing → on a filled primary — the arrow belongs to
                tertiaries/link-outs only (glyph canon; the verify page's
                receipt primary is the precedent). */}
            <PrimaryButton onClick={() => router.push("/")}>
              This weekend&rsquo;s feed
            </PrimaryButton>
          </div>
        </section>
      ) : null}
    </div>
  );
}
