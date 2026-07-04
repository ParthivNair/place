"""AirNow current-observations adapter (AQI by reporting area). Key-gated.

API: https://www.airnowapi.org/aq/observation/latLong/current/ — requires
AIRNOW_API_KEY; without it `fetch` raises MissingCredential and the evaluator
skips the feed with a log line (never fakes a value).

The payload is a flat list of per-parameter observations (O3, PM2.5, PM10…)
tagged with a human ``ReportingArea``. We emit ONE reading per reporting area:
the max AQI across parameters — the overall AQI by definition — under
``airnow:<area_slug>:aqi`` (e.g. ``airnow:portland:aqi``).

`observed_at` is reconstructed from DateObserved + HourObserved +
LocalTimeZone; AirNow reports fixed-offset zone abbreviations (PST even in
summer for the west coast), mapped explicitly below.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from place.config import Settings, get_settings
from place.evaluator.adapters._http import get_json, slug
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

BASE_URL = "https://www.airnowapi.org/aq/observation/latLong/current/"
PROVIDER = "airnow"
AQI = "aqi"

# AirNow LocalTimeZone abbreviations -> fixed UTC offsets (hours).
_TZ_OFFSETS = {
    "HST": -10, "AKST": -9, "AKDT": -8, "PST": -8, "PDT": -7,
    "MST": -7, "MDT": -6, "CST": -6, "CDT": -5, "EST": -5, "EDT": -4,
    "AST": -4, "GMT": 0, "UTC": 0,
}  # fmt: skip


async def fetch(
    lat: float,
    lng: float,
    *,
    api_key: str | None = None,
    distance_miles: int = 25,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    if api_key is None:
        api_key = get_settings().require("airnow_api_key")  # raises MissingCredential
    params = {
        "format": "application/json",
        "latitude": f"{lat:.4f}",
        "longitude": f"{lng:.4f}",
        "distance": str(distance_miles),
        "API_KEY": api_key,
    }
    payload = await get_json(BASE_URL, params=params, client=client)
    return parse(payload)


def parse(payload: list[dict]) -> list[Reading]:
    # (area_slug) -> (max AQI, observed_at)
    best: dict[str, tuple[float, datetime]] = {}
    for obs in payload:
        area = obs.get("ReportingArea")
        aqi = obs.get("AQI")
        if not area or aqi is None or int(aqi) < 0:  # AirNow uses -1 for missing
            continue
        tz_abbr = obs.get("LocalTimeZone", "UTC")
        if tz_abbr not in _TZ_OFFSETS:
            raise ValueError(f"unmapped AirNow LocalTimeZone: {tz_abbr!r}")
        observed_at = datetime.strptime(obs["DateObserved"].strip(), "%Y-%m-%d").replace(
            hour=int(obs.get("HourObserved", 0)),
            tzinfo=timezone(timedelta(hours=_TZ_OFFSETS[tz_abbr])),
        )
        key = slug(area)
        current = best.get(key)
        if current is None or int(aqi) > current[0]:
            best[key] = (float(int(aqi)), observed_at)
    return [
        Reading(
            feed_id=make_feed_id(PROVIDER, area_slug, AQI),
            value=value,
            observed_at=observed_at,
            unit="aqi",
        )
        for area_slug, (value, observed_at) in sorted(best.items())
    ]


class AirnowAdapter(FeedAdapter):
    """One reporting area's AQI, e.g. ``airnow:portland:aqi``.

    The feeds row's ``station_ref`` holds the provider-native query point
    ('45.51,-122.66'); the feed id's middle segment is the area slug AirNow's
    own ReportingArea must map to.
    """

    def __init__(self, *args: Any, api_key: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._api_key = api_key
        assert self.station_ref is not None
        lat_s, lng_s = self.station_ref.split(",", 1)
        self.lat, self.lng = float(lat_s), float(lng_s)

    async def fetch(self) -> Sequence[Reading]:
        return await fetch(self.lat, self.lng, api_key=self._api_key)


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:
    # Key-gated: raise MissingCredential eagerly so the sweep can log-and-skip
    # the feed before making any network call.
    api_key = settings.require("airnow_api_key")
    return AirnowAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
        api_key=api_key,
    )
