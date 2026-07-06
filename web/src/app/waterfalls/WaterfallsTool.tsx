"use client";

/* Surface 4 — the seasonal ranker (docs/02 §4, UI-DRAFT-BRIEF §4):
   "Gorge waterfalls, ranked by current flow", public launch #1, posted to
   r/Portland on the first big October rain. Free, no login, structurally
   ten ranked rows — never one pin (docs/02 §5.5) — each carrying its live
   flow driver, drive time, and provenance line (no bare ranks, docs/02
   §2). The ♥ is the tool's only conversion ask: heart → email capture →
   standing query (tool → save → alert → feed).

   No ranker endpoint exists yet: rows come from lib/waterfallsRanker
   fixtures (flagged API gap). States (a) big-rain / (b) dry-spell switch
   on the fixture's RANKER_SCENARIO constant — never a user-visible
   toggle. */

import { useEffect, useRef, useState } from "react";
import type { ReasonOut } from "@/lib/types";
import { ASSUMPTION_OF_RISK } from "@/lib/types";
import { fmtAsOf, fmtClockTime, fmtVerified, withData } from "@/lib/format";
import {
  clearPendingIntent,
  readWatchedFalls,
  writePendingIntent,
  writeWatchedFalls,
} from "@/lib/local";
import {
  RANKER_SCENARIO,
  waterfallsRanker,
  type RankerScenario,
  type WaterfallRow,
} from "@/lib/waterfallsRanker";
import { SaveHeart } from "@/components/Buttons";
import { SafetyLine } from "@/components/SafetyLine";
import { WaterfallsEmailSheet } from "./WaterfallsEmailSheet";
import styles from "./waterfalls.module.css";

/* Row glyph, from the single set: ⚡ only for a fresh weather-triggered
   window that is firing; a fading window keeps the solid dot (in amber);
   unknown is always the hollow ○ — stale tends to unknown, never false
   (docs/04 §4). glyphFor in lib/format decides per-reason; the row also
   knows its window is closing, so it chooses locally. */
function rowGlyph(row: WaterfallRow): string {
  if (row.flow_state === "unknown") return "○";
  if (
    row.flow_state === "live" &&
    row.reason.wtype === "weather_triggered" &&
    row.reason.fresh
  ) {
    return "⚡";
  }
  return "●";
}

/* The compact driver reading — provenance[0] is the number the evaluator
   measured, so it wears .data (docs/00 §1). precip readings render with
   their 72-h window; gauge readings stand alone. */
function driverReading(
  reason: ReasonOut,
): { value: string; window: string | null } | null {
  const p = reason.provenance[0];
  if (!p || p.value === null) return null;
  const value = p.unit !== null ? `${p.value} ${p.unit}` : String(p.value);
  return { value, window: p.parameter === "precip_72h" ? "72 h" : null };
}

/* "as of Fri 4pm", "usgs_nwis 14142800": clock times and long station ids
   are measured and wear .data — the shared lib/format withData (single
   source of the brand rule) handles both; weekdays and words stay UI.
   fmtClockTime/fmtAsOf come Pacific-pinned and fmtVerified runs against
   generated_at, never the wall clock: this page SERVER-renders, so any
   viewer-zone or render-moment dependence would fork the server HTML
   from client hydration (React 19 then re-renders the whole SEO page). */

