"use client";

/* Surface 4 — the Sunday verdict sheet (docs/02 §2), route /sunday. The
   deep-link target of the Sunday 6pm push (sending is PR-9; per
   UI-DRAFT-BRIEF decision 15 the surface also ships reachable in-app).
   This screen carries the First-100 gate: ≥30% of tracked visits answer
   at least one question. Questions are about claims, never experience —
   one-tap favors, not reviews. */

import {
  Fragment,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ApiError,
  getAffordanceClaims,
  getFeed,
  getPlace,
  postVerdict,
} from "@/lib/api";
import type { FeedCard } from "@/lib/types";
import { fmtDriveMinutes, verdictApiValue } from "@/lib/format";
import { readTripRecords, type TripRecord } from "@/lib/local";
import { PrimaryButton, TertiaryButton } from "@/components/Buttons";
import { MagicLinkSheet } from "@/components/MagicLinkSheet";
import { ProvenanceLine } from "@/components/ProvenanceLine";
import type { UiVerdict } from "@/components/VerdictControls";
import {
  eyebrowWord,
  selectQuestions,
  type SundayQuestion,
} from "./sunday-questions";
import styles from "./sunday.module.css";

/* Value before asks (docs/07): Portland is the default feed origin —
   duplicated from app/page.tsx, which keeps its constant private. */
const PORTLAND = { lat: 45.512, lng: -122.658 };

/* The client is also the only record of which claims this browser already
   answered (no GET /verdicts) — same pattern as the trip record. A reload
   after answering renders the honest already-logged receipt (state f)
   without burning a request; the server's 409 backstops other devices. */
const ANSWERS_KEY = "place.sunday.answers";

const AUTH_PITCH = "Session expired — sign in and we’ll finish logging your answer.";

/* Verdict labels per UI-DRAFT-BRIEF decision 2: UI says confirm / deny /
   changed; verdictApiValue maps deny → API "refute", never displayed.
   (design/surfaces/sunday-push.html sketches Yes/No — decision 2 wins,
   and matches VerdictControls across the product.) */
const UI_ORDER: readonly UiVerdict[] = ["confirm", "deny", "changed"];

const LABELS: Record<UiVerdict, string> = {
  confirm: "Confirm",
  deny: "Deny",
  changed: "Changed",
};

/* format.ts keeps its date tables private; GoingSheet's local-date helpers
   are private too. Parsed/serialized by hand: new Date("YYYY-MM-DD") is
   UTC midnight, which shifts a day back in negative-offset timezones. */
const pad2 = (n: number): string => String(n).padStart(2, "0");

