"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  addSave,
  getPlace,
  listSaves,
  postVerdict,
  removeSave,
} from "@/lib/api";
import type {
  AffordanceDetail,
  PlacePage,
  ProvenanceReading,
  SaveKind,
  WindowOut,
} from "@/lib/types";
import { fmtAsOf, fmtVerified, staleAsOf, windowGlyph, withData } from "@/lib/format";
import { writePendingIntent } from "@/lib/local";
import { AffordanceStrip } from "@/components/AffordanceStrip";
import { TertiaryButton } from "@/components/Buttons";
import { ClaimRow } from "@/components/ClaimRow";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import { NearbyAfter, type NearbyItem } from "@/components/NearbyAfter";
import { PlacePageHeader } from "@/components/PlacePageHeader";
import { SafetyLine } from "@/components/SafetyLine";
import { Toast, errorToastCopy, useToast } from "@/components/Toast";
import type { UiVerdict } from "@/components/VerdictControls";
import styles from "./place.module.css";

/* Leave No Trace rides every foot (docs/02 §5.4). The per-place permit
   copy (Northwest Forest Pass, Multnomah timed-use) rides SafetyLine's
   permit slot via PlacePage.permit_note — a client-proposed field the API
   doesn't serve yet (flagged gap in lib/types.ts). */
const STEWARDSHIP = "pack it out";

// Canon auth pitch for the save intercept (UI-DRAFT-BRIEF §7).
const SAVE_PITCH = "We’ll tell you when it’s flowing hard.";

/* PAIRS_WITH endpoint does not exist yet (UI-DRAFT-BRIEF gap 16) — canon
   fixture pairing until the API serves nearby-after. */
const NEARBY_ITEMS: NearbyItem[] = [
  { name: "Steeplejack Brewing", type: "brewery", minutes: 12 },
];

const DAY_NAMES = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];
const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const STATE_WORDS: Record<WindowOut["state"], string> = {
  true: "open",
  false: "closed",
  unknown: "unknown",
};

/* "opened Tuesday" copy for window state_since (API cheat sheet). Calendar-
   day math mirrors format.ts's private calendarDaysAgo. Dates stay in the UI
   font — they are copy, not sensor readings. */
function sinceCopy(state: WindowOut["state"], iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const days = Math.round(
    (new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() -
      new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) /
      86_400_000,
  );
  let when: string;
  if (days <= 0) when = "today";
  else if (days === 1) when = "yesterday";
  else if (days < 7) when = DAY_NAMES[d.getDay()];
  else when = `${MONTH_NAMES[d.getMonth()]} ${d.getDate()}`;
  if (state === "true") return `opened ${when}`;
  if (state === "false") return `closed ${when}`;
  return `unknown since ${when}`;
}

// One quiet line per evaluator reading; withData picks up the station id,
// the value+unit, and the as-of clock time.
function readingLine(r: ProvenanceReading): string {
  const src = [r.provider, r.station_ref].filter(Boolean).join(" ") || r.feed_id;
  const value =
    r.value != null ? `${r.value}${r.unit ? ` ${r.unit}` : ""}` : null;
  const parts = [src];
  if (r.parameter) parts.push(value ? `${r.parameter} ${value}` : r.parameter);
  else if (value) parts.push(value);
  if (r.observed_at) parts.push(fmtAsOf(r.observed_at));
  return parts.join(" · ");
}

type Tone = "isLive" | "isFading" | "isUnknown";

function toneOf(w: WindowOut): Tone {
  if (w.live) return w.live.fresh ? "isLive" : "isFading";
  // No live reason but a determined state: the evaluator's last word is
  // still knowledge — a known-open seasonal window renders live-toned with
  // its filled ● (the Dog Mountain seasonal-prior precedent), never in
  // unknown basalt. Only a genuinely unknown state gets ○ + basalt; stale
  // tends toward unknown, never toward false (docs/04 §4).
  return w.state === "unknown" ? "isUnknown" : "isLive";
}

function conditionLead(w: WindowOut): string {
  if (w.live) return w.live.text;
  const wtype = w.wtype.replace(/_/g, " ");
  if (w.state === "true") return `Open — ${wtype}`;
  if (w.state === "false") return `Closed — ${wtype}`;
  return `Live ${wtype} unavailable`;
}

