"use client";

/* Surface 1 — the "This Weekend" feed (docs/02 §2), home route. Ranked
   experience cards within a drive-time polygon, each carrying a live,
   provenance-backed reason. The feed is public: only ♡ and the going
   sheet intercept to auth. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { FeedCard, FeedResponse } from "@/lib/types";
import { ApiError, addSave, getFeed, postEvent, removeSave } from "@/lib/api";
import {
  NEIGHBORHOOD_KEY,
  WELCOME_DONE_KEY,
  WELCOME_SEEN_KEY,
  clearPendingIntent,
  readLocal,
  writeLocal,
  writePendingIntent,
} from "@/lib/local";
import { TertiaryButton } from "@/components/Buttons";
import { ExperienceCard } from "@/components/ExperienceCard";
import { FeedFilters } from "@/components/FeedFilters";
import type { FeedFilterState } from "@/components/FeedFilters";
import { GoingSheet } from "@/components/GoingSheet";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import { Toast, errorToastCopy, useToast } from "@/components/Toast";
import styles from "./page.module.css";

/* Value before asks (docs/07): the feed is useful signed-out and
   unlocated. Portland is the default origin; geolocation fires only when
   the user taps "use my location". */
const PORTLAND = { lat: 45.512, lng: -122.658 };

/* Inverse of fmtDriveMinutes' stated heuristic (minutes ≈ km / 1.44):
   the drive-time filter becomes the API's radius_km. */
const KM_PER_DRIVE_MIN = 1.44;

const SAVE_PITCH =
  "A save is a standing query — sign in and we’ll watch conditions for it.";
const GOING_PITCH =
  "Sign in to declare the trip — we’ll check conditions before you go.";

type FeedStatus = "loading" | "ready" | "error";
type LocStatus = "idle" | "locating" | "granted" | "unavailable" | "manual";

