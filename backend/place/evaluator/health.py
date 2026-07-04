"""feed_health writes and the three-consecutive-failure alert hook
(docs/04 §4 rule 4, §8).

Alert delivery at this phase is a callable hook defaulting to an ERROR log —
email/push composition is key-gated and out of scope; the hook is where the
integration wires it in.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable

from sqlalchemy import Connection, func, insert, select

from place.models import feed_health

log = logging.getLogger(__name__)

__all__ = [
    "ALERT_THRESHOLD",
    "check_and_alert",
    "consecutive_failures",
    "last_ok_checked_at",
    "record",
]

ALERT_THRESHOLD = 3

AlertHook = Callable[[str, str], None]


def _default_alert(feed_id: str, message: str) -> None:
    log.error("FEED ALERT [%s]: %s", feed_id, message)


def record(
    conn: Connection,
    feed_id: str,
    *,
    ok: bool,
    latency_ms: int | None = None,
    reading_observed_at: dt.datetime | None = None,
    error: str | None = None,
    checked_at: dt.datetime | None = None,
) -> None:
    """Append one adapter-run status row to feed_health."""
    values: dict[str, object] = {
        "feed_id": feed_id,
        "ok": ok,
        "latency_ms": latency_ms,
        "reading_observed_at": reading_observed_at,
        "error": error,
    }
    if checked_at is not None:
        values["checked_at"] = checked_at
    conn.execute(insert(feed_health).values(**values))


def consecutive_failures(
    conn: Connection, feed_id: str, *, limit: int = ALERT_THRESHOLD + 1
) -> int:
    """Length of the trailing run of not-ok checks for a feed (0 if last was
    ok), counted over at most the last `limit` rows."""
    rows = conn.execute(
        select(feed_health.c.ok)
        .where(feed_health.c.feed_id == feed_id)
        .order_by(feed_health.c.checked_at.desc(), feed_health.c.id.desc())
        .limit(limit)
    ).scalars().all()
    run = 0
    for ok in rows:
        if ok:
            break
        run += 1
    return run


def check_and_alert(
    conn: Connection,
    feed_id: str,
    *,
    threshold: int = ALERT_THRESHOLD,
    on_alert: AlertHook | None = None,
) -> bool:
    """Fire the alert hook when the trailing failure run reaches `threshold`.

    Fires exactly at the threshold (not on every subsequent failure) so a
    dead feed alerts once per outage, not once per sweep.
    """
    run = consecutive_failures(conn, feed_id, limit=threshold + 1)
    if run == threshold:
        (on_alert or _default_alert)(
            feed_id, f"{run} consecutive fetch failures — feed marked unhealthy"
        )
        return True
    return False


def last_ok_checked_at(conn: Connection) -> dict[str, dt.datetime]:
    """Most recent successful check per feed — drives per-feed fetch due-ness.

    (feeds.last_observed_at is unsuitable: tide *predictions* are future-dated,
    which would make a healthy CO-OPS feed look eternally fresh.)
    """
    rows = conn.execute(
        select(feed_health.c.feed_id, func.max(feed_health.c.checked_at))
        .where(feed_health.c.ok)
        .group_by(feed_health.c.feed_id)
    ).all()
    return {feed_id: checked_at for feed_id, checked_at in rows}