/* VerdictOut.conditions_snapshot arrives as {discharge_cfs: 990, temp_f: 82};
   the key suffix carries the unit. Unknown suffixes render the bare value —
   never an invented unit. */
const SNAPSHOT_UNITS: [string, string][] = [
  ["_cfs", " cfs"],
  ["_f", "°F"],
  ["_c", "°C"],
  ["_in", " in"],
  ["_ft", " ft"],
  ["_mm", " mm"],
  ["_pct", "%"],
  ["_min", " min"],
];

function fmtSnapshot(snapshot: Record<string, unknown>): string | null {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(snapshot)) {
    if (typeof value !== "number" && typeof value !== "string") continue;
    const unit = SNAPSHOT_UNITS.find(([suffix]) => key.endsWith(suffix));
    parts.push(unit ? `${value}${unit[1]}` : String(value));
  }
  return parts.length > 0 ? parts.join(", ") : null;
}

type VerdictNote = { mark?: string; tone?: "ok" | "re" | "ch"; text: string };

function AffordanceSection({
  aff,
  open,
  onToggle,
  answers,
  notes,
  refreshed,
  permit,
  onVerdict,
}: {
  aff: AffordanceDetail;
  open: boolean;
  onToggle: () => void;
  answers: Record<string, UiVerdict>;
  notes: Record<string, VerdictNote>;
  refreshed: Record<string, number>;
  permit: string | null;
  onVerdict: (
    claimId: string,
    apiVerdict: "confirm" | "refute" | "changed",
  ) => Promise<void>;
}) {
  // The gate window is the affordance's current-state authority; otherwise
  // the first window carrying a live reason, otherwise the first window.
  const primary =
    aff.windows.find((w) => w.is_gate) ??
    aff.windows.find((w) => w.live !== null) ??
    aff.windows[0];

  /* Shared staleAsOf (§9 state c): the server may have composed
     "(as of …)" into live.text already — stamp once, never twice
     (ProvenanceLine parity across feed/place/ranker). */
  const primaryStamp = primary?.live ? staleAsOf(primary.live) : null;

  return (
    <section className={styles.affordance}>
      <AffordanceStrip
        activityName={aff.activity_name}
        difficulty={aff.difficulty}
        typicalDurationMin={aff.typical_duration_min}
        dogOk={aff.dog_ok}
        kidOk={aff.kid_ok}
      />

      {primary ? (
        <div className={`${styles.condition} ${styles[toneOf(primary)]}`}>
          <span className={styles.glyph} aria-hidden="true">
            {windowGlyph(primary.state)}
          </span>
          <div>
            <p className={styles.lead}>
              {withData(conditionLead(primary))}
              {primaryStamp ? (
                <>
                  {" — "}
                  {withData(primaryStamp)}
                </>
              ) : null}
            </p>
            {primary.live?.source ? (
              <p className={styles.src}>{withData(primary.live.source)}</p>
            ) : null}
          </div>
        </div>
      ) : !aff.last_verified_at ? (
        <p className={styles.fallback}>
          From community reports · not yet verified
        </p>
      ) : null}

      {aff.last_verified_at ? (
        <div className={styles.credit}>
          <span className={`${styles.glyph} ${styles.check}`} aria-hidden="true">
            ✓
          </span>
          <p className={styles.creditText}>
            {withData(fmtVerified(aff.last_verified_at))}
            {aff.verified_by ? (
              <>
                {" by "}
                <span className={styles.verifier}>
                  @{aff.verified_by.replace(/^@/, "")}
                </span>
              </>
            ) : null}
          </p>
        </div>
      ) : null}

      {aff.windows.length > 0 ? (
        <div className={styles.moreRow}>
          <TertiaryButton onClick={onToggle}>
            {open ? "hide conditions" : "more conditions →"}
          </TertiaryButton>
        </div>
      ) : null}

      {open ? (
        <div className={styles.windows}>
          {aff.windows.map((w) => (
            <div key={w.window_id} className={styles[toneOf(w)]}>
              <p className={styles.windowHead}>
                <span className={styles.glyph} aria-hidden="true">
                  {windowGlyph(w.state)}
                </span>{" "}
                {w.wtype.replace(/_/g, " ")}
                {w.is_gate ? (
                  <span className={styles.gateMark}> · gate</span>
                ) : null}
              </p>
              <p className={styles.windowMeta}>
                {STATE_WORDS[w.state]}
                {w.state_since ? ` · ${sinceCopy(w.state, w.state_since)}` : null}
              </p>
              {w.live && w.live.provenance.length > 0 ? (
                <ul className={styles.readings}>
                  {w.live.provenance.map((r) => (
                    <li key={r.feed_id}>{withData(readingLine(r))}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {aff.claims.length > 0 ? (
        <div className={styles.claims}>
          {aff.claims.map((claim) => {
            const note = notes[claim.id];
            /* State (f): a verdict visually refreshes the claim — the
               VerdictOut confidence (and a reset decay clock) replace the
               served values, so a "needs a fresh look" chip clears the
               moment someone verifies (UI-DRAFT-BRIEF §2). */
            const fresh = refreshed[claim.id];
            const shown =
              fresh !== undefined
                ? {
                    ...claim,
                    confidence: fresh,
                    last_evidence_at: new Date().toISOString(),
                  }
                : claim;
            return (
              <div key={claim.id} className={styles.claimItem}>
                <ClaimRow
                  claim={shown}
                  answered={answers[claim.id] ?? null}
                  onVerdict={onVerdict}
                />
                {note ? (
                  <p className={styles.note}>
                    {note.mark && note.tone ? (
                      <span className={`${styles.noteMark} ${styles[note.tone]}`}>
                        {note.mark}
                      </span>
                    ) : null}
                    <span>{withData(note.text)}</span>
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      <div className={styles.foot}>
        {/* Hazard is pre-gated server-side: assumption_of_risk arrives only
            when both publication gates passed. Suppressed hazard affordances
            are acknowledged by name at page level (see PlaceRoute). */}
        <SafetyLine
          assumptionOfRisk={aff.assumption_of_risk}
          permit={permit}
          stewardship={STEWARDSHIP}
        />
      </div>
    </section>
  );
}

export default function PlaceClient({ id }: { id: string }) {
  const [place, setPlace] = useState<PlacePage | null>(null);
  const [failure, setFailure] = useState<"missing" | "error" | null>(null);
  const [attempt, setAttempt] = useState(0);
  /* Kind → the affordance actually carrying the save. Saves are
     affordance-scoped in the API while the header triplet is
     place-scoped (model gap): a feed ♥ can land on a non-lead
     affordance, and removal must DELETE that same save — deleting
     against the lead would 404 ("This place isn't available." on a
     page that plainly is) and leave the kind un-removable here. */
  const [savedBy, setSavedBy] = useState<Map<SaveKind, string>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [answers, setAnswers] = useState<Record<string, UiVerdict>>({});
  const [notes, setNotes] = useState<Record<string, VerdictNote>>({});
  const [refreshed, setRefreshed] = useState<Record<string, number>>({});
  const [noted, setNoted] = useState<Set<string>>(new Set());
  const [authOpen, setAuthOpen] = useState(false);
  const [authPitch, setAuthPitch] = useState<string | undefined>(undefined);
  // §9 state (e): the shared toast treatment — never a per-page one-off.
  const { toast, showToast } = useToast();
  /* A verdict that hit a 401 is kept and retried once when the auth sheet
     closes — the intent resumes, the user never re-taps (decision 11;
     app/page.tsx save-retry idiom). */
  const pendingVerdict = useRef<{
    claimId: string;
    apiVerdict: "confirm" | "refute" | "changed";
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPlace(null);
    setFailure(null);
    getPlace(id).then(
      (p) => {
        if (!cancelled) setPlace(p);
      },
      (err: unknown) => {
        if (cancelled) return;
        setFailure(
          err instanceof ApiError && err.status === 404 ? "missing" : "error",
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  useEffect(() => {
    if (!place) return;
    let cancelled = false;
    const here = new Set(place.affordances.map((a) => a.affordance_id));
    listSaves().then(
      (saves) => {
        if (cancelled) return;
        // First save wins per kind; several same-kind saves across this
        // place's affordances stay a /saves concern (it scopes per row).
        const byKind = new Map<SaveKind, string>();
        for (const s of saves) {
          if (s.place_id !== place.id && !here.has(s.affordance_id)) continue;
          if (!byKind.has(s.kind)) byKind.set(s.kind, s.affordance_id);
        }
        setSavedBy(byKind);
      },
      () => {
        /* signed-out: the triplet starts empty; the first tap intercepts */
      },
    );
    return () => {
      cancelled = true;
    };
  }, [place]);

  const toggleSave = (kind: SaveKind) => {
    if (!place || place.affordances.length === 0) return;
    // A NEW save lands on the lead affordance (model gap, savedBy note);
    // removal targets whichever affordance the read side found it on.
    const held = savedBy.get(kind);
    const affordanceId = held ?? place.affordances[0].affordance_id;
    const had = held !== undefined;
    setSavedBy((prev) => {
      const next = new Map(prev);
      if (had) next.delete(kind);
      else next.set(kind, affordanceId);
      return next;
    });
    const call = had
      ? removeSave(affordanceId, kind)
      : addSave({ affordance_id: affordanceId, kind });
    call.catch((err: unknown) => {
      setSavedBy((prev) => {
        const next = new Map(prev);
        if (had) next.set(kind, affordanceId);
        else next.delete(kind);
        return next;
      });
      if (err instanceof ApiError && err.status === 401) {
        // The magic link opens in a fresh tab — the interrupted save must
        // survive in storage for /auth/verify to finish (decision 11).
        if (!had) {
          writePendingIntent({
            type: "save",
            affordance_id: affordanceId,
            kind,
            place_name: place.name,
          });
        }
        setAuthPitch(SAVE_PITCH);
        setAuthOpen(true);
      } else {
        // §9 state (e): tellable failures share one toast treatment; the
        // triplet has already reverted, so the copy is the only residue.
        showToast(errorToastCopy(err, "Couldn’t save — try again."));
      }
    });
  };

  const toggleExpanded = (affordanceId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(affordanceId)) next.delete(affordanceId);
      else next.add(affordanceId);
      return next;
    });
  };

  const handleVerdict = async (
    claimId: string,
    apiVerdict: "confirm" | "refute" | "changed",
    isRetry = false,
  ): Promise<void> => {
    // UI copy says deny; the wire says refute — never displayed.
    const ui: UiVerdict = apiVerdict === "refute" ? "deny" : apiVerdict;
    try {
      const out = await postVerdict({ claim_id: claimId, verdict: apiVerdict });
      setAnswers((prev) => ({ ...prev, [claimId]: ui }));
      // State (f): the new confidence refreshes the row for everyone.
      setRefreshed((prev) => ({ ...prev, [claimId]: out.confidence }));
      if (ui === "confirm") {
        const snap = fmtSnapshot(out.conditions_snapshot);
        setNotes((prev) => ({
          ...prev,
          [claimId]: {
            mark: "✓",
            tone: "ok",
            text: snap
              ? `Thanks — logged with conditions at ${snap}`
              : "Thanks — logged with today’s conditions",
          },
        }));
      } else {
        // No deny/changed glyph exists in the single set (✕ and ~ don't,
        // and ● is reserved for "other live") — the receipt is quiet text.
        setNotes((prev) => ({
          ...prev,
          [claimId]: { text: "Noted — this claim gets re-checked" },
        }));
      }
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        // One verdict per trip per 24h — lock the row, honest receipt.
        setAnswers((prev) => ({ ...prev, [claimId]: ui }));
        setNotes((prev) => ({
          ...prev,
          [claimId]: { text: "Already logged this week ✓" },
        }));
      } else if (!isRetry && err instanceof ApiError && err.status === 401) {
        // The verdict survives the interception and retries once when the
        // auth sheet closes (decision 11) — never re-tapped, never looped.
        pendingVerdict.current = { claimId, apiVerdict };
        setAuthPitch(undefined);
        setAuthOpen(true);
      } else {
        // §9e copy source shared with the toasts (404/422); the receipt
        // renders inline because it belongs beside the tapped control.
        setNotes((prev) => ({
          ...prev,
          [claimId]: { text: errorToastCopy(err, "Couldn’t log that — try again.") },
        }));
      }
    }
  };

  const handleAuthClose = () => {
    setAuthOpen(false);
    // Magic-link auth completes out of band; one retry on close either
    // lands the kept verdict or settles into the quiet retry note.
    const pending = pendingVerdict.current;
    pendingVerdict.current = null;
    if (pending) void handleVerdict(pending.claimId, pending.apiVerdict, true);
  };

  if (failure === "missing") {
    return (
      <div className={styles.page}>
        <div className={styles.notice}>
          <p className={styles.noticeLead}>This place isn’t available.</p>
          <div className={styles.moreRow}>
            <TertiaryButton href="/">back to the feed →</TertiaryButton>
          </div>
        </div>
      </div>
    );
  }

  if (failure === "error") {
    return (
      <div className={styles.page}>
        <div className={styles.notice}>
          <p className={styles.noticeLead}>Couldn’t load this place.</p>
          <div className={styles.moreRow}>
            <TertiaryButton onClick={() => setAttempt((n) => n + 1)}>
              try again →
            </TertiaryButton>
          </div>
        </div>
      </div>
    );
  }

  if (!place) {
    /* §9 state (f): loading respects the surface anatomy — header (name /
       kind / save triplet), then affordance sections with the 22px-gutter
       condition row and claim lines. Never a spinner-only screen. */
    return (
      <div className={styles.page} role="status" aria-label="Loading this place">
        <article className={`${styles.surface} ${styles.skSurface}`} aria-hidden="true">
          <div className={styles.skHeader}>
            <div className={`${styles.skBar} ${styles.skName}`} />
            <div className={`${styles.skBar} ${styles.skKind}`} />
            <div className={styles.skTriplet}>
              <div className={styles.skDot} />
              <div className={styles.skDot} />
              <div className={styles.skDot} />
            </div>
          </div>
          {[0, 1].map((i) => (
            <div key={i} className={styles.skSection}>
              <div className={`${styles.skBar} ${styles.skStrip}`} />
              <div className={styles.skCondRow}>
                <div className={styles.skGlyph} />
                <div>
                  <div className={`${styles.skBar} ${styles.skLead}`} />
                  <div className={`${styles.skBar} ${styles.skSrc}`} />
                </div>
              </div>
              <div className={`${styles.skBar} ${styles.skClaim}`} />
              {i === 0 ? (
                <div className={`${styles.skBar} ${styles.skClaimShort}`} />
              ) : null}
            </div>
          ))}
        </article>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <article className={styles.surface}>
        <PlacePageHeader
          place={place}
          savedKinds={new Set(savedBy.keys())}
          onToggleSave={toggleSave}
        />

        <h2 className={styles.sectionHead}>What you can do here</h2>

        {place.affordances.map((aff) => (
          <AffordanceSection
            key={aff.affordance_id}
            aff={aff}
            open={expanded.has(aff.affordance_id)}
            onToggle={() => toggleExpanded(aff.affordance_id)}
            answers={answers}
            notes={notes}
            refreshed={refreshed}
            permit={place.permit_note ?? null}
            onVerdict={handleVerdict}
          />
        ))}

        {/* State (b): hazard affordances the server pre-gated out are
            acknowledged by name, never rendered as if they don't exist —
            honesty about suppression is part of the hazard posture
            (docs/02 §5.1; canon copy verbatim). */}
        {(place.suppressed_hazards ?? []).map((h) => (
          <section
            key={h.activity_name}
            className={styles.suppressed}
            aria-label={`${h.activity_name} — not shown`}
          >
            <p className={styles.suppressedName}>
              <span className={styles.suppressedGlyph} aria-hidden="true">
                ○
              </span>
              {h.activity_name}
            </p>
            <p className={styles.suppressedNote}>
              Not shown — needs a recent verification and a live trigger.
            </p>
          </section>
        ))}

        <div className={styles.directions}>
          {/* The committed last-mile hand-off — Place never does navigation
              (UI-DRAFT-BRIEF decision 14). */}
          <TertiaryButton
            href={`https://www.google.com/maps/dir/?api=1&destination=${place.lat},${place.lng}`}
          >
            Directions →
          </TertiaryButton>
        </div>
      </article>

      <NearbyAfter
        items={NEARBY_ITEMS}
        noted={noted}
        onNote={(name) => setNoted((prev) => new Set(prev).add(name))}
      />

      <MagicLinkSheet
        pitch={authPitch}
        open={authOpen}
        onClose={handleAuthClose}
      />
      <Toast message={toast} />
    </div>
  );
}