export function WaterfallsTool() {
  const [scenario, setScenario] = useState<RankerScenario>(RANKER_SCENARIO);
  const [savedIds, setSavedIds] = useState<Set<string>>(() => new Set());
  const [captureRow, setCaptureRow] = useState<WaterfallRow | null>(null);
  /* One capture per session: after a successful send, later ♥s confirm
     immediately — the magic link in flight covers them all. */
  const [emailCaptured, setEmailCaptured] = useState(false);
  /* The ♥ whose pending intent (lib/local) is currently parked for
     /auth/verify — so un-hearting that row can take the intent back. */
  const intentRow = useRef<string | null>(null);
  const [heartsHydrated, setHeartsHydrated] = useState(false);

  /* QA/screenshot override (?scenario=dry_spell) — reachable without an
     edit, invisible to users (no UI toggle exists, per §4 decisions).
     The fixture constant stays the source of truth for the SSR shell. */
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("scenario");
    if (q === "big_rain" || q === "dry_spell") setScenario(q);
  }, []);

  /* Hearts persist device-side (lib/local) so a reload keeps state (c)'s
     "watching this for you" rows. Hydrated in an effect, never the
     useState initializer — this page server-renders, and localStorage
     must not fork the HTML (the same hydration rule the Pacific time
     pin follows). */
  useEffect(() => {
    setSavedIds(new Set(readWatchedFalls()));
    setHeartsHydrated(true);
  }, []);

  useEffect(() => {
    if (heartsHydrated) writeWatchedFalls([...savedIds]);
  }, [heartsHydrated, savedIds]);

  const data = waterfallsRanker[scenario];
  const total = data.rows.length;

  const setSaved = (id: string, on: boolean) => {
    setSavedIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  /* Park the ♥ as the pending intent so /auth/verify actually finishes
     the save the moment the emailed link is tapped (decision 11 — no
     anonymous POST /saves exists, so the watch can only become real
     behind the session). Rows carry no affordance_id yet (flagged API
     gap in lib/waterfallsRanker) — the stable slug stands in: the mock
     loop completes end-to-end, and against the real API the verify page
     degrades to its honest "couldn't finish" note until the ranker
     endpoint serves real ids. One intent slot exists (lib/local,
     last-writer-wins), so the link completes the MOST RECENT ♥; earlier
     hearts persist device-side only. */
  const parkWatchIntent = (row: WaterfallRow) => {
    writePendingIntent({
      type: "save",
      affordance_id: row.id,
      kind: "want_to",
      place_name: row.name,
    });
    intentRow.current = row.id;
  };

  const handleHeart = (row: WaterfallRow) => {
    if (savedIds.has(row.id)) {
      setSaved(row.id, false);
      // Un-hearting the row the parked intent points at un-parks it —
      // the link must not resurrect a watch the user just took back.
      if (intentRow.current === row.id) {
        clearPendingIntent();
        intentRow.current = null;
      }
      return;
    }
    if (emailCaptured) {
      // The magic link already in flight covers later ♥s too — re-park
      // the intent on the newest row instead of re-asking for the email.
      setSaved(row.id, true);
      parkWatchIntent(row);
      return;
    }
    setCaptureRow(row);
  };

  const handleSent = () => {
    setEmailCaptured(true);
    /* State (c) lands behind the interstitial: closing the sheet shows
       the row already ♥ "watching this for you", and the parked intent
       lets /auth/verify finish the save when the link is tapped. */
    if (captureRow) {
      setSaved(captureRow.id, true);
      parkWatchIntent(captureRow);
    }
  };

  return (
    <div className={styles.page} data-shell-wide="">
      <section className={styles.tool} aria-label="Gorge waterfall ranking">
        <header className={styles.toolHead}>
          <h1 className={styles.title}>
            Gorge waterfalls, ranked by current flow
          </h1>
          <p className={styles.sub}>
            updated this morning at{" "}
            <span className="data">{fmtClockTime(data.generated_at)}</span>
            {" · "}
            <span className="data">72-h</span> NWS rain + creek gauges
            {" · "}within <span className="data">90 min</span> of Portland
          </p>
        </header>

        {/* The count line owns the honesty (docs/04 §4): a dry spell
            shortens what the rank stands behind, never the truth. */}
        <p className={styles.count}>
          <span className="data">{data.worth_count}</span> of{" "}
          <span className="data">{total}</span> worth the drive today
          {data.worth_count < total ? " — we’d rather say so." : null}
        </p>

        <ol className={styles.list}>
          {data.rows.map((row, i) => (
            <RankRow
              key={row.id}
              row={row}
              rank={i + 1}
              generatedAt={data.generated_at}
              saved={savedIds.has(row.id)}
              onHeart={() => handleHeart(row)}
            />
          ))}
        </ol>
      </section>

      <footer className={styles.foot}>
        <p className={styles.how}>
          <strong className={styles.howLead}>How we know:</strong> the rank
          blends <span className="data">72-h</span> NWS rain at each falls’
          nearest station with creek gauges where they exist, re-checked
          every morning. Sensors and named verifications — no stars, no
          sponsors.
        </p>
        <div className={styles.legal}>
          <SafetyLine
            stewardship="Leave No Trace — pack it out"
            assumptionOfRisk={ASSUMPTION_OF_RISK}
          />
        </div>
      </footer>

      {captureRow !== null && (
        <WaterfallsEmailSheet
          rowName={captureRow.name}
          open
          onSent={handleSent}
          onClose={() => setCaptureRow(null)}
        />
      )}
    </div>
  );
}