export default function Home() {
  const router = useRouter();

  const [filters, setFilters] = useState<FeedFilterState>({
    verb: "",
    driveMin: 60,
    dogOk: false,
    kidOk: false,
  });
  const [debouncedVerb, setDebouncedVerb] = useState("");
  const [origin, setOrigin] = useState(PORTLAND);
  const [locStatus, setLocStatus] = useState<LocStatus>("idle");
  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [status, setStatus] = useState<FeedStatus>("loading");
  const [retryToken, setRetryToken] = useState(0);
  const [savedIds, setSavedIds] = useState<Set<string>>(() => new Set());
  const [goingCard, setGoingCard] = useState<FeedCard | null>(null);
  const [magicOpen, setMagicOpen] = useState(false);
  const [magicPitch, setMagicPitch] = useState<string | undefined>(undefined);
  /* Manual neighborhood fallback (state e): the name only labels the
     origin line — no geocoding endpoint exists yet (flagged API gap;
     shared with /welcome via NEIGHBORHOOD_KEY), so ranking stays on the
     Portland default until the backend can resolve it. */
  const [neighborhood, setNeighborhood] = useState<string | null>(null);
  const [neighborhoodDraft, setNeighborhoodDraft] = useState("");
  const [welcomeBanner, setWelcomeBanner] = useState(false);
  // §9 state (e): the shared toast treatment — never a per-page one-off.
  const { toast, showToast } = useToast();
  const savedDay = useRef<string | null>(null);
  const pendingSave = useRef<FeedCard | null>(null);
  const pendingGoing = useRef<(() => void) | null>(null);
  const reqSeq = useRef(0);

  useEffect(() => {
    setNeighborhood(readLocal(NEIGHBORHOOD_KEY));
    // First-run doorway to /welcome (decision 12): a one-time quiet line,
    // never a gate — dismissing it is as final as finishing onboarding.
    setWelcomeBanner(
      !readLocal(WELCOME_DONE_KEY) && !readLocal(WELCOME_SEEN_KEY),
    );
  }, []);

  // The typed verb filters the visible cards instantly; the API refetch
  // (activity param) trails it so keystrokes don't fan out into requests.
  useEffect(() => {
    const t = setTimeout(
      () => setDebouncedVerb(filters.verb.trim().toLowerCase()),
      300,
    );
    return () => clearTimeout(t);
  }, [filters.verb]);

  useEffect(() => {
    const reqId = ++reqSeq.current;
    // Cards already on screen stay up during a refetch; the skeleton only
    // renders when there is nothing honest to show yet.
    setStatus((s) => (s === "ready" ? s : "loading"));
    getFeed({
      lat: origin.lat,
      lng: origin.lng,
      radius_km: filters.driveMin * KM_PER_DRIVE_MIN,
      ...(debouncedVerb ? { activity: debouncedVerb } : {}),
      ...(filters.dogOk ? { dog_ok: true } : {}),
      ...(filters.kidOk ? { kid_ok: true } : {}),
    })
      .then((res) => {
        if (reqSeq.current !== reqId) return;
        setFeed(res);
        setStatus("ready");
      })
      .catch(() => {
        if (reqSeq.current !== reqId) return;
        // Degraded is a state, not a guess (docs/04 §4): drop stale ranks
        // rather than serve them as current.
        setFeed(null);
        setStatus("error");
      });
  }, [
    origin.lat,
    origin.lng,
    filters.driveMin,
    filters.dogOk,
    filters.kidOk,
    debouncedVerb,
    retryToken,
  ]);

  const requestLocation = () => {
    // The permission ask happens here, on tap — never on load.
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setLocStatus("manual");
      return;
    }
    setLocStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocStatus("granted");
      },
      // Denial fallback (state e): manual neighborhood entry, mirroring
      // /welcome's graceful path — never a silent dead end.
      () => setLocStatus("manual"),
      { timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const confirmNeighborhood = () => {
    const name = neighborhoodDraft.trim();
    if (!name) return;
    writeLocal(NEIGHBORHOOD_KEY, name);
    setNeighborhood(name);
    setLocStatus("unavailable");
  };

  const showSavedToast = () => {
    const day = savedDay.current;
    savedDay.current = null;
    if (!day) return;
    showToast(`Saved for ${day} — we’ll ask two quick questions Sunday evening.`);
  };

  const setSaved = (affordanceId: string, on: boolean) => {
    setSavedIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(affordanceId);
      else next.delete(affordanceId);
      return next;
    });
  };

  const attemptSave = async (card: FeedCard, isRetry: boolean) => {
    setSaved(card.affordance_id, true); // optimistic ♥
    try {
      await addSave({ affordance_id: card.affordance_id, kind: "want_to" });
      // A 401 earlier parked this intent for /auth/verify; the same-tab
      // retry just landed it — don't complete it twice.
      if (isRetry) clearPendingIntent();
    } catch (err) {
      setSaved(card.affordance_id, false);
      if (err instanceof ApiError && err.status === 401) {
        if (!isRetry) {
          // Feed is public; only ♡ intercepts to auth. The intent is kept
          // twice (decision 11): in-memory for the same-tab retry when the
          // sheet closes, and in storage for /auth/verify, which opens from
          // the email in a fresh tab.
          pendingSave.current = card;
          writePendingIntent({
            type: "save",
            affordance_id: card.affordance_id,
            kind: "want_to",
            place_name: card.place_name,
          });
          setMagicPitch(SAVE_PITCH);
          setMagicOpen(true);
        }
        // Post-auth retry still 401 ("Not now"): the ♥ reverts quietly —
        // the user already declined the sheet once.
        return;
      }
      // §9 state (e): tellable failures (404/409/422) share one toast
      // treatment; the ♥ has already reverted, so the copy is the residue.
      showToast(errorToastCopy(err, "Couldn’t save — try again."));
    }
  };

  const handleSave = (card: FeedCard) => {
    if (savedIds.has(card.affordance_id)) {
      setSaved(card.affordance_id, false);
      removeSave(card.affordance_id, "want_to").catch(() => {
        setSaved(card.affordance_id, true);
        // §9e: the ♥ is back; the shared toast says why.
        showToast("Couldn’t remove that save — try again.");
      });
    } else {
      void attemptSave(card, false);
    }
  };

  const handleMagicClose = () => {
    setMagicOpen(false);
    // Magic-link auth completes out of band; one retry on close either
    // lands the kept intent or reverts quietly — it never reopens the
    // sheet. Saves and trips are exclusive: only one intercepted at once.
    const pending = pendingSave.current;
    pendingSave.current = null;
    if (pending) void attemptSave(pending, true);
    const retryGoing = pendingGoing.current;
    pendingGoing.current = null;
    retryGoing?.();
  };

  const handleMore = (card: FeedCard) => {
    // Telemetry is fire-and-forget; navigation never waits on it.
    postEvent({
      affordance_id: card.affordance_id,
      etype: "card_open",
      now_score: card.now_score,
      conditions_snapshot: card.conditions,
    }).catch(() => {});
    router.push(`/places/${card.place_id}`);
  };

  const liveVerb = filters.verb.trim().toLowerCase();
  const cards = feed ? feed.cards : [];
  // The API (and the mock, which mirrors its filter semantics) narrows by
  // activity server-side after the 300ms debounce; the live verb also
  // narrows client-side so keystrokes filter instantly.
  const visible = liveVerb
    ? cards.filter((c) => c.activity_name.toLowerCase().includes(liveVerb))
    : cards;
  // The count line owns the honesty: once a client-side verb filter is
  // narrowing, the server count no longer describes what's shown.
  const count = liveVerb ? visible.length : feed ? feed.count : 0;

  return (
    <>
      <section className={styles.feedTop}>
        <h1 className={styles.title}>This Weekend</h1>
        <p className={styles.sub}>
          <span className={styles.liveDot} aria-hidden="true" />
          ranked by live conditions
        </p>
        <p className={styles.loc} aria-live="polite">
          <span>
            {locStatus === "granted"
              ? "near you"
              : neighborhood
                ? `near ${neighborhood}`
                : "near Portland"}
          </span>
          {locStatus === "idle" || locStatus === "locating" ? (
            <>
              <span aria-hidden="true">·</span>
              <button
                type="button"
                className={styles.locBtn}
                onClick={requestLocation}
                disabled={locStatus === "locating"}
              >
                {locStatus === "locating" ? "locating…" : "use my location"}
              </button>
            </>
          ) : locStatus === "unavailable" ? (
            <>
              <span aria-hidden="true">·</span>
              <span>location unavailable</span>
            </>
          ) : null}
        </p>
        {locStatus === "manual" ? (
          /* State (e): manual neighborhood entry. The name labels the
             origin honestly; ranking keeps the Portland default until a
             geocoding path exists (flagged API gap). */
          <form
            className={styles.locForm}
            onSubmit={(e) => {
              e.preventDefault();
              confirmNeighborhood();
            }}
          >
            <input
              className={styles.locField}
              type="text"
              name="neighborhood"
              autoComplete="off"
              autoCapitalize="words"
              spellCheck={false}
              placeholder="No problem — name a neighborhood"
              aria-label="Neighborhood"
              value={neighborhoodDraft}
              onChange={(e) => setNeighborhoodDraft(e.target.value)}
            />
            <button
              type="submit"
              className={styles.locBtn}
              disabled={!neighborhoodDraft.trim()}
            >
              use it
            </button>
          </form>
        ) : null}
        <div className={styles.filters}>
          <FeedFilters value={filters} onChange={setFilters} />
        </div>
      </section>

      {welcomeBanner ? (
        /* First-run doorway to /welcome (decision 12): one quiet line,
           dismissible forever, never gating the feed below it. */
        <div className={styles.welcomeLine}>
          <span className={styles.welcomeCopy}>New here?</span>
          <TertiaryButton href="/welcome">set up Place →</TertiaryButton>
          <button
            type="button"
            className={styles.welcomeDismiss}
            onClick={() => {
              writeLocal(WELCOME_SEEN_KEY, new Date().toISOString());
              setWelcomeBanner(false);
            }}
          >
            dismiss
          </button>
        </div>
      ) : null}

      {status === "error" ? (
        <div className={styles.degraded} role="status">
          <p className={styles.degradedLead}>
            <span className={styles.degradedGlyph} aria-hidden="true">
              ○
            </span>
            live conditions unavailable
          </p>
          <div className={styles.degradedAction}>
            <TertiaryButton onClick={() => setRetryToken((t) => t + 1)}>
              retry
            </TertiaryButton>
          </div>
        </div>
      ) : feed === null ? (
        <div
          className={styles.skStack}
          role="status"
          aria-label="Checking live conditions"
        >
          {[0, 1, 2].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className={styles.empty}>
          {liveVerb ? (
            /* State (d): a narrowing verb owns its emptiness — show the
               active chip with a clear affordance so "nothing worth the
               drive" is never silently a filter artifact. */
            <p className={styles.emptyFilter}>
              <span className={styles.emptyChip}>{liveVerb}</span>
              <button
                type="button"
                className={styles.emptyClear}
                onClick={() => setFilters({ ...filters, verb: "" })}
              >
                clear
              </button>
            </p>
          ) : null}
          <p className={styles.emptyLead}>
            Nothing worth the drive this weekend.
          </p>
          <p className={styles.emptySub}>We’d rather say so.</p>
        </div>
      ) : (
        <>
          <p className={styles.count}>
            <span className="data">{count}</span>{" "}
            {count === 1 ? "place" : "places"} worth it this weekend
          </p>
          <div className={styles.stack}>
            {visible.map((card) => (
              <ExperienceCard
                key={card.affordance_id}
                card={card}
                saved={savedIds.has(card.affordance_id)}
                onSave={() => handleSave(card)}
                onGoing={() => setGoingCard(card)}
                onMore={() => handleMore(card)}
              />
            ))}
          </div>
        </>
      )}

      {status === "ready" ? (
        /* Quiet tertiary doorway to the public ranker — an acquisition/SEO
           surface, so nothing louder than a footer line (task: decision 1,
           quiet chrome only). */
        <div className={styles.footLink}>
          <TertiaryButton href="/waterfalls">
            Gorge waterfalls by current flow →
          </TertiaryButton>
        </div>
      ) : null}

      {goingCard !== null && (
        <GoingSheet
          card={goingCard}
          open
          onClose={() => {
            setGoingCard(null);
            // State (d): the saved-for-Sunday confirmation outlives the
            // sheet as a short toast residue on the feed.
            showSavedToast();
          }}
          onAuthNeeded={(retry) => {
            pendingGoing.current = retry;
            setMagicPitch(GOING_PITCH);
            setMagicOpen(true);
          }}
          onSaved={(day) => {
            savedDay.current = day;
          }}
        />
      )}
      <MagicLinkSheet
        pitch={magicPitch}
        open={magicOpen}
        onClose={handleMagicClose}
      />
      <Toast message={toast} />
    </>
  );
}

/* Loading respects the card anatomy — identity, provenance rows, strip,
   two actions — never a bare spinner. */
function SkeletonCard() {
  return (
    <article className={styles.skCard} aria-hidden="true">
      <div className={styles.skIdentity}>
        <div className={styles.skIdMain}>
          <div className={`${styles.skBar} ${styles.skTitle}`} />
          <div className={`${styles.skBar} ${styles.skContext}`} />
        </div>
        <div className={`${styles.skBar} ${styles.skDrive}`} />
      </div>
      <div className={styles.skProvRow}>
        <div className={styles.skGlyph} />
        <div>
          <div className={`${styles.skBar} ${styles.skLead}`} />
          <div className={`${styles.skBar} ${styles.skDetail}`} />
        </div>
      </div>
      <div className={styles.skProvRow}>
        <div className={styles.skGlyph} />
        <div>
          <div className={`${styles.skBar} ${styles.skLeadShort}`} />
        </div>
      </div>
      <div className={`${styles.skBar} ${styles.skStrip}`} />
      <div className={styles.skActions}>
        <div className={styles.skPrimary} />
        <div className={`${styles.skBar} ${styles.skTertiary}`} />
      </div>
    </article>
  );
}
