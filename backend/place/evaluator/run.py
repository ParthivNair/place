"""The condition-evaluator sweep (docs/04 §4) — the component that makes
Place temporal.

``python -m place.evaluator.run [--once] [--interval-minutes N]``

One lockfile-guarded process (flock, so a crashed run never wedges the next):
each sweep

  1. idempotently ensures current+next month feed_readings partitions;
  2. fetches every due feed (per-feed cadence via the registry; adapters are
     isolated — one throwing never aborts the run) and stores readings +
     feeds.last_value + feed_health rows; three consecutive failures alert;
  3. re-evaluates every condition_windows.predicate (the DSL walker) against
     the readings — stale readings evaluate as unknown (rule 1) — updating
     the denormalized state and appending condition_states history;
  4. rewrites good_now with the three-factor now_score upsert (docs/01 §7 Q1)
     and drops rows that no longer qualify (hazard kill switches);
  5. runs the standing-query (saves) alert pass (docs/01 §7 Q3).

Default mode loops every ``--interval-minutes`` (30, the docs/04 sweep
cadence); ``--once`` runs a single sweep and exits (cron mode — cron is the
deployment story, the loop is a dev convenience).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import fcntl
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from sqlalchemy import Connection, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from place import dsl, scoring
from place.config import Settings, get_settings
from place.db import ensure_feed_readings_partitions, get_sync_engine
from place.evaluator import alerts, health, registry
from place.evaluator.adapters.base import FeedAdapter, Reading
from place.models import condition_states, condition_windows, feed_readings, feeds

log = logging.getLogger("place.evaluator")

__all__ = ["DbReadingsProvider", "SweepStats", "main", "sweep"]


# ---------------------------------------------------------------------------
# readings provider (DB-backed; owns the stale-as-unknown rule)
# ---------------------------------------------------------------------------



# The sweep anchors `now` at its start, but adapters stamp locally-computed
# readings (astro) at *fetch* time, seconds later — without a small forward
# tolerance those readings would be invisible in the very sweep that produced
# them and every astro window would evaluate unknown in --once mode. Five
# minutes is far below any feed cadence, and on the tide prediction curve a
# value 5 minutes ahead still describes "now".
_FETCH_SKEW = dt.timedelta(minutes=5)


class DbReadingsProvider:
    """dsl.ReadingsProvider over feed_readings.

    - ``latest`` returns the newest reading with observed_at <= now (plus
      the small _FETCH_SKEW tolerance; tide *predictions* extend hours into
      the future and the predicate asks about now), or None when missing or
      stale (> 2x cadence old, docs/04 §4 rule 1).
    - ``window`` returns values in (now - window_h, now]; None when empty or
      when even the newest reading in the window is stale.
    """

    def __init__(self, conn: Connection, now: dt.datetime) -> None:
        self._conn = conn
        self._now = now
        self._latest_cache: dict[str, float | None] = {}
        self._window_cache: dict[tuple[str, int], list[float] | None] = {}
        # observed_at of the newest usable reading served per feed — the
        # evaluator stores it in condition_states.inputs so cards render
        # freshness from the *reading's* age (docs/04 §4 rule 1), not from
        # evaluated_at.
        self._observed: dict[str, dt.datetime] = {}

    def observed_at(self, feed_id: str) -> dt.datetime | None:
        """observed_at of the newest reading a latest()/window() call used."""
        return self._observed.get(feed_id)

    def latest(self, feed_id: str) -> float | None:
        if feed_id not in self._latest_cache:
            row = self._conn.execute(
                select(feed_readings.c.value, feed_readings.c.observed_at)
                .where(
                    feed_readings.c.feed_id == feed_id,
                    feed_readings.c.observed_at <= self._now + _FETCH_SKEW,
                )
                .order_by(feed_readings.c.observed_at.desc())
                .limit(1)
            ).first()
            if row is None or registry.is_stale(row.observed_at, feed_id, self._now):
                self._latest_cache[feed_id] = None
            else:
                self._latest_cache[feed_id] = float(row.value)
                self._observed[feed_id] = row.observed_at
        return self._latest_cache[feed_id]

    def window(self, feed_id: str, window_h: int) -> list[float] | None:
        key = (feed_id, window_h)
        if key not in self._window_cache:
            since = self._now - dt.timedelta(hours=window_h)
            rows = self._conn.execute(
                select(feed_readings.c.value, feed_readings.c.observed_at)
                .where(
                    feed_readings.c.feed_id == feed_id,
                    feed_readings.c.observed_at > since,
                    feed_readings.c.observed_at <= self._now,
                )
                .order_by(feed_readings.c.observed_at.asc())
            ).all()
            if not rows or registry.is_stale(rows[-1].observed_at, feed_id, self._now):
                self._window_cache[key] = None
            else:
                self._window_cache[key] = [float(r.value) for r in rows]
                newest = rows[-1].observed_at
                if feed_id not in self._observed or newest > self._observed[feed_id]:
                    self._observed[feed_id] = newest
        return self._window_cache[key]


# ---------------------------------------------------------------------------
# fetch phase
# ---------------------------------------------------------------------------


@dataclass
class _FetchOutcome:
    adapter: FeedAdapter
    readings: list[Reading] | None
    error: BaseException | None
    latency_ms: int


async def _fetch_one(adapter: FeedAdapter) -> _FetchOutcome:
    t0 = time.monotonic()
    try:
        readings = list(await adapter.fetch())
        return _FetchOutcome(adapter, readings, None, int((time.monotonic() - t0) * 1000))
    except Exception as exc:  # adapter isolation, docs/04 §4 rule 4
        return _FetchOutcome(adapter, None, exc, int((time.monotonic() - t0) * 1000))


async def _fetch_all(adapters: Sequence[FeedAdapter]) -> list[_FetchOutcome]:
    return list(await asyncio.gather(*(_fetch_one(a) for a in adapters)))


def _store_readings(
    conn: Connection, readings: Sequence[Reading], known_feed_ids: set[str]
) -> int:
    """Insert readings (idempotent on the (feed_id, observed_at) PK) and
    refresh feeds.last_value/last_observed_at. Readings for feed ids without
    a feeds row are dropped with a warning (FK safety)."""
    rows = []
    for r in readings:
        if r.feed_id not in known_feed_ids:
            log.warning("dropping reading for unregistered feed %s", r.feed_id)
            continue
        rows.append({"feed_id": r.feed_id, "observed_at": r.observed_at, "value": r.value})
    if not rows:
        return 0
    conn.execute(
        pg_insert(feed_readings).on_conflict_do_nothing(
            index_elements=["feed_id", "observed_at"]
        ),
        rows,
    )
    newest: dict[str, Reading] = {}
    for r in readings:
        if r.feed_id in known_feed_ids and (
            r.feed_id not in newest or r.observed_at > newest[r.feed_id].observed_at
        ):
            newest[r.feed_id] = r
    for feed_id, r in newest.items():
        conn.execute(
            update(feeds)
            .where(feeds.c.id == feed_id)
            .values(last_value=r.value, last_observed_at=r.observed_at)
        )
    return len(rows)


# ---------------------------------------------------------------------------
# evaluate phase
# ---------------------------------------------------------------------------


def _enrich_inputs(
    inputs: dict[str, Any], provider: DbReadingsProvider
) -> dict[str, Any]:
    """Attach each reading's observed_at to the stored inputs (docs/04 §4
    rule 1: every condition_states row carries the reading's observed_at).

    Feed values become {"value": v, "observed_at": iso}; non-feed keys
    ("month", "predicate_error") and missing/stale values (None) stay scalar.
    reasons.normalize_reading parses both shapes.
    """
    out: dict[str, Any] = {}
    for key, value in inputs.items():
        observed = provider.observed_at(key) if value is not None else None
        if observed is not None:
            out[key] = {"value": value, "observed_at": observed.isoformat()}
        else:
            out[key] = value
    return out


def _evaluate_windows(conn: Connection, now: dt.datetime) -> tuple[int, int]:
    """Re-evaluate every condition window; returns (evaluated, unknown)."""
    provider = DbReadingsProvider(conn, now)
    rows = conn.execute(
        select(
            condition_windows.c.id,
            condition_windows.c.predicate,
            condition_windows.c.state,
            condition_windows.c.is_gate,
        )
    ).all()
    unknown = 0
    history: list[dict[str, Any]] = []
    for row in rows:
        try:
            dsl.validate_predicate(row.predicate, is_gate=row.is_gate)
            result = dsl.evaluate(row.predicate, provider, now=now, prev_state=row.state)
        except dsl.DSLError as exc:
            log.error("window %s: invalid predicate: %s", row.id, exc)
            result = dsl.EvalResult(state=None, inputs={"predicate_error": str(exc)})
        values: dict[str, Any] = {"state": result.state, "last_eval": now}
        if result.state is not row.state:  # tri-state flip
            values["state_since"] = now
        conn.execute(
            update(condition_windows).where(condition_windows.c.id == row.id).values(**values)
        )
        if result.state is None:
            unknown += 1
        else:
            # condition_states.satisfied is NOT NULL: unknown evaluations update
            # the denormalized state but append no history row.
            history.append(
                {
                    "window_id": row.id,
                    "satisfied": result.state,
                    "evaluated_at": now,
                    "inputs": _enrich_inputs(result.inputs, provider),
                }
            )
    if history:
        conn.execute(condition_states.insert(), history)
    return len(rows), unknown


# ---------------------------------------------------------------------------
# materialize phase — docs/01 §7 Q1, verbatim modulo :now parameterization,
# plus a stale-row delete so disqualified affordances drop out (hazard kill
# switches must *remove* cards, not leave old scores behind).
#
# Two docs/01 rules the migration's publication trigger defers to query time
# are enforced here, in this single statement:
# - §5 corroboration boost: each claim's effective log-odds gains +0.5 nats
#   per *other* independent published source_domain on the same affordance,
#   capped at +1.5 (the stored log_odds stays prior + verdict updates; the
#   boost is stateless at read time, so it never double-counts).
# - §4 gate 2 confidence bar: top-claim effective confidence must be >= 0.45
#   to serve ("pulled from serving until re-verified" when decay/refutes drop
#   it below the bar).
# The hazard confirm prong requires the confirming verdict to come from a
# power_verifier (the founder is verifier #1) on a *published* claim — an
# unprivileged self-confirm must never open a hazard gate (docs/04 §4 rule 3).
# ---------------------------------------------------------------------------

_GOOD_NOW_UPSERT = text(
    """