/* One ranked row: rank · name · live flow driver (glyph + .data numbers)
   · drive time, then the provenance meta line — source, last-verified,
   permit note where real. Anatomy per design/surfaces/seasonal-ranker.html
   (.rank-row / .row-driver / .row-prov), on the five type sizes. */
function RankRow({
  row,
  rank,
  generatedAt,
  saved,
  onHeart,
}: {
  row: WaterfallRow;
  rank: number;
  /* The fixture's generation instant — fmtVerified's "now", so the
     server-rendered "verified today" is a pure function of the data. */
  generatedAt: string;
  saved: boolean;
  onHeart: () => void;
}) {
  const reading = driverReading(row.reason);
  const stateClass =
    row.flow_state === "live"
      ? styles.isLive
      : row.flow_state === "fading"
        ? styles.isFading
        : styles.isUnknown;

  return (
    <li className={styles.row}>
      <span className={`${styles.rank} data`} aria-hidden="true">
        {rank}
      </span>
      <div className={styles.rowMain}>
        <p className={styles.name}>{row.name}</p>

        <p className={`${styles.driver} ${stateClass}`}>
          <span className={styles.glyph} aria-hidden="true">
            {rowGlyph(row)}
          </span>{" "}
          {reading ? (
            <>
              <span className="data">{reading.value}</span>
              {reading.window ? (
                <>
                  {" / "}
                  <span className="data">{reading.window}</span>
                </>
              ) : null}
            </>
          ) : (
            row.driver_note
          )}
          {!row.reason.fresh && row.reason.as_of ? (
            <>
              <span className={styles.sep}> · </span>
              {withData(fmtAsOf(row.reason.as_of))}
            </>
          ) : null}
          <span className={styles.sep}> · </span>
          <span className={styles.state}>{row.flow_label}</span>
          <span className={styles.sep}> · </span>
          <span className="data">{row.drive_min} min</span>
        </p>

        <p className={styles.prov}>
          {row.live_unavailable.map((label) => (
            <span key={label} className={styles.unavailable}>
              live {label} unavailable ·{" "}
            </span>
          ))}
          {row.reason.source ? withData(row.reason.source) : null}
          {" · "}
          {row.last_verified_at ? (
            <>
              <span className={styles.check} aria-hidden="true">
                ✓
              </span>{" "}
              {withData(
                fmtVerified(row.last_verified_at, null, new Date(generatedAt)),
              )}
              {row.verified_by ? (
                <>
                  {" by "}
                  <span className={styles.verifier}>@{row.verified_by}</span>
                </>
              ) : null}
            </>
          ) : (
            "not yet verified"
          )}
          {row.permit ? (
            <>
              {" · "}
              <span className={styles.permit}>{row.permit}</span>
            </>
          ) : null}
        </p>

        {saved ? (
          <p className={styles.watching}>watching this for you</p>
        ) : null}
      </div>
      <SaveHeart
        saved={saved}
        onToggle={onHeart}
        label={saved ? `Unsave ${row.name}` : `Save ${row.name}`}
      />
    </li>
  );
}
