"""USGS NWIS instantaneous-values adapter.

API: https://waterservices.usgs.gov/nwis/iv/ (WaterML-JSON). One request covers
a comma-joined site list; parameters default to discharge (00060, cfs) and
water temperature (00010, °C). Feed ids use the raw NWIS parameter code, per
the docs/01 canonical example ``usgs_nwis:14210000:00060``.

Caveats observed against the live service:
- Not every gauge carries every parameter (14137000 Sandy @ Bull Run has no
  00010 series) — absent series simply yield no readings.
- Sentinel `noDataValue` (-999999) points and empty-string values are skipped.
- `dateTime` carries a UTC offset (gauge-local), which we preserve.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import httpx

from place.config import Settings
from place.evaluator.adapters._http import get_json
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"
PROVIDER = "usgs_nwis"

DISCHARGE = "00060"  # cfs
WATER_TEMP = "00010"  # °C
DEFAULT_PARAMETER_CODES: tuple[str, ...] = (DISCHARGE, WATER_TEMP)


async def fetch(
    sites: Sequence[str],
    *,
    parameter_codes: Sequence[str] = DEFAULT_PARAMETER_CODES,
    period: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[Reading]:
    """Fetch instantaneous values for `sites`.

    Without `period` NWIS returns only the most recent point per series; pass
    an ISO-8601 duration (e.g. "PT2H") to backfill recent points.
    """
    params: dict[str, str] = {
        "format": "json",
        "sites": ",".join(sites),
        "parameterCd": ",".join(parameter_codes),
        "siteStatus": "all",
    }
    if period is not None:
        params["period"] = period
    payload = await get_json(BASE_URL, params=params, client=client)
    return parse(payload)


def parse(payload: dict) -> list[Reading]:
    readings: list[Reading] = []
    for series in payload["value"]["timeSeries"]:
        site = series["sourceInfo"]["siteCode"][0]["value"]
        variable = series["variable"]
        param = variable["variableCode"][0]["value"]
        unit = variable.get("unit", {}).get("unitCode")
        no_data = variable.get("noDataValue")
        feed_id = make_feed_id(PROVIDER, site, param)
        for block in series.get("values", []):
            for point in block.get("value", []):
                raw = point.get("value")
                if raw is None or raw == "":
                    continue
                value = float(raw)
                if no_data is not None and value == float(no_data):
                    continue
                readings.append(
                    Reading(
                        feed_id=feed_id,
                        value=value,
                        observed_at=datetime.fromisoformat(point["dateTime"]),
                        unit=unit,
                    )
                )
    return readings


class UsgsNwisAdapter(FeedAdapter):
    """One NWIS site+parameter feed, e.g. ``usgs_nwis:14210000:00060``."""

    async def fetch(self) -> Sequence[Reading]:
        assert self.station_ref is not None
        return await fetch([self.station_ref], parameter_codes=[self.parameter])


def build(feed_row: Mapping[str, Any], settings: Settings) -> FeedAdapter:  # noqa: ARG001
    return UsgsNwisAdapter(
        feed_row["id"],
        unit=feed_row["unit"],
        station_ref=feed_row.get("station_ref"),
        cadence=feed_row.get("poll_interval"),
    )
