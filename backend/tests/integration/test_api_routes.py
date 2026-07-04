"""Full-request API tests against the compose postgres (integration marker).

Covers the brief's required happy paths: feed, saves, verdicts, plus auth
gating and the DB-enforced publication gate surfacing through
/admin/review-queue. Data is seeded directly through the sync engine; the
app runs its real lifespan (async engine) via TestClient.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select, text, update

from place.api import security
from place.config import Settings
from place.models import (
    activities,
    affordances,
    claims,
    condition_states,
    condition_windows,
    feeds,
    good_now,
    places,
    trips,
    users,
    verifications,
)

PRECIP_FEED = "nws:45.40,-121.57:precip_in"
LAT, LNG = 45.40, -121.57


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str) -> dict[str, Any]:
    token = security.create_magic_token(email, Settings())
    resp = client.post("/auth/verify", json={"token": token})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def founder_env(monkeypatch):
    monkeypatch.setenv("FOUNDER_EMAIL", "founder@place.test")
    security.get_api_settings.cache_clear()
    yield "founder@place.test"
    security.get_api_settings.cache_clear()


def seed_graph(engine: Engine) -> dict[str, Any]:
    """Place + published affordance + live window/state/feed + good_now row."""
    now = dt.datetime.now(dt.UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(activities).values(
                id="waterfall_view", display_name="Waterfall view", hazard_class=False
            )
        )
        pid = conn.execute(
            insert(places)
            .values(
                name="Tamanawas Falls",
                kind="waterfall",
                geom=f"SRID=4326;POINT({LNG} {LAT})",
            )
            .returning(places.c.id)
        ).scalar()
        aid = conn.execute(
            insert(affordances)
            .values(
                place_id=pid,
                activity_id="waterfall_view",
                difficulty=2,
                dog_ok=True,
                kid_ok=True,
                base_quality=0.7,
                status="draft",
            )
            .returning(affordances.c.id)
        ).scalar()
        cid = conn.execute(
            insert(claims)
            .values(
                affordance_id=aid,
                cclass="seasonal_bio",
                stype="founder_verified",
                source_domain="place.founder",
                observed_date=now.date(),
                log_odds=2.94,
                status="published",
                last_evidence_at=now,
            )
            .returning(claims.c.id)
        ).scalar()
        # founder_verified published support satisfies the structural gate
        conn.execute(
            update(affordances).where(affordances.c.id == aid).values(status="published")
        )
        conn.execute(
            insert(feeds).values(
                id=PRECIP_FEED,
                provider="nws",
                parameter="precip_in",
                unit="in",
                poll_interval=dt.timedelta(hours=1),
                last_value=1.6,
                last_observed_at=now,
            )
        )
        wid = conn.execute(
            insert(condition_windows)
            .values(
                affordance_id=aid,
                wtype="weather_triggered",
                predicate={
                    "feed": PRECIP_FEED,
                    "agg": "sum",
                    "window_h": 72,
                    "op": ">=",
                    "value": 1.0,
                },
                multiplier=1.8,
                is_gate=False,
                state=True,
                state_since=now,
                last_eval=now,
            )
            .returning(condition_windows.c.id)
        ).scalar()
        conn.execute(
            insert(condition_states).values(
                window_id=wid,
                satisfied=True,
                evaluated_at=now,
                inputs={PRECIP_FEED: 1.6},
            )
        )
        conn.execute(
            insert(good_now).values(
                affordance_id=aid,
                now_score=1.9,
                reasons=[{"window_id": str(wid), "wtype": "weather_triggered"}],
                computed_at=now,
            )
        )
    return {"place_id": pid, "affordance_id": aid, "claim_id": cid, "window_id": wid}


# ---------------------------------------------------------------------------
# feed
# ---------------------------------------------------------------------------


def test_feed_happy_path_renders_live_reason_and_logs_impression(client, db) -> None:
    ids = seed_graph(db)
    resp = client.get("/feed", params={"lat": LAT, "lng": LNG})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 1
    # other build agents share this postgres; find our card, don't assume alone
    card = next(c for c in body["cards"] if c["place_name"] == "Tamanawas Falls")
    assert card["now_score"] == pytest.approx(1.9)
    assert card["assumption_of_risk"] is None  # not hazard-class

    reason = card["reasons"][0]
    assert reason["wtype"] == "weather_triggered"
    assert "1.6" in reason["text"] and "72 h" in reason["text"]
    assert reason["source"].startswith("nws")
    assert reason["fresh"] is True

    assert card["conditions"][PRECIP_FEED] == 1.6
    assert card["verdict_controls"][0]["claim_id"] == str(ids["claim_id"])
    assert set(card["verdict_controls"][0]["allowed_verdicts"]) == {
        "confirm",
        "refute",
        "changed",
    }

    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT etype::text AS etype, conditions_snapshot FROM feed_events"
                " WHERE affordance_id = :aid"
            ),
            {"aid": ids["affordance_id"]},
        ).mappings().one()
    assert row["etype"] == "impression"
    assert row["conditions_snapshot"][PRECIP_FEED] == 1.6


def test_feed_marks_unknown_live_window_as_unavailable(client, db) -> None:
    # docs/04 §4 rule 2: a live window in state=unknown (feed down) must be
    # explicitly marked, not silently absent from reasons
    ids = seed_graph(db)
    with db.begin() as conn:
        conn.execute(
            update(condition_windows)
            .where(condition_windows.c.id == ids["window_id"])
            .values(state=None)
        )
    resp = client.get("/feed", params={"lat": LAT, "lng": LNG})
    card = next(c for c in resp.json()["cards"] if c["place_name"] == "Tamanawas Falls")
    assert card["live_unavailable"] == ["nws precip_in (weather_triggered)"]


def test_feed_respects_radius(client, db) -> None:
    seed_graph(db)
    resp = client.get("/feed", params={"lat": 37.77, "lng": -122.42})  # SF: far away
    assert resp.json()["count"] == 0


def test_place_page_and_search(client, db) -> None:
    ids = seed_graph(db)
    resp = client.get(f"/places/{ids['place_id']}")
    assert resp.status_code == 200
    page = resp.json()
    assert page["name"] == "Tamanawas Falls"
    aff = page["affordances"][0]
    assert aff["windows"][0]["state"] == "true"
    assert aff["windows"][0]["live"]["source"].startswith("nws")
    assert aff["claims"][0]["confidence"] > 0.9  # founder prior, fresh
    assert "quote_internal" not in resp.text

    search = client.get(
        "/places/search",
        params={"lat": LAT, "lng": LNG, "activity": "waterfall_view"},
    )
    assert search.status_code == 200
    assert "Tamanawas Falls" in [row["name"] for row in search.json()]

    claims_resp = client.get(f"/affordances/{ids['affordance_id']}/claims")
    assert claims_resp.status_code == 200
    assert claims_resp.json()[0]["source_type"] == "founder_verified"


# ---------------------------------------------------------------------------
# auth + saves
# ---------------------------------------------------------------------------


def test_auth_gating_and_saves_flow(client, db) -> None:
    ids = seed_graph(db)
    payload = {"affordance_id": str(ids["affordance_id"]), "kind": "want_to"}

    # not logged in yet: gated
    assert client.post("/saves", json=payload).status_code == 401

    login(client, "hiker@place.test")
    assert client.post("/saves", json=payload).status_code == 201
    saved = client.get("/saves").json()
    assert len(saved) == 1
    assert saved[0]["place_name"] == "Tamanawas Falls"
    assert saved[0]["kind"] == "want_to"

    # idempotent re-save, then delete
    assert client.post("/saves", json=payload).status_code == 201
    assert (
        client.delete("/saves", params=payload).status_code == 204
    )
    assert client.get("/saves").json() == []
    assert client.delete("/saves", params=payload).status_code == 404


# ---------------------------------------------------------------------------
# trips + verdicts
# ---------------------------------------------------------------------------


def test_verdict_confirm_auto_snapshots_and_updates_log_odds(client, db) -> None:
    ids = seed_graph(db)
    login(client, "hiker@place.test")

    trip_resp = client.post(
        "/trips",
        json={
            "affordance_id": str(ids["affordance_id"]),
            "planned_date": dt.date.today().isoformat(),
        },
    )
    assert trip_resp.status_code == 201

    resp = client.post(
        "/verdicts", json={"claim_id": str(ids["claim_id"]), "verdict": "confirm"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # unweighted confirm: 2.94 + 1.50
    assert body["log_odds"] == pytest.approx(4.44, abs=0.01)
    # the user never described the weather; the server attached the snapshot
    assert body["conditions_snapshot"][PRECIP_FEED] == 1.6
    assert "date" in body["conditions_snapshot"]

    with db.connect() as conn:
        claim = conn.execute(
            select(claims.c.log_odds, claims.c.last_evidence_at).where(
                claims.c.id == ids["claim_id"]
            )
        ).one()
        verif = conn.execute(
            select(verifications.c.trip_id, verifications.c.conditions_snapshot).where(
                verifications.c.claim_id == ids["claim_id"]
            )
        ).one()
    assert float(claim.log_odds) == pytest.approx(4.44, abs=0.01)
    assert verif.trip_id == uuid.UUID(trip_resp.json()["id"])
    assert verif.conditions_snapshot[PRECIP_FEED] == 1.6


def test_verdict_repeat_within_24h_is_rejected(client, db) -> None:
    # a single account must not be able to loop confirm/refute on one claim
    ids = seed_graph(db)
    login(client, "hiker@place.test")
    first = client.post(
        "/verdicts", json={"claim_id": str(ids["claim_id"]), "verdict": "refute"}
    )
    assert first.status_code == 201, first.text
    again = client.post(
        "/verdicts", json={"claim_id": str(ids["claim_id"]), "verdict": "refute"}
    )
    assert again.status_code == 409
    with db.connect() as conn:
        n = conn.execute(
            select(text("count(*)")).select_from(verifications)
        ).scalar()
    assert n == 1


def test_verdict_on_unpublished_claim_is_rejected(client, db) -> None:
    # pre-seeding a confirm on a still-in-review claim must be impossible
    ids = seed_graph(db)
    with db.begin() as conn:
        review_claim = conn.execute(
            insert(claims)
            .values(
                affordance_id=ids["affordance_id"],
                cclass="access",
                stype="llm_extracted",
                source_domain="reddit.com",
                log_odds=-0.62,
                status="review",
            )
            .returning(claims.c.id)
        ).scalar()
    login(client, "hiker@place.test")
    resp = client.post(
        "/verdicts", json={"claim_id": str(review_claim), "verdict": "confirm"}
    )
    assert resp.status_code == 409
    with db.connect() as conn:
        n = conn.execute(select(text("count(*)")).select_from(verifications)).scalar()
    assert n == 0


def test_verdict_changed_supersedes_claim(client, db) -> None:
    ids = seed_graph(db)
    login(client, "hiker@place.test")
    resp = client.post(
        "/verdicts", json={"claim_id": str(ids["claim_id"]), "verdict": "changed"}
    )
    assert resp.status_code == 201
    new_id = resp.json()["superseding_claim_id"]
    assert new_id is not None
    with db.connect() as conn:
        old = conn.execute(
            select(claims.c.superseded_by).where(claims.c.id == ids["claim_id"])
        ).scalar()
        new = conn.execute(
            select(claims.c.stype, claims.c.status).where(
                claims.c.id == uuid.UUID(new_id)
            )
        ).one()
    assert old == uuid.UUID(new_id)
    assert str(new.stype) == "user_reported"
    assert str(new.status) == "review"


def test_verdict_rejects_foreign_trip(client, db) -> None:
    ids = seed_graph(db)
    with db.begin() as conn:
        other = conn.execute(
            insert(users).values(email="other@place.test").returning(users.c.id)
        ).scalar()
        foreign_trip = conn.execute(
            insert(trips)
            .values(
                user_id=other,
                affordance_id=ids["affordance_id"],
                planned_date=dt.date.today(),
            )
            .returning(trips.c.id)
        ).scalar()
    login(client, "hiker@place.test")
    resp = client.post(
        "/verdicts",
        json={
            "claim_id": str(ids["claim_id"]),
            "verdict": "confirm",
            "trip_id": str(foreign_trip),
        },
    )
    assert resp.status_code == 404  # not yours -> not found, never actionable


# ---------------------------------------------------------------------------
# admin review queue + DB publication gate
# ---------------------------------------------------------------------------


def test_admin_gate_blocks_then_publishes(client, db, founder_env) -> None:
    ids = seed_graph(db)
    now = dt.datetime.now(dt.UTC)
    with db.begin() as conn:
        conn.execute(
            insert(activities).values(
                id="tidepool", display_name="Tidepool", hazard_class=False
            )
        )
        draft_aff = conn.execute(
            insert(affordances)
            .values(
                place_id=ids["place_id"],
                activity_id="tidepool",
                base_quality=0.5,
                status="draft",
            )
            .returning(affordances.c.id)
        ).scalar()
        review_claim = conn.execute(
            insert(claims)
            .values(
                affordance_id=draft_aff,
                cclass="access",
                stype="llm_extracted",
                source_domain="reddit.com",
                quote_internal="internal-evidence-never-served",
                log_odds=-0.62,
                status="review",
                last_evidence_at=now,
            )
            .returning(claims.c.id)
        ).scalar()

    assert client.get("/admin/review-queue").status_code == 401  # anon: gated
    login(client, founder_env)

    queue = client.get("/admin/review-queue")
    assert queue.status_code == 200
    assert str(review_claim) in [item["id"] for item in queue.json()]
    assert "internal-evidence-never-served" not in queue.text

    # one reddit claim: structural gate must block affordance publication
    resp = client.post(
        "/admin/review-queue",
        json={"claim_id": str(review_claim), "action": "approve"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["claim_status"] == "published"
    assert body["affordance_published"] is False
    assert "publication gate" in body["gate_error"]

    with db.connect() as conn:
        status = conn.execute(
            select(affordances.c.status).where(affordances.c.id == draft_aff)
        ).scalar()
    assert str(status) == "draft"  # claim approval survived, gate held

    # add an independent second domain, re-approve: gate now passes
    with db.begin() as conn:
        conn.execute(
            insert(claims).values(
                affordance_id=draft_aff,
                cclass="access",
                stype="llm_extracted",
                source_domain="oregonhikers.org",
                log_odds=-0.62,
                status="published",
                last_evidence_at=now,
            )
        )
    resp2 = client.post(
        "/admin/review-queue",
        json={"claim_id": str(review_claim), "action": "approve"},
    )
    assert resp2.json()["affordance_published"] is True
    with db.connect() as conn:
        status = conn.execute(
            select(affordances.c.status).where(affordances.c.id == draft_aff)
        ).scalar()
    assert str(status) == "published"


def test_admin_requires_founder(client, db, founder_env) -> None:
    login(client, "regular@place.test")
    assert client.get("/admin/review-queue").status_code == 403
