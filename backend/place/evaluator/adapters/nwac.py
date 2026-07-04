"""NWAC avalanche-danger adapter (via the avalanche.org public API).

NWAC has no first-party JSON API; its forecasts are served by the National
Avalanche Center's public aggregation API, which is the stable public
endpoint the NWAC site itself consumes:

    https://api.avalanche.org/v2/public/products/map-layer/NWAC

The map layer is GeoJSON; each feature is a forecast zone whose properties
carry ``name`` ("Mt Hood"), ``danger_level`` (1 Low … 5 Extreme), and the
forecast validity window (``start_date``/``end_date``, naive Pacific local).

Feed ids: ``nwac:<zone_slug>:danger_level`` (e.g. ``nwac:mt_hood:danger_level``,
matching docs/01 §3d).

SAFETY / off-season semantics: outside the forecast season (roughly
Nov–Apr) zones carry ``danger_level`` -1/0 = "no rating". No reading is
emitted for unrated zones — emitting 0 would satisfy hazard predicates like
``danger_level <= 2``. With no reading the window evaluates to *unknown* and
`is_gate` windows stay closed (docs/04 §4 rule 3: hazard degrades DOWN only).
An empty result with a 200 response therefore means "live but unrated"; the
health layer should record it as `live_unavailable` rather than a failure —
`fetch` distinguishes the two by returning [] vs raising.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from place.config import Settings
from place.evaluator.adapters._http import get_json, slug
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

MAP_LAYER_URL = "https://api.avalanche.org/v2/public/products/map-layer/{center_id}"
PROVIDER = "nwac"
DANGER_LEVEL = "danger_level"
NO_RATING = (-1, 0)

_PACIFIC = ZoneInfo("America/Los_Angeles")


async def fetch(
    zones: Sequence[str] | None = None,
    *,
    center_id: str = "NWAC",
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """Danger level per rated forecast zone; `zones` filters by slug ('mt_hood')."""
    payload = await get_json(MAP_LAYER_URL.format(center_id=center_id), client=client)
    return parse(payload, zones=zones)


def parse(payload: dict, *, zones: Sequence[str] | None = None) -> list[Reading]:
    wanted = {z.lower() for z in zones} if zones else None
    readings: list[Reading] = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name")
        if not name:
            continue
        zone_slug = slug(name)
        if wanted is not None and zone_slug not in wanted:
            continue
        danger = props.get("danger_level")
        if danger is None or int(danger) in NO_RATING:
            continue  # unrated: emit nothing so hazard gates read unknown, never "safe"
        start = props.get("start_date")
        if not start:
            continue  # no validity timestamp -> cannot honor observed_at-from-payload
        readings.append(
            Reading(
                feed_id=make_feed_id(PROVIDER, zone_slug, DANGER_LEVEL),
                value=float(int(danger)),
                observed_at=datetime.fromisoformat(start).replace(tzinfo=_PACIFIC),
                unit="nac_danger_scale",
            )
        )
    return readings


class NwacAdapter(FeedAdapter):
    """One forecast zone's danger feed, e.g. ``nwac:mt_hood:danger_level``.

    An empty result is 'live but unrated' (off-season) — the sweep should
    record it as live_unavailable, not a failure; the zone's windows read
    unknown and hazard gates stay closed.
    """

    async def fetch(self) -> Sequence[Reading]:
        assert self.station_ref is not None
        return await fetch(zones=[self.station_ref])


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    return NwacAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
    )