INSERT INTO good_now (affordance_id, now_score, reasons, computed_at)
SELECT a.id,
       a.base_quality
         * COALESCE(EXP(SUM(LN(cw.multiplier)) FILTER (WHERE cw.state)), 1.0)
         * top_claim.conf AS now_score,
       COALESCE(jsonb_agg(jsonb_build_object('window_id', cw.id, 'wtype', cw.wtype))
                FILTER (WHERE cw.state), '[]'::jsonb) AS reasons,
       :now
FROM affordances a
LEFT JOIN condition_windows cw ON cw.affordance_id = a.id
CROSS JOIN LATERAL (
  SELECT MAX( (1/(1+EXP(-(c.log_odds + LEAST(:corr_nats * indep.n, :corr_cap)))))
            * EXP(-(LN(2.0)/hl.days)
                  * EXTRACT(epoch FROM CAST(:now AS timestamptz) - c.last_evidence_at)/86400)
        ) AS conf
  FROM claims c
  JOIN (VALUES ('geomorphic', 3650.0), ('seasonal_bio', 730.0),
               ('access', 180.0), ('hazard_calibration', 60.0)) AS hl(cclass, days)
    ON hl.cclass = c.cclass::text
  CROSS JOIN LATERAL (
    SELECT count(DISTINCT c3.source_domain) AS n
    FROM claims c3
    WHERE c3.affordance_id = a.id AND c3.superseded_by IS NULL
      AND c3.status = 'published' AND c3.source_domain IS NOT NULL
      AND c3.source_domain IS DISTINCT FROM c.source_domain
  ) indep
  WHERE c.affordance_id = a.id AND c.superseded_by IS NULL AND c.status = 'published'
) top_claim
WHERE a.status = 'published'
  AND top_claim.conf >= :conf_bar   -- docs/01 §4 gate 2 (NULL conf never serves)
  AND NOT EXISTS (SELECT 1 FROM places p WHERE p.id = a.place_id AND p.sensitive)
  AND NOT EXISTS (  -- hazard kill switch 1: every is_gate window must be live-true
      SELECT 1 FROM condition_windows g
      WHERE g.affordance_id = a.id AND g.is_gate AND g.state IS DISTINCT FROM true)
  AND (             -- hazard kill switch 2: recent trusted confirm within class half-life
      NOT EXISTS (SELECT 1 FROM activities act
                  WHERE act.id = a.activity_id AND act.hazard_class)
      OR EXISTS (SELECT 1 FROM verifications v
                 JOIN claims c2 ON c2.id = v.claim_id
                 JOIN users u ON u.id = v.user_id
                 WHERE c2.affordance_id = a.id AND c2.status = 'published'
                   AND v.verdict = 'confirm' AND u.power_verifier
                   AND v.verified_at > CAST(:now AS timestamptz) - interval '60 days'))
