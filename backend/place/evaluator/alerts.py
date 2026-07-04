"""Saves are standing queries (docs/01 §7 Q3): after each evaluator sweep,
match condition windows that flipped true since the user was last alerted.

Delivery at this phase is a callable hook defaulting to an INFO log — the
push composition cron (PR-9) is out of scope; the matched rows and the
saves.last_alerted_at bookkeeping are the contract it will build on.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Connection, and_, func, select, update

from place.models import affordances, condition_windows, places, saves, users

log = logging.getLogger(__name__)

__all__ = ["StandingQueryAlert", "match_standing_queries", "run_alert_pass"]


@dataclass(frozen=True)
class StandingQueryAlert:
    user_id: uuid.UUID
    email: str
    affordance_id: uuid.UUID
    place_name: str
    window_id: uuid.UUID
    wtype: str
    state_since: dt.datetime


NotifyHook = Callable[[StandingQueryAlert], None]


def _default_notify(alert: StandingQueryAlert) -> None:
    log.info(
        "SAVED-QUERY ALERT for %s: %s %s window flipped true at %s",
        alert.email, alert.place_name, alert.wtype, alert.state_since.isoformat(),
    )


def match_standing_queries(conn: Connection) -> list[StandingQueryAlert]:
    """docs/01 §7 Q3: want_to saves whose windows flipped true since the last alert."""
    stmt = (
        select(
            saves.c.user_id,
            users.c.email,
            saves.c.affordance_id,
            places.c.name,
            condition_windows.c.id,
            condition_windows.c.wtype,
            condition_windows.c.state_since,
        )
        .select_from(
            saves.join(
                condition_windows,
                condition_windows.c.affordance_id == saves.c.affordance_id,
            )
            .join(affordances, affordances.c.id == saves.c.affordance_id)
            .join(places, places.c.id == affordances.c.place_id)
            .join(users, users.c.id == saves.c.user_id)
        )
        .where(
            saves.c.kind == "want_to",
            condition_windows.c.state.is_(True),
            condition_windows.c.state_since
            > func.coalesce(saves.c.last_alerted_at, saves.c.created_at),
            affordances.c.status == "published",
        )
    )
    return [
        StandingQueryAlert(
            user_id=row[0], email=row[1], affordance_id=row[2], place_name=row[3],
            window_id=row[4], wtype=str(row[5]), state_since=row[6],
        )
        for row in conn.execute(stmt).all()
    ]


def run_alert_pass(
    conn: Connection,
    *,
    now: dt.datetime | None = None,
    notify: NotifyHook | None = None,
) -> list[StandingQueryAlert]:
    """Match, notify, and stamp saves.last_alerted_at (idempotent per flip)."""
    now = now or dt.datetime.now(dt.UTC)
    alerts = match_standing_queries(conn)
    hook = notify or _default_notify
    for alert in alerts:
        hook(alert)
    for user_id, affordance_id in {(a.user_id, a.affordance_id) for a in alerts}:
        conn.execute(
            update(saves)
            .where(
                and_(
                    saves.c.user_id == user_id,
                    saves.c.affordance_id == affordance_id,
                    saves.c.kind == "want_to",
                )
            )
            .values(last_alerted_at=now)
        )
    return alerts
