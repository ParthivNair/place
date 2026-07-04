"""Route logic with the stubbed DB: saves ownership, event alias mapping."""

from __future__ import annotations

import uuid

from .conftest import FakeResult

AFF = uuid.uuid4()


def _queue_exists_then_defaults(fake_db) -> None:
    # affordance-exists probe, then insert / snapshot / event-insert defaults
    fake_db.queue(FakeResult(rows=[{"ok": 1}]))


def test_save_is_scoped_to_session_user(auth_client, fake_db, user) -> None:
    _queue_exists_then_defaults(fake_db)
    resp = auth_client.post("/saves", json={"affordance_id": str(AFF), "kind": "want_to"})
    assert resp.status_code == 201
    save_inserts = fake_db.inserts_into("saves")
    assert len(save_inserts) == 1
    assert save_inserts[0]["user_id"] == user["id"]  # ownership from cookie, not body
    # the save logged its conditions snapshot (docs/02 section 5)
    event_inserts = fake_db.inserts_into("feed_events")
    assert len(event_inserts) == 1
    assert event_inserts[0]["etype"] == "save"
    assert "date" in event_inserts[0]["conditions_snapshot"]


def test_save_unknown_affordance_404(auth_client, fake_db) -> None:
    fake_db.queue(FakeResult(rows=[]))
    resp = auth_client.post("/saves", json={"affordance_id": str(AFF), "kind": "loved"})
    assert resp.status_code == 404


def test_delete_save_404_when_absent(auth_client, fake_db) -> None:
    fake_db.queue(FakeResult(rowcount=0))
    resp = auth_client.delete(
        "/saves", params={"affordance_id": str(AFF), "kind": "want_to"}
    )
    assert resp.status_code == 404


def test_delete_save_204_when_deleted(auth_client, fake_db) -> None:
    fake_db.queue(FakeResult(rowcount=1))
    resp = auth_client.delete(
        "/saves", params={"affordance_id": str(AFF), "kind": "want_to"}
    )
    assert resp.status_code == 204


def test_event_alias_went_maps_to_going(auth_client, fake_db, user) -> None:
    fake_db.queue(
        FakeResult(rows=[{"ok": 1}]),  # affordance exists
        FakeResult(rows=[]),  # snapshot window states
        FakeResult(scalar_value=7),  # insert returning id
    )
    resp = auth_client.post(
        "/events", json={"affordance_id": str(AFF), "etype": "went"}
    )
    assert resp.status_code == 201
    assert resp.json()["etype"] == "going"
    inserts = fake_db.inserts_into("feed_events")
    assert inserts[0]["etype"] == "going"
    assert inserts[0]["user_id"] == user["id"]


def test_event_shown_maps_to_impression(auth_client, fake_db) -> None:
    fake_db.queue(
        FakeResult(rows=[{"ok": 1}]),
        FakeResult(rows=[]),
        FakeResult(scalar_value=8),
    )
    resp = auth_client.post(
        "/events",
        json={"affordance_id": str(AFF), "etype": "shown", "now_score": 1.4},
    )
    assert resp.json()["etype"] == "impression"


def test_event_unknown_etype_422(auth_client) -> None:
    resp = auth_client.post(
        "/events", json={"affordance_id": str(AFF), "etype": "vibed"}
    )
    assert resp.status_code == 422


def test_event_client_snapshot_passes_through(auth_client, fake_db) -> None:
    snapshot = {"usgs_nwis:14210000:00060": 410}
    fake_db.queue(FakeResult(rows=[{"ok": 1}]), FakeResult(scalar_value=9))
    resp = auth_client.post(
        "/events",
        json={
            "affordance_id": str(AFF),
            "etype": "verified",
            "conditions_snapshot": snapshot,
        },
    )
    assert resp.status_code == 201
    inserts = fake_db.inserts_into("feed_events")
    assert inserts[0]["conditions_snapshot"] == snapshot
