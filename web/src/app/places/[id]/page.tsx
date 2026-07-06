"use client";

import { use, useEffect, useState, type ReactNode } from "react";
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
import { fmtAsOf, fmtVerified, windowGlyph } from "@/lib/format";
import { AffordanceStrip } from "@/components/AffordanceStrip";
import { TertiaryButton } from "@/components/Buttons";
import { ClaimRow } from "@/components/ClaimRow";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import { NearbyAfter, type NearbyItem } from "@/components/NearbyAfter";
import { PlacePageHeader } from "@/components/PlacePageHeader";
import { SafetyLine } from "@/components/SafetyLine";
import type { UiVerdict } from "@/components/VerdictControls";
import styles from "./place.module.css";

/* .data wrapping for measured values — duplicated from ProvenanceLine, which
   does not export withData and is owned by another surface. Same rules: unit-
   bearing numbers, comparator thresholds, ranges, clock times, 5+-digit
   station ids; no lookbehind (Safari < 16.4 throws at construction). */
const NUM = "[−-]?\\d[\\d,.]*";
const RANGE = `${NUM}(?:\\s?[–—-]\\s?${NUM})?`;
const UNIT =
  "(?:cfs|°[cf]|ft|in|mi|km|mm|cm|hours?|hrs?|h|min(?:ute)?s?|days?|weeks?|%)";
const MEASURE = new RegExp(
  [
    `[<>≤≥~]\\s?${RANGE}(?:\\s?${UNIT})?(?![a-z0-9])`,
    `${RANGE}\\s?${UNIT}(?![a-z0-9])`,
    `\\d{1,2}:\\d{2}(?:\\s?(?:am|pm))?`,
    `\\d{1,2}\\s?(?:am|pm)(?![a-z0-9])`,
    `\\d{5,}`,
  ].join("|"),
  "gi",
);

function withData(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MEASURE)) {
    const start = match.index ?? 0;
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      <span key={start} className="data">
        {match[0]}
      </span>,
    );
    cursor = start + match[0].length;
  }
  if (cursor === 0) return text;
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

/* Leave No Trace rides every foot (docs/02 §5.4). Per-place permit strings
   (Northwest Forest Pass, Multnomah timed-use) cannot render yet: PlacePage
   serves no permit field (UI-DRAFT-BRIEF cheat sheet) — SafetyLine's permit
   slot stays empty until the API grows one. */
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
  // No live reason → seasonal prior only; stale tends toward unknown (○),
  // never toward false (docs/04 §4).
  return "isUnknown";
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
  onVerdict,
}: {
  aff: AffordanceDetail;
  open: boolean;
  onToggle: () => void;
  answers: Record<string, UiVerdict>;
  notes: Record<string, VerdictNote>;
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
              {primary.live && !primary.live.fresh && primary.live.as_of ? (
                <>
                  {" — "}
                  {withData(fmtAsOf(primary.live.as_of))}
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
            {fmtVerified(aff.last_verified_at)}
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
            return (
              <div key={claim.id} className={styles.claimItem}>
                <ClaimRow
                  claim={claim}
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
            when both publication gates passed; absent hazard affordances
            simply are not in the payload — no client gating. */}
        <SafetyLine
          assumptionOfRisk={aff.assumption_of_risk}
          stewardship={STEWARDSHIP}
        />
      </div>
    </section>
  );
}

export default function PlaceRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  const [place, setPlace] = useState<PlacePage | null>(null);
  const [failure, setFailure] = useState<"missing" | "error" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [savedKinds, setSavedKinds] = useState<Set<SaveKind>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [answers, setAnswers] = useState<Record<string, UiVerdict>>({});
  const [notes, setNotes] = useState<Record<string, VerdictNote>>({});
  const [noted, setNoted] = useState<Set<string>>(new Set());
  const [authOpen, setAuthOpen] = useState(false);
  const [authPitch, setAuthPitch] = useState<string | undefined>(undefined);

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
        setSavedKinds(
          new Set(
            saves
              .filter((s) => s.place_id === place.id || here.has(s.affordance_id))
              .map((s) => s.kind),
          ),
        );
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
    // Saves are affordance-scoped in the API while the header triplet is
    // place-scoped — the lead affordance carries the save (model gap).
    const affordanceId = place.affordances[0].affordance_id;
    const had = savedKinds.has(kind);
    setSavedKinds((prev) => {
      const next = new Set(prev);
      if (had) next.delete(kind);
      else next.add(kind);
      return next;
    });
    const call = had
      ? removeSave(affordanceId, kind)
      : addSave({ affordance_id: affordanceId, kind });
    call.catch((err: unknown) => {
      setSavedKinds((prev) => {
        const next = new Set(prev);
        if (had) next.add(kind);
        else next.delete(kind);
        return next;
      });
      if (err instanceof ApiError && err.status === 401) {
        setAuthPitch(SAVE_PITCH);
        setAuthOpen(true);
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
  ): Promise<void> => {
    // UI copy says deny; the wire says refute — never displayed.
    const ui: UiVerdict = apiVerdict === "refute" ? "deny" : apiVerdict;
    try {
      const out = await postVerdict({ claim_id: claimId, verdict: apiVerdict });
      setAnswers((prev) => ({ ...prev, [claimId]: ui }));
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
        setNotes((prev) => ({
          ...prev,
          [claimId]: {
            mark: ui === "deny" ? "●" : "~",
            tone: ui === "deny" ? "re" : "ch",
            text: "Noted — this claim gets re-checked",
          },
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
      } else if (err instanceof ApiError && err.status === 401) {
        setAuthPitch(undefined);
        setAuthOpen(true);
      } else {
        setNotes((prev) => ({
          ...prev,
          [claimId]: { text: "Couldn’t log that — try again." },
        }));
      }
    }
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
    return (
      <div className={styles.page} aria-busy="true">
        <div className={styles.skeleton}>
          <span className={`${styles.bar} ${styles.barWide}`} />
          <span className={`${styles.bar} ${styles.barMid}`} />
          <span className={`${styles.bar} ${styles.barFull}`} />
          <span className={`${styles.bar} ${styles.barMid}`} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <article className={styles.surface}>
        <PlacePageHeader
          place={place}
          savedKinds={savedKinds}
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
            onVerdict={handleVerdict}
          />
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
        onClose={() => setAuthOpen(false)}
      />
    </div>
  );
}