const localIsoDate = (d: Date): string =>
  `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y || 0, (m || 1) - 1, d || 1);
  date.setDate(date.getDate() + days);
  return localIsoDate(date);
}

/* The most recent trip that already happened. planned_date must be today
   or earlier — never ask about a trip we don't know happened, and a
   planned date still in the future hasn't happened yet (docs/02 §2
   Surface 4). The six-day floor matches the one-push-per-week cadence:
   Sunday's sheet covers the week behind it, nothing older. Records come
   from lib/local (shared with the GoingSheet that writes them). */
function readWeekTrip(): TripRecord | null {
  const today = localIsoDate(new Date());
  const floor = addDays(today, -6);
  let latest: TripRecord | null = null;
  for (const t of readTripRecords()) {
    if (t.planned_date > today || t.planned_date < floor) continue;
    if (latest === null || t.planned_date >= latest.planned_date) latest = t;
  }
  return latest;
}

type AnswerLog = Record<string, Record<string, UiVerdict>>;

function readAnswers(tripId: string): Record<string, UiVerdict> {
  try {
    const raw = window.localStorage.getItem(ANSWERS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
      return {};
    const forTrip: unknown = (parsed as AnswerLog)[tripId];
    if (typeof forTrip !== "object" || forTrip === null) return {};
    const out: Record<string, UiVerdict> = {};
    for (const [claimId, v] of Object.entries(forTrip)) {
      if (v === "confirm" || v === "deny" || v === "changed") out[claimId] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function rememberAnswer(tripId: string, claimId: string, verdict: UiVerdict): void {
  try {
    const raw = window.localStorage.getItem(ANSWERS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    const log: AnswerLog =
      typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
        ? (parsed as AnswerLog)
        : {};
    log[tripId] = { ...(log[tripId] ?? {}), [claimId]: verdict };
    window.localStorage.setItem(ANSWERS_KEY, JSON.stringify(log));
  } catch {
    // storage unavailable: the server still holds the verdict; only the
    // local already-answered receipt forgets
  }
}

/* VerdictOut.conditions_snapshot arrives as {discharge_cfs: 990, temp_f: 82};
   the key suffix carries the unit. Unknown suffixes render the bare value —
   never an invented unit. Duplicated from app/places/[id]/page.tsx, which
   does not export it and is owned by another surface. */
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

function snapshotParts(snapshot: Record<string, unknown>): string[] {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(snapshot)) {
    if (typeof value !== "number" && typeof value !== "string") continue;
    const unit = SNAPSHOT_UNITS.find(([suffix]) => key.endsWith(suffix));
    parts.push(unit ? `${value}${unit[1]}` : String(value));
  }
  return parts;
}

// ---------------------------------------------------------------------------
// state machines
// ---------------------------------------------------------------------------

type SheetState =
  | { status: "loading" }
  // (d) feed-only: no qualifying local trip record — zero questions ever
  | { status: "feedOnly" }
  | { status: "error" }
  | {
      status: "ready";
      trip: TripRecord;
      placeName: string;
      activityName: string | null;
      questions: SundayQuestion[];
    };

type QState =
  | { kind: "pending"; failed: boolean }
  | { kind: "posting" }
  | { kind: "answered"; verdict: UiVerdict; snapshot: string[] }
  // (f) already logged — a prior verdict exists (local record or API 409)
  | { kind: "already"; verdict: UiVerdict | null };

export default function SundayPage() {
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Sunday</h1>
        {/* The cadence promise, verbatim (UI-DRAFT-BRIEF §8). */}
        <p className={styles.sub}>
          One push a week, Sunday <span className="data">6pm</span>. That’s the
          deal.
        </p>
      </header>
      {/* useSearchParams must sit under a Suspense boundary in the App
          Router (auth/verify precedent). */}
      <Suspense fallback={<SheetSkeleton />}>
        <SundaySheet />
      </Suspense>
    </div>
  );
}

function SundaySheet() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [sheet, setSheet] = useState<SheetState>({ status: "loading" });
  const [qStates, setQStates] = useState<Record<string, QState>>({});
  const [attempt, setAttempt] = useState(0);
  const [feedTop, setFeedTop] = useState<FeedCard | null>(null);
  const [feedStatus, setFeedStatus] = useState<"loading" | "ready" | "down">(
    "loading",
  );
  const [authOpen, setAuthOpen] = useState(false);
  const pendingVerdict = useRef<{ q: SundayQuestion; ui: UiVerdict } | null>(null);
  /* State (g) rehearsal switch: the fixture client never serves a 401, so
     ?expired=1 stands in for the lapsed ~180-day session on the first tap.
     A live 401 from the real API reaches the identical catch below. */
  const expired = useRef(searchParams.get("expired") === "1");

  useEffect(() => {
    let cancelled = false;
    const trip = readWeekTrip();
    if (!trip) {
      setSheet({ status: "feedOnly" });
      return;
    }
    setSheet({ status: "loading" });
    /* The trip record carries its own place/activity names (lib/local
       TripRecord — the GoingSheet writes them because the API echoes no
       place context back). Only legacy records without names fall back to
       getPlace(affordance_id), which is semantically wrong — it hands an
       affordance id to a place route — and only works because the mock
       serves High Rocks for any id (flagged API gap: the backend needs an
       affordance→place lookup). */
    const knownName =
      typeof trip.place_name === "string" && trip.place_name.length > 0
        ? trip.place_name
        : null;
    const placePromise = knownName
      ? Promise.resolve(null)
      : getPlace(trip.affordance_id);
    Promise.all([placePromise, getAffordanceClaims(trip.affordance_id)]).then(
      ([place, claims]) => {
        if (cancelled) return;
        const aff = place
          ? (place.affordances.find(
              (a) => a.affordance_id === trip.affordance_id,
            ) ??
            place.affordances[0] ??
            null)
          : null;
        const questions = selectQuestions(claims);
        if (questions.length === 0) {
          // A trip whose claims carry no askable question hands off
          // quietly — a question is never invented to fill the slot.
          setSheet({ status: "feedOnly" });
          return;
        }
        const prior = readAnswers(trip.id);
        const initial: Record<string, QState> = {};
        for (const q of questions) {
          const was = prior[q.claim.id];
          initial[q.claim.id] = was
            ? { kind: "already", verdict: was }
            : { kind: "pending", failed: false };
        }
        setQStates(initial);
        setSheet({
          status: "ready",
          trip,
          placeName: knownName ?? place?.name ?? "your trip",
          activityName:
            (knownName ? trip.activity_name : aff?.activity_name) ?? null,
          questions,
        });
      },
      () => {
        if (!cancelled) setSheet({ status: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // The re-engagement half rides the same sheet: verify → see what's good
  // next weekend → the loop closes.
  useEffect(() => {
    let cancelled = false;
    getFeed({ lat: PORTLAND.lat, lng: PORTLAND.lng }).then(
      (res) => {
        if (cancelled) return;
        setFeedTop(res.cards[0] ?? null);
        setFeedStatus("ready");
      },
      () => {
        if (!cancelled) setFeedStatus("down");
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const setQ = (claimId: string, s: QState) =>
    setQStates((prev) => ({ ...prev, [claimId]: s }));

  async function submit(
    trip: TripRecord,
    q: SundayQuestion,
    ui: UiVerdict,
    isRetry: boolean,
  ): Promise<void> {
    setQ(q.claim.id, { kind: "posting" });
    try {
      if (expired.current) throw new ApiError(401, "session expired");
      const out = await postVerdict({
        claim_id: q.claim.id,
        verdict: verdictApiValue(ui),
        trip_id: trip.id,
      });
      rememberAnswer(trip.id, q.claim.id, ui);
      setQ(q.claim.id, {
        kind: "answered",
        verdict: ui,
        snapshot: snapshotParts(out.conditions_snapshot),
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // One verdict per trip per 24h (API cheat sheet): an honest
        // receipt, never a red error for having done the right thing.
        rememberAnswer(trip.id, q.claim.id, ui);
        setQ(q.claim.id, { kind: "already", verdict: ui });
      } else if (!isRetry && err instanceof ApiError && err.status === 401) {
        // (g) Expired session: the pending verdict survives the
        // interception (UI-DRAFT-BRIEF decision 11) and completes after
        // auth — the user never re-answers.
        pendingVerdict.current = { q, ui };
        setQ(q.claim.id, { kind: "pending", failed: false });
        setAuthOpen(true);
      } else {
        setQ(q.claim.id, { kind: "pending", failed: true });
      }
    }
  }

  const handleAuthClose = () => {
    setAuthOpen(false);
    // Magic-link auth completes out of band (page.tsx save-retry idiom):
    // one retry on close either lands the preserved verdict or settles
    // into the quiet retry note — the sheet never reopens itself.
    expired.current = false;
    const pending = pendingVerdict.current;
    pendingVerdict.current = null;
    if (pending && sheet.status === "ready") {
      void submit(sheet.trip, pending.q, pending.ui, true);
    }
  };

  if (sheet.status === "loading") return <SheetSkeleton />;

  if (sheet.status === "error") {
    return (
      <div className={styles.notice}>
        <p className={styles.noticeLead}>Couldn’t load this week’s questions.</p>
        <div className={styles.noticeAction}>
          <TertiaryButton onClick={() => setAttempt((n) => n + 1)}>
            try again →
          </TertiaryButton>
        </div>
      </div>
    );
  }

  const settled =
    sheet.status === "ready" &&
    sheet.questions.every((q) => {
      const s = qStates[q.claim.id];
      return s !== undefined && (s.kind === "answered" || s.kind === "already");
    });
  const anyOpen =
    sheet.status === "ready" &&
    sheet.questions.some((q) => {
      const s = qStates[q.claim.id];
      return s === undefined || s.kind === "pending" || s.kind === "posting";
    });

  return (
    <>
      {sheet.status === "ready" ? (
        <section className={styles.sheet} aria-label="This week’s questions">
          <header className={styles.sheetHead}>
            <h2 className={styles.sheetTitle}>You went to {sheet.placeName} —</h2>
            <p className={styles.sheetSub}>
              {sheet.questions.length === 1
                ? "one tap and you’re done"
                : "two taps and you’re done"}
            </p>
          </header>
          {sheet.questions.map((q, i) => (
            <QuestionBlock
              key={q.claim.id}
              index={i}
              total={sheet.questions.length}
              question={q}
              activityName={sheet.activityName}
              state={qStates[q.claim.id] ?? { kind: "pending", failed: false }}
              onVerdict={(ui) => void submit(sheet.trip, q, ui, false)}
            />
          ))}
          {anyOpen ? (
            // Deny framing is no-penalty (docs/02 §2 Surface 4).
            <p className={styles.noPenalty}>A no is worth as much as a yes.</p>
          ) : null}
        </section>
      ) : null}

      {sheet.status === "feedOnly" || settled ? (
        <NextWeekend
          card={feedTop}
          feedStatus={feedStatus}
          feedOnly={sheet.status === "feedOnly"}
          onSeeFeed={() => router.push("/")}
        />
      ) : null}

      <MagicLinkSheet pitch={AUTH_PITCH} open={authOpen} onClose={handleAuthClose} />
    </>
  );
}

// ---------------------------------------------------------------------------
// question block
// ---------------------------------------------------------------------------

const CHOSEN_CLASS: Record<UiVerdict, string> = {
  confirm: "isConfirm",
  deny: "isDeny",
  changed: "isChanged",
};

/* One claim, one tap. Buttons mirror design/components/verdict-controls
   (idle / answered-confirm / answered-deny) rather than reusing the
   VerdictControls component: its answered micro-copy is fixed, and this
   surface's notes are different by spec — the confirm note carries the
   postVerdict conditions_snapshot ("logged with conditions at 990 cfs,
   82°F") and changed reads "Noted — we'll re-check this claim". */
function QuestionBlock({
  index,
  total,
  question,
  activityName,
  state,
  onVerdict,
}: {
  index: number;
  total: number;
  question: SundayQuestion;
  activityName: string | null;
  state: QState;
  onVerdict: (ui: UiVerdict) => void;
}) {
  const options = UI_ORDER.filter((v) =>
    question.claim.allowed_verdicts.includes(verdictApiValue(v)),
  );
  const locked = state.kind !== "pending";
  const chosen =
    state.kind === "answered" || state.kind === "already" ? state.verdict : null;
  const showChoice = state.kind === "answered" || state.kind === "already";

  const btnClass = (v: UiVerdict) =>
    showChoice
      ? `${styles.vbtn} ${chosen === v ? styles[CHOSEN_CLASS[v]] : styles.isReceded}`
      : styles.vbtn;

  let note: ReactNode = null;
  if (state.kind === "answered" && state.verdict === "confirm") {
    // The auto-attached snapshot — the user never describes the weather.
    note = (
      <p className={styles.note} role="status">
        <span className={`${styles.noteMark} ${styles.ok}`} aria-hidden="true">
          ✓
        </span>
        <span>
          {state.snapshot.length > 0 ? (
            <>
              Thanks — logged with conditions at{" "}
              {state.snapshot.map((part, i) => (
                <Fragment key={part}>
                  {i > 0 ? ", " : null}
                  <span className="data">{part}</span>
                </Fragment>
              ))}
            </>
          ) : (
            "Thanks — logged with today’s conditions"
          )}
        </span>
      </p>
    );
  } else if (state.kind === "answered") {
    // (e) deny/changed: a single quiet confirmation, no follow-up form.
    // No receipt glyph — the single set has no deny/changed mark (✕ and ~
    // don't exist in this system; ● is reserved for "other live").
    note = (
      <p className={styles.note} role="status">
        <span>Noted — we’ll re-check this claim</span>
      </p>
    );
  } else if (state.kind === "already") {
    note = (
      <p className={styles.note} role="status">
        <span className={`${styles.noteMark} ${styles.ok}`} aria-hidden="true">
          ✓
        </span>
        <span>Already logged this week</span>
      </p>
    );
  } else if (state.kind === "pending" && state.failed) {
    note = (
      <p className={styles.qError} role="status">
        Couldn’t log that — try again.
      </p>
    );
  }

  return (
    <div className={styles.qblock}>
      <p className={styles.qEyebrow}>
        {index + 1} of {total} · {eyebrowWord(question.claim, activityName)} claim
      </p>
      <p className={styles.qText}>{question.text}</p>
      <div className={styles.verdicts}>
        {options.map((v) => (
          <button
            key={v}
            type="button"
            className={btnClass(v)}
            aria-pressed={showChoice ? chosen === v : undefined}
            disabled={locked}
            onClick={() => onVerdict(v)}
          >
            {LABELS[v]}
            {v === "confirm" ? (
              <span className={styles.vGlyph} aria-hidden="true">
                ✓
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {note}
    </div>
  );
}

// ---------------------------------------------------------------------------
// next weekend — the re-engagement half
// ---------------------------------------------------------------------------

function NextWeekend({
  card,
  feedStatus,
  feedOnly,
  onSeeFeed,
}: {
  card: FeedCard | null;
  feedStatus: "loading" | "ready" | "down";
  feedOnly: boolean;
  onSeeFeed: () => void;
}) {
  // "41 min drive" — minutes are measured (.data); the word is not
  // (ExperienceCard idiom).
  const drive = card ? fmtDriveMinutes(card.distance_km) : null;
  const driveValue = drive ? drive.replace(/ drive$/, "") : null;

  return (
    <section className={styles.sheet} aria-label="Next weekend">
      {feedOnly ? (
        /* (d) Never ask about a trip we don't know happened (docs/02 §2
           Surface 4): with no local trip record the sheet carries zero
           questions — only this quiet hand-off. */
        <p className={styles.quiet}>
          Nothing to verify this week — we only ask about trips you’ve
          declared.
        </p>
      ) : null}
      <div className={styles.nwRow}>
        <h2 className={styles.nwHead}>Next weekend</h2>
        <p className={styles.nwMeta}>top feed card</p>
      </div>
      {card ? (
        <article className={styles.mini}>
          <div className={styles.miniIdentity}>
            <h3 className={`place-name ${styles.miniName}`}>{card.place_name}</h3>
            {drive && driveValue ? (
              <span className={styles.drive}>
                <span className="data">{driveValue}</span>
                {drive.slice(driveValue.length)}
              </span>
            ) : null}
          </div>
          <div className={styles.miniProv}>
            <ProvenanceLine
              reasons={card.reasons.slice(0, 1)}
              lastVerifiedAt={card.reasons.length === 0 ? card.last_verified_at : null}
              verifiedBy={card.reasons.length === 0 ? card.verified_by : null}
              compact
            />
          </div>
        </article>
      ) : feedStatus === "loading" ? (
        <div className={styles.miniSk} aria-hidden="true">
          <div className={`${styles.skBar} ${styles.skMiniTitle}`} />
          <div className={`${styles.skBar} ${styles.skMiniLead}`} />
        </div>
      ) : (
        // Degraded is a state, not a guess: "live … unavailable", never
        // "conditions bad" (docs/04 §4).
        <p className={styles.nwDown}>
          <span aria-hidden="true">○</span> live feed unavailable
        </p>
      )}
      <div className={styles.feedAction}>
        {/* No trailing → on a filled primary — the arrow belongs to
            tertiaries/link-outs only (glyph canon). The brief's "see the
            feed →" prompt copy fixes the words; sunday-push.html's arrowed
            button is a sketch, and canon glyph rules win. */}
        <PrimaryButton onClick={onSeeFeed}>see the feed</PrimaryButton>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// loading — respects the sheet anatomy, never a bare spinner
// ---------------------------------------------------------------------------

function SheetSkeleton() {
  return (
    <div role="status" aria-label="Loading this week’s questions">
      <section className={`${styles.sheet} ${styles.skSheet}`} aria-hidden="true">
        <div className={`${styles.skBar} ${styles.skTitle}`} />
        <div className={`${styles.skBar} ${styles.skSub}`} />
        {[0, 1].map((i) => (
          <div key={i} className={styles.skQ}>
            <div className={`${styles.skBar} ${styles.skEyebrow}`} />
            <div className={`${styles.skBar} ${styles.skQuestion}`} />
            <div className={styles.skVerdicts}>
              <div className={styles.skBtn} />
              <div className={styles.skBtn} />
              <div className={styles.skBtn} />
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
