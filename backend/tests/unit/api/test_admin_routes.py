"""Review-queue actions: approve/reject/edit, DB-gate error surfacing."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import DBAPIError

from place.api import security

from .conftest import FakeResult

CLAIM = uuid.uuid4()
AFF = uuid.uuid4()


@pytest.fixture()
def founder_client(auth_client, user, monkeypatch):
    monkeypatch.setenv("FOUNDER_EMAIL", user["email"])
    security.get_api_settings.cache_clear()
    return auth_client


def _claim_row() -> FakeResult:
    return FakeResult(rows=[{"id": CLAIM, "affordance_id": AFF, "status": "review"}])


def test_approve_publishes_claim_and_affordance(founder_client, fake_db) -> None:
    fake_db.queue(
        _claim_row(),
        FakeResult(rowcount=1),  # claim update
        FakeResult(rowcount=1),  # affordance publish (gate passes)
    )
    resp = founder_client.post(
        "/admin/review-queue", json={"claim_id": str(CLAIM), "action": "approve"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim_status"] == "published"
    assert body["affordance_published"] is True
    assert body["gate_error"] is None


def test_approve_surfaces_db_gate_error_cleanly(founder_client, fake_db) -> None:
    gate_msg = (
        f"publication gate: affordance {AFF} needs >=2 published claims from "
        "independent source_domains or a founder_verified/user_reported claim"
    )
    fake_db.queue(
        _claim_row(),
        FakeResult(rowcount=1),  # claim update succeeds
        DBAPIError("UPDATE affordances", {}, Exception(gate_msg)),
    )
    resp = founder_client.post(
        "/admin/review-queue", json={"claim_id": str(CLAIM), "action": "approve"}
    )
    assert resp.status_code == 200  # claim approval still stands
    body = resp.json()
    assert body["claim_status"] == "published"
    assert body["affordance_published"] is False
    assert "publication gate" in body["gate_error"]


def test_reject_suppresses_claim(founder_client, fake_db) -> None:
    fake_db.queue(_claim_row(), FakeResult(rowcount=1))
    resp = founder_client.post(
        "/admin/review-queue", json={"claim_id": str(CLAIM), "action": "reject"}
    )
    assert resp.json()["claim_status"] == "suppressed"
    assert resp.json()["affordance_published"] is False


def test_edit_requires_fields(founder_client, fake_db) -> None:
    fake_db.queue(_claim_row())
    resp = founder_client.post(
        "/admin/review-queue", json={"claim_id": str(CLAIM), "action": "edit"}
    )
    assert resp.status_code == 422


def test_edit_updates_whitelisted_fields_only(founder_client, fake_db) -> None:
    fake_db.queue(_claim_row(), FakeResult(rowcount=1))
    resp = founder_client.post(
        "/admin/review-queue",
        json={
            "claim_id": str(CLAIM),
            "action": "edit",
            "edits": {"source_domain": "oregonhikers.org", "cclass": "access"},
        },
    )
    assert resp.status_code == 200
    update_stmt = fake_db.calls[-1][0]
    params = update_stmt.compile().params
    assert params["source_domain"] == "oregonhikers.org"
    assert params["cclass"] == "access"
    assert "quote_internal" not in params


def test_unknown_claim_404(founder_client, fake_db) -> None:
    fake_db.queue(FakeResult(rows=[]))
    resp = founder_client.post(
        "/admin/review-queue", json={"claim_id": str(CLAIM), "action": "approve"}
    )
    assert resp.status_code == 404
