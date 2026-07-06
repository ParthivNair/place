"use client";

/* Surface 1 — the "This Weekend" feed (docs/02 §2), home route. Ranked
   experience cards within a drive-time polygon, each carrying a live,
   provenance-backed reason. The feed is public: only ♡ and the going
   sheet intercept to auth. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { FeedCard, FeedResponse } from "@/lib/types";
import { ApiError, addSave, getFeed, postEvent, removeSave } from "@/lib/api";
import { TertiaryButton } from "@/components/Buttons";
import { ExperienceCard } from "@/components/ExperienceCard";
import { FeedFilters } from "@/components/FeedFilters";
import type { FeedFilterState } from "@/components/FeedFilters";
import { GoingSheet } from "@/components/GoingSheet";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
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
type LocStatus = "idle" | "locating" | "granted" | "unavailable";

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
  const pendingSave = useRef<FeedCard | null>(null);
  const reqSeq = useRef(0);

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
      setLocStatus("unavailable");
      return;
    }
    setLocStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocStatus("granted");
      },
      () => setLocStatus("unavailable"),
      { timeout: 10_000, maximumAge: 300_000 },
    );
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
    } catch (err) {
      setSaved(card.affordance_id, false);
      if (!isRetry && err instanceof ApiError && err.status === 401) {
        // Feed is public; only ♡ intercepts to auth. The intent is kept
        // and retried once when the sheet closes.
        pendingSave.current = card;
        setMagicPitch(SAVE_PITCH);
        setMagicOpen(true);
      }
    }
  };

  const handleSave = (card: FeedCard) => {
    if (savedIds.has(card.affordance_id)) {
      setSaved(card.affordance_id, false);
      removeSave(card.affordance_id, "want_to").catch(() =>
        setSaved(card.affordance_id, true),
      );
    } else {
      void attemptSave(card, false);
    }
  };

  const handleMagicClose = () => {
    setMagicOpen(false);
    const pending = pendingSave.current;
    pendingSave.current = null;
    // Magic-link auth completes out of band; one retry on close either
    // lands the save or reverts quietly — it never reopens the sheet.
    if (pending) void attemptSave(pending, true);
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
  // The API filters by activity server-side; mock mode ignores params, so
  // the verb also narrows client-side on activity_name substring.
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
          <span>{locStatus === "granted" ? "near you" : "near Portland"}</span>
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
        <div className={styles.filters}>
          <FeedFilters value={filters} onChange={setFilters} />
        </div>
      </section>

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

      {goingCard !== null && (
        <GoingSheet
          card={goingCard}
          open
          onClose={() => setGoingCard(null)}
          onAuthNeeded={() => {
            setMagicPitch(GOING_PITCH);
            setMagicOpen(true);
          }}
        />
      )}
      <MagicLinkSheet
        pitch={magicPitch}
        open={magicOpen}
        onClose={handleMagicClose}
      />
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
