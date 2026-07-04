"""SNOTEL/AWDB parser tests against the recorded Mt Hood Test Site response."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import respx

from place.evaluator.adapters import snotel

TRIPLET = snotel.MT_HOOD_TEST_SITE  # 651:OR:SNTL


def test_parse_recorded_response(load_fixture) -> None:
    readings = snotel.parse(load_fixture("snotel_awdb.json"), TRIPLET)
    ids = {r.feed_id for r in readings}
    # ref defaults to the numeric station id (triplets contain colons).
    assert ids == {"snotel:651:swe_in", "snotel:651:snow_depth_in"}
    depth = [r for r in readings if r.feed_id == "snotel:651:snow_depth_in"]
    d0701 = next(r for r in depth if r.observed_at.astimezone(UTC).date().isoformat()
                 == "2026-07-01")
    assert d0701.value == 1.0
    # daily value anchored at station-local (Pacific) start of day
    assert d0701.observed_at == datetime(2026, 7, 1, 0, 0,
                                         tzinfo=ZoneInfo("America/Los_Angeles"))
    assert all(r.unit == "in" for r in readings)


def test_parse_alias_override(load_fixture) -> None:
    readings = snotel.parse(load_fixture("snotel_awdb.json"), TRIPLET, alias="mt_hood")
    assert {r.feed_id for r in readings} == {"snotel:mt_hood:swe_in",
                                             "snotel:mt_hood:snow_depth_in"}


def test_parse_skips_null_values(load_fixture) -> None:
    payload = load_fixture("snotel_awdb.json")
    payload[0]["data"][0]["values"].insert(0, {"date": "2026-06-30", "value": None})
    count_before = len(payload[0]["data"][0]["values"]) - 1
    readings = [r for r in snotel.parse(payload, TRIPLET)
                if r.parameter == snotel.ELEMENTS[
                    payload[0]["data"][0]["stationElement"]["elementCode"]][0]]
    assert len(readings) == count_before


@respx.mock
async def test_fetch_requests_daily_elements(load_fixture) -> None:
    route = respx.get(snotel.BASE_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("snotel_awdb.json"))
    )
    readings = await snotel.fetch()
    assert readings
    params = route.calls.last.request.url.params
    assert params["stationTriplets"] == TRIPLET
    assert params["elements"] == "WTEQ,SNWD"
    assert params["duration"] == "DAILY"
