"""Condition-state readers.

The feed and verdict routes NEVER evaluate conditions at request time
(docs/01 section 7); they read what the evaluator materialized:
condition_windows (denormalized current state) + the latest
condition_states history row (exact inputs used) + feeds metadata.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import DateTime

from place.api.reasons import iter_leaves, normalize_reading

# Public: the pack compiler (evaluator/publish.py) executes this same
# statement on its sync connection so pack window state and API window state
# can never come from different queries.
WINDOW_STATES_SQL = text(
    """
    SELECT cw.affordance_id, cw.id AS window_id, cw.wtype::text AS wtype,
           cw.is_gate, cw.multiplier, cw.predicate,
           cw.state, cw.state_since, cw.last_eval,
           cs.satisfied, cs.evaluated_at, cs.inputs
    FROM condition_windows cw
    LEFT JOIN LATERAL (
        SELECT satisfied, evaluated_at, inputs
        FROM condition_states
        WHERE window_id = cw.id
          AND (CAST(:at AS timestamptz) IS NULL OR evaluated_at <= :at)
        ORDER BY evaluated_at DESC
        LIMIT 1
    ) cs ON true
    WHERE cw.affordance_id IN :ids
    """
).bindparams(
    bindparam("ids", expanding=True),
    bindparam("at", type_=DateTime(timezone=True)),
)

_FEEDS_META_SQL = text(
    """
    SELECT id, provider, station_ref, parameter, unit,
           EXTRACT(epoch FROM poll_interval) AS poll_interval_s
    FROM feeds
    WHERE id IN :ids
    """
).bindparams(bindparam("ids", expanding=True))


async def window_states(
    db: AsyncConnection,
    affordance_ids: list[uuid.UUID],
    at: dt.datetime | None = None,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Windows + their latest evaluation (optionally as of `at`), per affordance."""
    if not affordance_ids:
        return {}
    rows = (
        await db.execute(WINDOW_STATES_SQL, {"ids": list(affordance_ids), "at": at})
    ).mappings().all()
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["affordance_id"], []).append(dict(row))
    return out


def collect_feed_ids(window_rows: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in window_rows:
        for leaf in iter_leaves(row.get("predicate") or {}):
            if leaf.get("feed"):
                ids.add(str(leaf["feed"]))
        for key in (row.get("inputs") or {}):
            ids.add(str(key))
    return ids


async def feeds_meta(
    db: AsyncConnection, feed_ids: set[str]
) -> dict[str, dict[str, Any]]:
    if not feed_ids:
        return {}
    rows = (
        await db.execute(_FEEDS_META_SQL, {"ids": sorted(feed_ids)})
    ).mappings().all()
    return {row["id"]: dict(row) for row in rows}


def merge_inputs(window_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge every window's latest inputs into one snapshot keyed by feeds.id.

    Scalar values only (the verifications.conditions_snapshot shape in
    docs/01 section 2); when two windows carry the same feed, the most
    recently evaluated wins.
    """
    ordered = sorted(
        window_rows,
        key=lambda r: r.get("evaluated_at") or dt.datetime.min.replace(tzinfo=dt.UTC),
    )
    snapshot: dict[str, Any] = {}
    for row in ordered:
        for feed_id, raw in (row.get("inputs") or {}).items():
            value, _ = normalize_reading(raw)
            snapshot[str(feed_id)] = value
    return snapshot


async def snapshot_for_affordance(
    db: AsyncConnection,
    affordance_id: uuid.UUID,
    at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Conditions snapshot for one affordance, optionally as of a trip time."""
    states = await window_states(db, [affordance_id], at=at)
    snapshot = merge_inputs(states.get(affordance_id, []))
    snapshot["date"] = (at or dt.datetime.now(dt.UTC)).date().isoformat()
    return snapshot
