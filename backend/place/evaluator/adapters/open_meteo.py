"""Open-Meteo point-forecast adapter, with api.weather.gov gridpoint fallback.

Primary: https://api.open-meteo.com/v1/forecast — current 2 m air temperature
(°F) plus hourly observed precipitation (inches) for the trailing window
(default 72 h, the waterfall-binding accumulation window; the DSL's
``agg: sum / window_h`` recomputes the sum from the stored hourly readings).
Forecast hours are excluded: only hourly points at or before the payload's
`current.time` are emitted, so `observed_at` is never in the future.

Fallback: api.weather.gov /points/{lat},{lng} -> forecastHourly. It provides
the current-hour temperature forecast only — NWS gridpoints carry no observed
precipitation series — and emits under the SAME feed ids as Open-Meteo, since
the feed id names the conceptual point metric, not the transport. Callers who
need the docs' ``nws:`` prefix (docs/01 §3 examples b/d) can pass
``provider="nws"``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from place.config import Settings
from place.evaluator.adapters._http import get_json, point_ref
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NWS_POINTS_URL = "https://api.weather.gov/points/{lat:.4f},{lng:.4f}"
PROVIDER = "open_meteo"

AIR_TEMP_F = "air_temp_f"
PRECIP_IN = "precip_in"


async def fetch(
    lat: float,
    lng: float,
    *,
    past_hours: int = 72,
    provider: str = PROVIDER,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """Current air temp (°F) + trailing `past_hours` of observed hourly precip (in)."""
    past_days = max(1, -(-past_hours // 24))  # ceil
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lng:.4f}",
        "current": "temperature_2m,precipitation",
        "hourly": "precipitation",
        "past_days": str(past_days),
        "forecast_days": "1",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "timeformat": "unixtime",
        "timezone": "UTC",
    }
    payload = await get_json(FORECAST_URL, params=params, client=client)
    return parse(payload, lat, lng, past_hours=past_hours, provider=provider)


def parse(
    payload: dict,
    lat: float,
    lng: float,
    *,
    past_hours: int = 72,
    provider: str = PROVIDER,
) -> list[Reading]:
    ref = point_ref(lat, lng)
    current = payload["current"]
    now_ts = int(current["time"])
    readings = [
        Reading(
            feed_id=make_feed_id(provider, ref, AIR_TEMP_F),
            value=float(current["temperature_2m"]),
            observed_at=datetime.fromtimestamp(now_ts, tz=UTC),
            unit="degF",
        )
    ]
    hourly = payload.get("hourly", {})
    cutoff = now_ts - past_hours * 3600
    precip_id = make_feed_id(provider, ref, PRECIP_IN)
    for ts, value in zip(hourly.get("time", []), hourly.get("precipitation", []), strict=True):
        if value is None or ts > now_ts or ts < cutoff:
            continue  # forecast hour or outside the trailing window
        readings.append(
            Reading(
                feed_id=precip_id,
                value=float(value),
                observed_at=datetime.fromtimestamp(int(ts), tz=UTC),
                unit="in",
            )
        )
    return readings


async def fetch_nws_fallback(
    lat: float,
    lng: float,
    *,
    provider: str = PROVIDER,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """api.weather.gov gridpoint fallback: current-hour temperature only."""
    points = await get_json(NWS_POINTS_URL.format(lat=lat, lng=lng), client=client)
    hourly_url = points["properties"]["forecastHourly"]
    forecast = await get_json(hourly_url, params={"units": "us"}, client=client)
    return parse_nws_hourly(forecast, lat, lng, provider=provider)


def parse_nws_hourly(
    payload: dict,
    lat: float,
    lng: float,
    *,
    provider: str = PROVIDER,
) -> list[Reading]:
    periods = payload["properties"]["periods"]
    if not periods:
        return []
    first = periods[0]
    if first.get("temperatureUnit") not in (None, "F"):
        raise ValueError(f"unexpected NWS temperature unit: {first['temperatureUnit']}")
    return [
        Reading(
            feed_id=make_feed_id(provider, point_ref(lat, lng), AIR_TEMP_F),
            value=float(first["temperature"]),
            observed_at=datetime.fromisoformat(first["startTime"]),
            unit="degF",
        )
    ]


async def fetch_with_fallback(
    lat: float,
    lng: float,
    *,
    past_hours: int = 72,
    provider: str = PROVIDER,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """Open-Meteo, degrading to the NWS gridpoint temperature if it fails.

    The fallback loses the precipitation series — windows aggregating
    ``precip_in`` go stale and flip to unknown per docs/04 §4 rule 1, which is
    the intended degradation, not a bug to paper over.
    """
    try:
        return await fetch(lat, lng, past_hours=past_hours, provider=provider, client=client)
    except (httpx.HTTPError, KeyError, ValueError):
        return await fetch_nws_fallback(lat, lng, provider=provider, client=client)


class OpenMeteoAdapter(FeedAdapter):
    """One point feed, e.g. ``open_meteo:45.45,-121.65:air_temp_f``.

    A single fetch returns the sibling readings for the point (temp + hourly
    precip) — the sweep stores whatever comes back, keyed by Reading.feed_id.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        assert self.station_ref is not None
        lat_s, lng_s = self.station_ref.split(",", 1)
        self.lat, self.lng = float(lat_s), float(lng_s)

    async def fetch(self) -> Sequence[Reading]:
        return await fetch_with_fallback(self.lat, self.lng, provider=self.provider)


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    # provider may be 'open_meteo' or 'nws' (docs/01 §3 uses both prefixes for
    # point feeds); readings are emitted under the row's own prefix either way.
    return OpenMeteoAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
    )
