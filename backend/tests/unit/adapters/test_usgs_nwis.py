"""USGS NWIS parser tests against the recorded live response (2026-07-03)."""

from __future__ import annotations

from datetime import datetime

import httpx
import respx

from place.evaluator.adapters import usgs_nwis


def test_parse_recorded_response(load_fixture) -> None:
    readings = usgs_nwis.parse(load_fixture("usgs_nwis_iv.json"))
    by_id = {r.feed_id: r for r in readings}
    # 14137000 (Sandy @ Bull Run) carries no 00010 series — 3 series, not 4.
    assert set(by_id) == {
        "usgs_nwis:14210000:00060",
        "usgs_nwis:14210000:00010",
        "usgs_nwis:14137000:00060",
    }
    discharge = by_id["usgs_nwis:14210000:00060"]
    assert discharge.value == 869.0
    assert discharge.unit == "ft3/s"
    assert discharge.observed_at == datetime.fromisoformat("2026-07-03T22:45:00.000-07:00")
    assert discharge.observed_at.tzinfo is not None
    assert discharge.provider == "usgs_nwis"
    assert discharge.station_ref == "14210000"
    assert discharge.parameter == "00060"
    assert by_id["usgs_nwis:14210000:00010"].unit == "deg C"


def test_parse_skips_no_data_sentinel_and_blank(load_fixture) -> None:
    payload = load_fixture("usgs_nwis_iv.json")
    series = payload["value"]["timeSeries"][0]
    series["values"][0]["value"] = [
        {"value": "-999999", "dateTime": "2026-07-03T20:00:00.000-07:00"},
        {"value": "", "dateTime": "2026-07-03T20:15:00.000-07:00"},
        {"value": "480", "dateTime": "2026-07-03T20:30:00.000-07:00"},
    ]
    payload["value"]["timeSeries"] = [series]
    readings = usgs_nwis.parse(payload)
    assert [r.value for r in readings] == [480.0]


@respx.mock
async def test_fetch_builds_site_list_request(load_fixture) -> None:
    route = respx.get(usgs_nwis.BASE_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("usgs_nwis_iv.json"))
    )
    readings = await usgs_nwis.fetch(["14210000", "14137000"], period="PT2H")
    assert len(readings) == 3
    params = route.calls.last.request.url.params
    assert params["sites"] == "14210000,14137000"
    assert params["parameterCd"] == "00060,00010"
    assert params["period"] == "PT2H"


@respx.mock
async def test_fetch_does_not_retry_4xx(load_fixture) -> None:
    route = respx.get(usgs_nwis.BASE_URL).mock(return_value=httpx.Response(400))
    try:
        await usgs_nwis.fetch(["14210000"])
        raise AssertionError("expected HTTPStatusError")
    except httpx.HTTPStatusError:
        pass
    assert route.call_count == 1  # config errors must not be retried