GROUP BY a.id, a.base_quality, top_claim.conf
ON CONFLICT (affordance_id) DO UPDATE
  SET now_score = EXCLUDED.now_score, reasons = EXCLUDED.reasons,
      computed_at = EXCLUDED.computed_at
"""
)

_GOOD_NOW_PRUNE = text("DELETE FROM good_now WHERE computed_at < :now")
_GOOD_NOW_COUNT = text("SELECT count(*) FROM good_now")


def _materialize_good_now(conn: Connection, now: dt.datetime) -> int:
    conn.execute(
        _GOOD_NOW_UPSERT,
        {
            "now": now,
            "corr_nats": scoring.CORROBORATION_NATS,
            "corr_cap": scoring.CORROBORATION_CAP_NATS,
            "conf_bar": scoring.SERVING_CONFIDENCE_BAR,
        },
    )
    conn.execute(_GOOD_NOW_PRUNE, {"now": now})
    return int(conn.execute(_GOOD_NOW_COUNT).scalar_one())


# ---------------------------------------------------------------------------
# the sweep
# ---------------------------------------------------------------------------


@dataclass
class SweepStats:
    started_at: dt.datetime
    feeds_fetched: int = 0
    feeds_failed: int = 0
    feeds_skipped: int = 0
    readings_stored: int = 0
    windows_evaluated: int = 0
    windows_unknown: int = 0
    good_now_rows: int = 0
    alerts_matched: int = 0
    skipped: list[registry.SkippedFeed] = field(default_factory=list)


def sweep(
    engine: Engine,
    *,
    settings: Settings | None = None,
    now: dt.datetime | None = None,
    adapters: Sequence[FeedAdapter] | None = None,
) -> SweepStats:
    """Run one full sweep. `adapters=None` builds the due set from the feeds
    table via the registry; passing an explicit list (tests, backfills)
    fetches exactly those. `now` is injectable for deterministic tests."""
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.UTC)
    stats = SweepStats(started_at=now)

    with engine.begin() as conn:
        ensure_feed_readings_partitions(conn, now)

    # --- fetch phase -------------------------------------------------------
    with engine.connect() as conn:
        feed_rows = conn.execute(select(feeds)).mappings().all()
        known_feed_ids = {row["id"] for row in feed_rows}
        if adapters is None:
            last_ok = health.last_ok_checked_at(conn)
            due_rows = [
                row
                for row in feed_rows
                if row["id"] not in last_ok
                or now - last_ok[row["id"]] >= registry.cadence_for(row["provider"])
            ]
            adapter_list, skipped = registry.load_adapters(due_rows, settings)
            stats.skipped = skipped
            stats.feeds_skipped = len(skipped)
        else:
            adapter_list = list(adapters)

    outcomes = asyncio.run(_fetch_all(adapter_list)) if adapter_list else []
    for outcome in outcomes:
        feed_id = outcome.adapter.feed_id
        with engine.begin() as conn:  # per-adapter transaction: isolation
            if outcome.error is not None:
                stats.feeds_failed += 1
                log.warning("feed %s fetch failed: %s", feed_id, outcome.error)
                health.record(
                    conn, feed_id, ok=False, latency_ms=outcome.latency_ms,
                    error=str(outcome.error)[:500], checked_at=now,
                )
                health.check_and_alert(conn, feed_id)
            else:
                stats.feeds_fetched += 1
                stored = _store_readings(conn, outcome.readings or [], known_feed_ids)
                stats.readings_stored += stored
                own = [r.observed_at for r in outcome.readings or [] if r.feed_id == feed_id]
                # ok=True (no failure alert) but note the empty result so a
                # zone/station filter mismatch or an off-season NWAC feed is
                # visible in feed_health instead of masquerading as healthy.
                health.record(
                    conn, feed_id, ok=True, latency_ms=outcome.latency_ms,
                    reading_observed_at=max(own) if own else None, checked_at=now,
                    error=None if own else "live_unavailable: fetch ok, no readings for this feed",
                )

    # --- evaluate + materialize + alerts (one transaction) ------------------
    with engine.begin() as conn:
        stats.windows_evaluated, stats.windows_unknown = _evaluate_windows(conn, now)
        stats.good_now_rows = _materialize_good_now(conn, now)
        stats.alerts_matched = len(alerts.run_alert_pass(conn, now=now))

    log.info(
        "sweep done: %d fetched / %d failed / %d skipped feeds, %d readings, "
        "%d windows (%d unknown), %d good_now rows, %d alerts",
        stats.feeds_fetched, stats.feeds_failed, stats.feeds_skipped,
        stats.readings_stored, stats.windows_evaluated, stats.windows_unknown,
        stats.good_now_rows, stats.alerts_matched,
    )
    return stats


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def _acquire_lock(path: Path) -> IO[str] | None:
    """flock-based guard: returns the held file handle, or None if another
    evaluator holds the lock. flock dies with the process — no stale locks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Place condition-evaluator sweep")
    parser.add_argument("--once", action="store_true",
                        help="run a single sweep and exit (cron mode)")
    parser.add_argument("--interval-minutes", type=float, default=30.0,
                        help="loop interval when not --once (default 30)")
    args = parser.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    lock = _acquire_lock(settings.evaluator_lockfile)
    if lock is None:
        log.info("another evaluator run holds %s; exiting", settings.evaluator_lockfile)
        return 0

    engine = get_sync_engine(settings)
    try:
        while True:
            try:
                sweep(engine, settings=settings)
            except Exception:
                if args.once:
                    raise
                log.exception("sweep failed; retrying next interval")
            if args.once:
                return 0
            time.sleep(args.interval_minutes * 60)
    finally:
        engine.dispose()
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
