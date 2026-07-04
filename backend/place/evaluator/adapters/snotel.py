"""USDA AWDB (SNOTEL) adapter — snow-water equivalent + snow depth.

API: https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data (the AWDB REST
service that replaced the old SOAP interface). Stations are addressed by
triplet, e.g. ``651:OR:SNTL`` = Mt Hood Test Site; elements WTEQ (SWE, inches)
and SNWD (snow depth, inches), DAILY duration.

Feed ids: ``snotel:<ref>:swe_in`` / ``snotel:<ref>:snow_depth_in`` where
``ref`` defaults to the numeric station id ("651" — triplets contain colons
and would break the 3-part feed-id format); bindings may pass an alias like
``mt_hood`` (docs/01 §3d).

AWDB daily values carry a bare local date; SNOTEL convention is the reading at
station-local start of day, so we anchor `observed_at` at 00:00
America/Los_Angeles for these Pacific stations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from place.config import Settings
from place.evaluator.adapters._http import get_json
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

BASE_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
PROVIDER = "snotel"
MT_HOOD_TEST_SITE = "651:OR:SNTL"

_PACIFIC = ZoneInfo("America/Los_Angeles")
# AWDB element code -> (feed parameter, unit)
ELEMENTS: dict[str, tuple[str, str]] = {
    "WTEQ": ("swe_in", "in"),
    "SNWD": ("snow_depth_in", "in"),
}


async def fetch(
    station_triplet: str = MT_HOOD_TEST_SITE,
    *,
    alias: str | None = None,
    days: int = 7,
    end: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    end_date = end or datetime.now(tz=_PACIFIC).date()
    params = {
        "stationTriplets": station_triplet,
        "elements": ",".join(ELEMENTS),
        "duration": "DAILY",
        "beginDate": (end_date - timedelta(days=days)).isoformat(),
        "endDate": end_date.isoformat(),
    }
    payload = await get_json(BASE_URL, params=params, client=client)
    return parse(payload, station_triplet, alias=alias)


def parse(
    payload: list[dict],
    station_triplet: str,
    *,
    alias: str | None = None,
) -> list[Reading]:
    ref = alias or station_triplet.split(":", 1)[0]
    readings: list[Reading] = []
    for station in payload:
        if station.get("stationTriplet") not in (None, station_triplet):
            continue
        for element in station.get("data", []):
            code = element["stationElement"]["elementCode"]
            if code not in ELEMENTS:
                continue
            parameter, unit = ELEMENTS[code]
            feed_id = make_feed_id(PROVIDER, ref, parameter)
            for point in element.get("values", []):
                if point.get("value") is None:
                    continue
                observed = datetime.combine(
                    date.fromisoformat(point["date"][:10]),
                    datetime.min.time(),
                    tzinfo=_PACIFIC,
                ).astimezone(UTC)
                readings.append(
                    Reading(
                        feed_id=feed_id,
                        value=float(point["value"]),
                        observed_at=observed,
                        unit=unit,
                    )
                )
    return readings


class SnotelAdapter(FeedAdapter):
    """One SNOTEL station's snow feeds, e.g. ``snotel:mt_hood:swe_in``.

    The feeds row's ``station_ref`` holds the AWDB station triplet
    (``651:OR:SNTL``); the feed id's middle segment is the alias readings are
    emitted under. One fetch returns both SWE and depth (sibling feed ids).
    """

    async def fetch(self) -> Sequence[Reading]:
        assert self.station_ref is not None
        alias = self.feed_id.split(":")[1]
        return await fetch(self.station_ref, alias=alias)


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    return SnotelAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref") or MT_HOOD_TEST_SITE,
        cadence=feed_row.get("poll_interval"),
    )
