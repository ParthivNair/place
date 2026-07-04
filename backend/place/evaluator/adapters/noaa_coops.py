"""NOAA CO-OPS tide-predictions adapter.

API: https://api.tidesandcurrents.noaa.gov/api/prod/datagetter, product
``predictions``, datum MLLW, English units, GMT timestamps. Two products per
station and sweep (predictions are stable — 6 h cadence per docs/04 §4):

- 6-minute series -> ``noaa_coops:<ref>:tide_pred_ft_mllw`` (the continuous
  curve DSL leaves like ``<= 0.0`` evaluate against; docs/01 §3c)
- high/low extremes -> ``noaa_coops:<ref>:tide_hilo_ft_mllw`` (kept as a
  separate parameter so ``agg: latest`` on the continuous series never grabs
  an extreme from hours away)

``ref`` defaults to the station id; bindings may pass a human alias (e.g.
``haystack_rock`` -> station 9437540 Garibaldi, the nearest predictions
station to Cannon Beach — ~15 mi north, so timing/height carry a real offset
the binding must caveat).

CO-OPS reports errors as HTTP 200 with an ``error`` body — parsed and raised.
`observed_at` is the *predicted-for* instant, so future readings are expected
and correct here (forecastable windows, docs/01 §6 example 3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from place.config import Settings
from place.evaluator.adapters._http import get_json
from place.evaluator.adapters.base import AdapterError, FeedAdapter, Reading, make_feed_id

BASE_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
PROVIDER = "noaa_coops"

TIDE_PRED = "tide_pred_ft_mllw"  # 6-minute product
TIDE_HILO = "tide_hilo_ft_mllw"  # hilo product

_PRODUCT_PARAM = {TIDE_PRED: "6", TIDE_HILO: "hilo"}


async def fetch(
    station: str,
    *,
    alias: str | None = None,
    start: datetime | None = None,
    hours: int = 48,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """Fetch hilo + 6-minute tide predictions for `station` over [start, start+hours]."""
    begin = (start or datetime.now(tz=UTC)).astimezone(UTC)
    end = begin + timedelta(hours=hours)
    readings: list[Reading] = []
    for parameter, interval in _PRODUCT_PARAM.items():
        params = {
            "product": "predictions",
            "application": "place-backend",
            "datum": "MLLW",
            "units": "english",
            "time_zone": "gmt",
            "format": "json",
            "interval": interval,
            "station": station,
            "begin_date": begin.strftime("%Y%m%d %H:%M"),
            "end_date": end.strftime("%Y%m%d %H:%M"),
        }
        payload = await get_json(BASE_URL, params=params, client=client)
        readings.extend(parse(payload, station, parameter, alias=alias))
    return readings


def parse(
    payload: dict,
    station: str,
    parameter: str,
    *,
    alias: str | None = None,
) -> list[Reading]:
    if "error" in payload:  # CO-OPS signals errors in-band with HTTP 200
        raise AdapterError(f"CO-OPS station {station}: {payload['error'].get('message')}")
    feed_id = make_feed_id(PROVIDER, alias or station, parameter)
    return [
        Reading(
            feed_id=feed_id,
            value=float(p["v"]),
            # time_zone=gmt was requested; 't' is naive GMT like '2026-07-04 17:13'
            observed_at=datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC),
            unit="ft",
        )
        for p in payload.get("predictions", [])
    ]


class NoaaCoopsAdapter(FeedAdapter):
    """One station's tide predictions, e.g. ``noaa_coops:haystack_rock:tide_pred_ft_mllw``.

    The feeds row's ``station_ref`` holds the real CO-OPS station id (resolved
    once at binding time, docs/01 §3c); the feed id's middle segment may be a
    human alias — readings are emitted under the alias so predicates match.
    """

    async def fetch(self) -> Sequence[Reading]:
        assert self.station_ref is not None
        alias = self.feed_id.split(":")[1]
        return await fetch(self.station_ref, alias=alias)


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    return NoaaCoopsAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
    )
