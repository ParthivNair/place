"""Open-Meteo (+ NWS fallback) parser tests against recorded responses (2026-07-04)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from place.evaluator.adapters import open_meteo

LAT, LNG = 45.45, -121.65


def test_parse_recorded_response(load_fixture) -> None:
    payload = load_fixture("open_meteo_forecast.json")
    readings = open_meteo.parse(payload, LAT, LNG)

    temps = [r for r in readings if r.feed_id == "open_meteo:45.45,-121.65:air_temp_f"]
    assert len(temps) == 1
    assert temps[0].value == 60.4
    assert temps[0].observed_at == datetime.fromtimestamp(1783221300, tz=UTC)
    assert temps[0].unit == "degF"

    winds = [r for r in readings if r.feed_id == "open_meteo:45.45,-121.65:wind_speed_mph"]
    assert len(winds) == 1
    assert winds[0].value == 7.0
    assert winds[0].observed_at == temps[0].observed_at
    assert winds[0].unit == "mph"

    precip = [r for r in readings if r.feed_id == "open_meteo:45.45,-121.65:precip_in"]
    # 96 hourly points in the payload (3 past days + 1 forecast day); only the
    # 72 observed hours at/before current.time within the window are emitted.
    assert len(precip) == 72
    now_ts = payload["current"]["time"]
    assert all(r.observed_at <= datetime.fromtimestamp(now_ts, tz=UTC) for r in precip)
    assert all(r.value >= 0.0 for r in precip)


def test_parse_respects_provider_prefix(load_fixture) -> None:
    readings = open_meteo.parse(load_fixture("open_meteo_forecast.json"), 45.40, -121.57,
                                provider="nws")
    assert readings[0].feed_id == "nws:45.40,-121.57:air_temp_f"


def test_parse_nws_hourly_fallback(load_fixture) -> None:
    readings = open_meteo.parse_nws_hourly(load_fixture("nws_forecast_hourly.json"), LAT, LNG)
    assert len(readings) == 2
    temp, wind = readings
    assert temp.feed_id == "open_meteo:45.45,-121.65:air_temp_f"
    assert temp.value == 55.0
    assert temp.observed_at == datetime.fromisoformat("2026-07-03T23:00:00-07:00")
    # windSpeed "3 mph" is a clean single value — mapped, no conversion needed.
    assert wind.feed_id == "open_meteo:45.45,-121.65:wind_speed_mph"
    assert wind.value == 3.0
    assert wind.unit == "mph"
    assert wind.observed_at == temp.observed_at


def test_parse_nws_wind_never_guesses_units(load_fixture) -> None:
    # Ranges and unknown units emit no wind reading (wrong units are worse
    # than a stale feed); km/h converts.
    payload = load_fixture("nws_forecast_hourly.json")
    for unclean in ("5 to 10 mph", "3 kt", "", None):
        payload["properties"]["periods"][0]["windSpeed"] = unclean
        readings = open_meteo.parse_nws_hourly(payload, LAT, LNG)
        assert [r.feed_id for r in readings] == ["open_meteo:45.45,-121.65:air_temp_f"]
    payload["properties"]["periods"][0]["windSpeed"] = "16 km/h"
    wind = open_meteo.parse_nws_hourly(payload, LAT, LNG)[1]
    assert wind.unit == "mph"
    assert round(wind.value, 2) == 9.94


@respx.mock
async def test_fetch_with_fallback_degrades_to_nws(load_fixture) -> None:
    # 404 is non-retryable, so the fallback engages without retry sleeps.
    respx.get(open_meteo.FORECAST_URL).mock(return_value=httpx.Response(404))
    respx.get("https://api.weather.gov/points/45.4500,-121.6500").mock(
        return_value=httpx.Response(200, json=load_fixture("nws_points.json"))
    )
    respx.get("https://api.weather.gov/gridpoints/PQR/145,94/forecast/hourly").mock(
        return_value=httpx.Response(200, json=load_fixture("nws_forecast_hourly.json"))
    )
    readings = await open_meteo.fetch_with_fallback(LAT, LNG)
    assert [r.feed_id for r in readings] == [
        "open_meteo:45.45,-121.65:air_temp_f",
        "open_meteo:45.45,-121.65:wind_speed_mph",
    ]


@respx.mock
async def test_fetch_requests_observed_units(load_fixture) -> None:
    route = respx.get(open_meteo.FORECAST_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("open_meteo_forecast.json"))
    )
    await open_meteo.fetch(LAT, LNG)
    params = route.calls.last.request.url.params
    assert params["temperature_unit"] == "fahrenheit"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert "wind_speed_10m" in params["current"].split(",")
    assert params["past_days"] == "3"
    assert params["timeformat"] == "unixtime"
