"""Render good_now reasons into provenance lines (docs/02 sections 2-3).

good_now.reasons stores only [{window_id, wtype}]; card copy is rendered
from the window's predicate leaves plus the exact readings the evaluator
used (condition_states.inputs) — nothing is hand-written. Freshness rule
(docs/04 section 4 rule 1): a reading older than its feed's staleness
cutoff (the registry's 2x-cadence rule, with the same per-provider
overrides the evaluator uses) is never shown as implicitly current; the
card says "as of <t>". The reading's observed_at (stored in inputs by the
evaluator) drives the check; evaluated_at is only the fallback.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from place.evaluator.registry import staleness_cutoff

# Fallback copy when a window has no feed-backed leaves (e.g. seasonal priors).
_WTYPE_FALLBACK = {
    "seasonal": "in season",
    "weather_triggered": "recent weather favorable",
    "hydrological": "flow in range",
    "tidal": "tide window",
    "astronomical": "sky window",
    "snow": "snow conditions in range",
}


def iter_leaves(node: Any) -> list[dict[str, Any]]:
    """Flatten a predicate tree (docs/01 section 3 grammar) into its leaves."""
    if not isinstance(node, dict):
        return []
    if "all" in node or "any" in node:
        out: list[dict[str, Any]] = []
        for child in node.get("all", node.get("any", [])) or []:
            out.extend(iter_leaves(child))
        return out
    if "not" in node:
        return iter_leaves(node["not"])
    return [node]


def _parse_ts(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def normalize_reading(raw: Any) -> tuple[Any, dt.datetime | None]:
    """condition_states.inputs values may be scalars or {value, observed_at} dicts."""
    if isinstance(raw, dict):
        return raw.get("value"), _parse_ts(raw.get("observed_at"))
    return raw, None


def _fmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return f"{value:g}"
    return str(value)


def _leaf_line(leaf: dict[str, Any], value: Any, meta: dict[str, Any]) -> str:
    feed_id = str(leaf.get("feed", ""))
    parameter = str(meta.get("parameter") or feed_id.rsplit(":", 1)[-1]).replace("_", " ")
    unit = meta.get("unit") or ""
    val = _fmt_value(value)
    if leaf.get("agg") in ("sum", "min", "max") and leaf.get("window_h"):
        # e.g. "1.6 in precip over last 72 h" — always prints the leaf's window_h
        return f"{val} {unit} {parameter} over last {leaf['window_h']} h".replace("  ", " ")
    return f"{parameter} {val} {unit}".strip()


def _provenance_label(meta: dict[str, Any], feed_id: str) -> str:
    provider = meta.get("provider")
    if not provider:
        return feed_id
    station = meta.get("station_ref")
    return f"{provider} {station}" if station else str(provider)


def render_reason(
    *,
    window_id: Any,
    wtype: str,
    predicate: dict[str, Any] | None,
    inputs: dict[str, Any] | None,
    feeds_meta: dict[str, dict[str, Any]] | None,
    evaluated_at: dt.datetime | None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Compose one card reason: text + provenance + freshness."""
    now = now or dt.datetime.now(dt.UTC)
    parts: list[str] = []
    labels: list[str] = []
    provenance: list[dict[str, Any]] = []
    fresh = True
    oldest_as_of: dt.datetime | None = None

    for leaf in iter_leaves(predicate or {}):
        feed_id = leaf.get("feed")
        if not feed_id:
            continue
        raw = (inputs or {}).get(feed_id)
        if raw is None:
            continue
        value, observed_at = normalize_reading(raw)
        meta = (feeds_meta or {}).get(feed_id) or {}
        parts.append(_leaf_line(leaf, value, meta))
        labels.append(_provenance_label(meta, str(feed_id)))
        as_of = observed_at or evaluated_at
        if as_of is not None:
            oldest_as_of = as_of if oldest_as_of is None else min(oldest_as_of, as_of)
            if now - as_of > staleness_cutoff(str(feed_id)):
                fresh = False
        provenance.append(
            {
                "feed_id": str(feed_id),
                "provider": meta.get("provider"),
                "station_ref": meta.get("station_ref"),
                "parameter": meta.get("parameter"),
                "unit": meta.get("unit"),
                "value": value,
                "observed_at": observed_at,
            }
        )

    text = " · ".join(parts) if parts else _WTYPE_FALLBACK.get(wtype, "conditions favorable")
    as_of = oldest_as_of or evaluated_at
    if not fresh and as_of is not None:
        text = f"{text} (as of {as_of.isoformat(timespec='minutes')})"
    # De-dup provenance labels, order-preserving.
    source = ", ".join(dict.fromkeys(labels)) or None
    return {
        "window_id": window_id,
        "wtype": wtype,
        "text": text,
        "source": source,
        "fresh": fresh,
        "as_of": as_of,
        "evaluated_at": evaluated_at,
        "provenance": provenance,
    }
