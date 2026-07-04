"""Integration tests for the evaluator sweep against the compose postgres,
using synthetic feeds/readings (no network).

Explicitly marked `integration` (this directory is component-owned; the
conftest applies the marker by path only under tests/integration/).

Covers, end to end: partition creation, adapter isolation + feed_health,
reading storage, DSL evaluation with hysteresis-carrying gate windows,
stale-readings-flip-to-unknown (rule 1), degrade-to-seasonal-priors (rule 2),
both hazard kill switches (rule 3 / docs/01 §7 Q1), condition_states history,
good_now materialization + pruning, and the saves standing-query alert pass.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import insert, select, text

from place import scoring
from place.db import ensure_feed_readings_partitions
from place.evaluator import health
from place.evaluator.adapters.base import AdapterError, FeedAdapter, Reading
from place.evaluator.run import sweep
from place.models import (
    activities,
    affordances,
    claims,
    condition_states,
    condition_windows,
    feed_readings,
    feeds,
    good_now,
    saves,
    users,
    verifications,
)

pytestmark = pytest.mark.integration

F_FLOW = "usgs_nwis:14210000:00060"
F_TEMP = "open_meteo:45.44,-122.62:air_temp_f"
F_PRECIP = "nws:45.40,-121.57:precip_in"
F_BROKEN = "usgs_nwis:99999999:00060"


class FakeAdapter(FeedAdapter):
    def __init__(self, feed_id: str, readings: list[Reading]):
        super().__init__(feed_id, unit="synthetic")
        self._readings = readings

    async def fetch(self):
        return self._readings


class FailingAdapter(FeedAdapter):
    def __init__(self, feed_id: str):
        super().__init__(feed_id, unit="synthetic")

    async def fetch(self):
        raise AdapterError("synthetic outage")


def _seed(conn, now: dt.datetime) -> dict:
    """Synthetic graph: a hazard wild-swim (gate + seasonal windows, recent
    founder confirm) and a standard waterfall (weather + seasonal windows)."""
    ensure_feed_readings_partitions(conn, now)  # before any readings land

    for fid, provider, param, unit in [
        (F_FLOW, "usgs_nwis", "00060", "cfs"),
        (F_TEMP, "open_meteo", "air_temp_f", "degF"),
        (F_PRECIP, "nws", "precip_in", "in"),
        (F_BROKEN, "usgs_nwis", "00060", "cfs"),
    ]:
        conn.execute(
            insert(feeds).values(id=fid, provider=provider, parameter=param, unit=unit)
        )

    # pre-seeded readings (the flow reading arrives via the fake adapter)
    rows = [
        (F_TEMP, now - dt.timedelta(minutes=30), 80.0),
        (F_PRECIP, now - dt.timedelta(hours=1), 0.6),
        (F_PRECIP, now - dt.timedelta(hours=2), 0.5),
        (F_PRECIP, now - dt.timedelta(hours=3), 0.5),
    ]
    for fid, at, value in rows:
        conn.execute(insert(feed_readings).values(feed_id=fid, observed_at=at, value=value))

    ids = {
        "p_swim": uuid.uuid4(), "p_falls": uuid.uuid4(),
        "a_swim": uuid.uuid4(), "a_falls": uuid.uuid4(),
        "w_gate": uuid.uuid4(), "w_season": uuid.uuid4(),
        "w_rain": uuid.uuid4(), "w_season2": uuid.uuid4(),
        "c_swim": uuid.uuid4(), "c_falls": uuid.uuid4(),
        "user": uuid.uuid4(),
    }
    for pid, name, kind, lng, lat in [
        (ids["p_swim"], "High Rocks (synthetic)", "swim_hole", -122.62, 45.44),
        (ids["p_falls"], "Tamanawas Falls (synthetic)", "waterfall", -121.57, 45.40),
    ]:
        conn.execute(
            text(
                "INSERT INTO places (id, name, kind, geom) VALUES "
                "(:id, :name, :kind, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))"
            ),
            {"id": pid, "name": name, "kind": kind, "lng": lng, "lat": lat},
        )

    conn.execute(insert(activities).values(id="wild_swim", display_name="Wild swim",
                                           hazard_class=True))
    conn.execute(insert(activities).values(id="waterfall_view", display_name="Waterfall view",
                                           hazard_class=False))

    # draft first: the DB publication-gate trigger requires supporting claims
    conn.execute(insert(affordances).values(
        id=ids["a_swim"], place_id=ids["p_swim"], activity_id="wild_swim",
        base_quality=0.8, status="draft"))
    conn.execute(insert(affordances).values(
        id=ids["a_falls"], place_id=ids["p_falls"], activity_id="waterfall_view",
        base_quality=0.7, status="draft"))

    month = now.month
    conn.execute(insert(condition_windows).values(
        id=ids["w_gate"], affordance_id=ids["a_swim"], wtype="hydrological",
        predicate={"all": [
            {"feed": F_FLOW, "op": "<", "value": 1050, "exit_value": 1200},
            {"feed": F_TEMP, "op": ">", "value": 75},
        ]},
        multiplier=2.0, is_gate=True))
    conn.execute(insert(condition_windows).values(
        id=ids["w_season"], affordance_id=ids["a_swim"], wtype="seasonal",
        predicate={"month": [month, month]}, multiplier=1.2, is_gate=False))
    conn.execute(insert(condition_windows).values(
        id=ids["w_rain"], affordance_id=ids["a_falls"], wtype="weather_triggered",
        predicate={"feed": F_PRECIP, "agg": "sum", "window_h": 72, "op": ">=", "value": 1.0},
        multiplier=1.8, is_gate=False))
    conn.execute(insert(condition_windows).values(
        id=ids["w_season2"], affordance_id=ids["a_falls"], wtype="seasonal",
        predicate={"month": [1, 12]}, multiplier=1.3, is_gate=False))

    conn.execute(insert(claims).values(
        id=ids["c_swim"], affordance_id=ids["a_swim"], window_id=ids["w_gate"],
        cclass="hazard_calibration", stype="founder_verified", source_domain="place.local",
        status="published", log_odds=1.76, last_evidence_at=now))
    conn.execute(insert(claims).values(
        id=ids["c_falls"], affordance_id=ids["a_falls"],
        cclass="seasonal_bio", stype="llm_extracted", source_domain="oregonhikers.org",
        status="published", log_odds=0.38,
        last_evidence_at=now - dt.timedelta(days=30)))
    # second independent domain to satisfy the structural publication gate;
    # strictly lower confidence so the top claim stays c_falls
    conn.execute(insert(claims).values(
        id=uuid.uuid4(), affordance_id=ids["a_falls"],
        cclass="seasonal_bio", stype="llm_extracted", source_domain="reddit.com",
        status="published", log_odds=-0.62,
        last_evidence_at=now - dt.timedelta(days=30)))

    conn.execute(affordances.update().values(status="published"))

    conn.execute(insert(users).values(id=ids["user"], email="verifier@example.com",
                                      power_verifier=True))
    conn.execute(insert(verifications).values(
        claim_id=ids["c_swim"], user_id=ids["user"], verdict="confirm",
        conditions_snapshot={F_FLOW: 410, F_TEMP: 84}, verified_at=now))

    # a want_to save on the waterfall: the standing query (docs/01 §7 Q3)
    conn.execute(insert(saves).values(
        user_id=ids["user"], affordance_id=ids["a_falls"], kind="want_to",
        created_at=now - dt.timedelta(days=3)))
    return ids


def _good_now_rows(conn) -> dict:
    return {
        row.affordance_id: row
        for row in conn.execute(select(good_now)).all()
    }


def _window_state(conn, window_id):
    return conn.execute(
        select(condition_windows.c.state, condition_windows.c.state_since)
        .where(condition_windows.c.id == window_id)
    ).one()


def test_sweep_end_to_end(db):
    now1 = dt.datetime.now(dt.UTC)
    with db.begin() as conn:
        ids = _seed(conn, now1)

    flow_reading = Reading(F_FLOW, 900.0, now1 - dt.timedelta(minutes=5))
    stats1 = sweep(
        db, now=now1,
        adapters=[FakeAdapter(F_FLOW, [flow_reading]), FailingAdapter(F_BROKEN)],
    )

    # --- fetch phase: storage, feeds refresh, health, adapter isolation ----
    assert stats1.feeds_fetched == 1 and stats1.feeds_failed == 1
    assert stats1.readings_stored == 1
    with db.connect() as conn:
        stored = conn.execute(
            select(feed_readings.c.value).where(feed_readings.c.feed_id == F_FLOW)
        ).scalars().all()
        assert [float(v) for v in stored] == [900.0]
        feed_row = conn.execute(select(feeds).where(feeds.c.id == F_FLOW)).one()
        assert float(feed_row.last_value) == 900.0
        assert feed_row.last_observed_at == flow_reading.observed_at

        health_rows = conn.execute(
            select(health.feed_health.c.feed_id, health.feed_health.c.ok)
        ).all()
        assert (F_FLOW, True) in health_rows
        assert (F_BROKEN, False) in health_rows

        # --- evaluation: all four windows true, history appended -----------
        for w in ("w_gate", "w_season", "w_rain", "w_season2"):
            state, since = _window_state(conn, ids[w])
            assert state is True
            assert since == now1
        gate_inputs = conn.execute(
            select(condition_states.c.inputs)
            .where(condition_states.c.window_id == ids["w_gate"])
        ).scalar_one()
        # inputs carry {value, observed_at} so cards can render freshness
        # from the reading's age (docs/04 §4 rule 1), not evaluated_at
        assert gate_inputs[F_FLOW]["value"] == 900.0
        assert gate_inputs[F_FLOW]["observed_at"] == flow_reading.observed_at.isoformat()
        assert gate_inputs[F_TEMP]["value"] == 80.0

        # --- good_now: three-factor scores, SQL math == scoring.py math ----
        rows = _good_now_rows(conn)
        assert set(rows) == {ids["a_swim"], ids["a_falls"]}

        swim_conf = scoring.effective_confidence(1.76, "hazard_calibration", now1, now1)
        expected_swim = scoring.now_score(0.8, [2.0, 1.2], swim_conf, hazard_class=True)
        assert float(rows[ids["a_swim"]].now_score) == pytest.approx(expected_swim, rel=1e-9)

        # c_falls is corroborated by one other independent published domain
        # (reddit.com), so serving confidence includes the +0.5-nat boost
        # (docs/01 §5); c_swim has no corroborator, so its L is unboosted.
        falls_conf = scoring.effective_confidence(
            0.38 + scoring.corroboration_boost(1), "seasonal_bio",
            now1 - dt.timedelta(days=30), now1)
        expected_falls = scoring.now_score(0.7, [1.8, 1.3], falls_conf)
        assert float(rows[ids["a_falls"]].now_score) == pytest.approx(expected_falls, rel=1e-9)

        reasons = rows[ids["a_swim"]].reasons
        assert {r["window_id"] for r in reasons} == {str(ids["w_gate"]), str(ids["w_season"])}

        # --- standing-query alert: fired and stamped ------------------------
        assert stats1.alerts_matched == 2  # both waterfall windows flipped true
        alerted_at = conn.execute(select(saves.c.last_alerted_at)).scalar_one()
        assert alerted_at == now1

    # ======= kill switch 2: hazard without a recent confirm is suppressed ==
    with db.begin() as conn:
        conn.execute(text("DELETE FROM verifications"))
    now2 = now1 + dt.timedelta(minutes=5)
    stats2 = sweep(db, now=now2, adapters=[])
    with db.connect() as conn:
        rows = _good_now_rows(conn)
        assert ids["a_swim"] not in rows          # suppressed, not down-ranked
        assert ids["a_falls"] in rows             # standard affordance unaffected
        state, since = _window_state(conn, ids["w_gate"])
        assert state is True and since == now1    # the gate itself is still live
    assert stats2.alerts_matched == 0             # no re-alert without a fresh flip

    # restore the verification for the staleness phase
    with db.begin() as conn:
        conn.execute(insert(verifications).values(
            claim_id=ids["c_swim"], user_id=ids["user"], verdict="confirm",
            conditions_snapshot={F_FLOW: 900}, verified_at=now1))

    # ======= rule 1 + kill switch 1: stale readings -> unknown -> gate kills
    now3 = now1 + dt.timedelta(hours=3)
    stats3 = sweep(db, now=now3, adapters=[])
    with db.connect() as conn:
        # flow (2x15min) and temp (2x1h) and precip (2x1h) are all stale now
        state, since = _window_state(conn, ids["w_gate"])
        assert state is None and since == now3    # flipped true -> unknown
        assert _window_state(conn, ids["w_rain"]).state is None
        assert _window_state(conn, ids["w_season"]).state is True
        assert stats3.windows_unknown == 2

        rows = _good_now_rows(conn)
        # hazard degrades DOWN only: unknown gate suppresses it entirely
        assert ids["a_swim"] not in rows
        # the standard card degrades to its seasonal prior (rule 2), not to silence
        falls_conf3 = scoring.effective_confidence(
            0.38 + scoring.corroboration_boost(1), "seasonal_bio",
            now1 - dt.timedelta(days=30), now3)
        expected_falls3 = scoring.now_score(0.7, [1.3], falls_conf3)
        assert float(rows[ids["a_falls"]].now_score) == pytest.approx(expected_falls3, rel=1e-9)
        assert {r["window_id"] for r in rows[ids["a_falls"]].reasons} == {str(ids["w_season2"])}

        # unknown evaluations update state but append no history row
        gate_history = conn.execute(
            select(condition_states.c.id)
            .where(condition_states.c.window_id == ids["w_gate"])
        ).all()
        assert len(gate_history) == 2  # sweeps 1 and 2 only
    assert stats3.alerts_matched == 0


def test_confidence_bar_and_corroboration_boost(db):
    """Docs/01 §5 worked math: one llm extraction sits at sigma(-0.62)=0.35 and
    never serves; an independent second domain boosts both claims +0.5 nats to
    sigma(-0.12)=0.47, clearing the 0.45 serving bar (docs/01 §4 gate 2)."""
    now = dt.datetime.now(dt.UTC)
    pid, aid, c1, c2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with db.begin() as conn:
        ensure_feed_readings_partitions(conn, now)
        conn.execute(
            text(
                "INSERT INTO places (id, name, kind, geom) VALUES "
                "(:id, 'Hidden Falls (synthetic)', 'waterfall', "
                "ST_SetSRID(ST_MakePoint(-122.0, 45.5), 4326))"
            ),
            {"id": pid},
        )
        conn.execute(insert(activities).values(
            id="waterfall_view", display_name="Waterfall view", hazard_class=False))
        conn.execute(insert(affordances).values(
            id=aid, place_id=pid, activity_id="waterfall_view",
            base_quality=0.7, status="draft"))
        for cid, domain in ((c1, "reddit.com"), (c2, "oregonhikers.org")):
            conn.execute(insert(claims).values(
                id=cid, affordance_id=aid, cclass="geomorphic",
                stype="llm_extracted", source_domain=domain,
                status="published", log_odds=-0.62, last_evidence_at=now))
        conn.execute(affordances.update().where(affordances.c.id == aid)
                     .values(status="published"))
        # suppress the corroborator: a lone extraction must not serve
        conn.execute(claims.update().where(claims.c.id == c2)
                     .values(status="suppressed"))

    sweep(db, now=now, adapters=[])
    with db.connect() as conn:
        assert aid not in _good_now_rows(conn)  # sigma(-0.62)=0.35 < 0.45

    with db.begin() as conn:
        conn.execute(claims.update().where(claims.c.id == c2)
                     .values(status="published"))
    now2 = now + dt.timedelta(minutes=1)
    sweep(db, now=now2, adapters=[])
    with db.connect() as conn:
        row = _good_now_rows(conn)[aid]
        conf = scoring.effective_confidence(
            -0.62 + scoring.corroboration_boost(1), "geomorphic", now, now2)
        assert conf == pytest.approx(0.47, abs=0.005)  # the docs' worked number
        assert float(row.now_score) == pytest.approx(
            scoring.now_score(0.7, [], conf), rel=1e-9)


def test_three_consecutive_failures_fire_the_alert_once(db):
    now = dt.datetime.now(dt.UTC)
    fired: list[str] = []
    with db.begin() as conn:
        conn.execute(insert(feeds).values(
            id=F_BROKEN, provider="usgs_nwis", parameter="00060", unit="cfs"))
        for i in range(1, 5):  # four straight failures
            health.record(conn, F_BROKEN, ok=False, error="boom",
                          checked_at=now + dt.timedelta(minutes=i))
            health.check_and_alert(conn, F_BROKEN, on_alert=lambda f, m: fired.append(f))
        assert fired == [F_BROKEN]  # exactly at the third failure, once per outage

        # recovery resets the run
        health.record(conn, F_BROKEN, ok=True, checked_at=now + dt.timedelta(minutes=10))
        assert health.consecutive_failures(conn, F_BROKEN) == 0


def test_partition_helper_is_idempotent(db):
    now = dt.datetime.now(dt.UTC)
    with db.begin() as conn:
        ensure_feed_readings_partitions(conn, now)
    with db.begin() as conn:
        ensure_feed_readings_partitions(conn, now)  # second run: no error
        suffix = f"y{now.year}m{now.month:02d}"
        exists = conn.execute(
            text("SELECT to_regclass(:t)"), {"t": f"feed_readings_{suffix}"}
        ).scalar_one()
        assert exists is not None
