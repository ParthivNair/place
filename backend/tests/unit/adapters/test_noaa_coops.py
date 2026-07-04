"""NOAA CO-OPS parser tests against recorded Garibaldi (9437540) predictions."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from place.evaluator.adapters import noaa_coops
from place.evaluator.adapters.base import AdapterError

STATION = "9437540"  # Garibaldi, OR — nearest predictions station to Cannon Beach


def test_parse_hilo_recorded(load_fixture) -> None:
    readings = noaa_coops.parse(
        load_fixture("coops_predictions_hilo.json"), STATION, noaa_coops.TIDE_HILO
    )
    assert len(readings) == 7
    assert {r.feed_id for r in readings} == {"noaa_coops:9437540:tide_hilo_ft_mllw"}
    low = min(readings, key=lambda r: r.value)
    assert low.value == -0.469
    assert low.observed_at == datetime(2026, 7, 4, 17, 13, tzinfo=UTC)  # 't' is GMT
    assert low.unit == "ft"


def test_parse_six_minute_recorded_with_alias(load_fixture) -> None:
    readings = noaa_coops.parse(
        load_fixture("coops_predictions_6min.json"),
        STATION,
        noaa_coops.TIDE_PRED,
        alias="haystack_rock",
    )
    assert len(readings) == 240
    assert {r.feed_id for r in readings} == {"noaa_coops:haystack_rock:tide_pred_ft_mllw"}
    assert readings[0].value == 6.641
    assert readings[0].observed_at == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)


def test_parse_raises_on_in_band_error() -> None:
    payload = {"error": {"message": "No Predictions data was found."}}
    with pytest.raises(AdapterError, match="No Predictions"):
        noaa_coops.parse(payload, STATION, noaa_coops.TIDE_PRED)


@respx.mock
async def test_fetch_requests_both_products(load_fixture) -> None:
    hilo = respx.get(noaa_coops.BASE_URL, params__contains={"interval": "hilo"}).mock(
        return_value=httpx.Response(200, json=load_fixture("coops_predictions_hilo.json"))
    )
    six = respx.get(noaa_coops.BASE_URL, params__contains={"interval": "6"}).mock(
        return_value=httpx.Response(200, json=load_fixture("coops_predictions_6min.json"))
    )
    start = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    readings = await noaa_coops.fetch(STATION, start=start, hours=24)
    assert hilo.called and six.called
    assert len(readings) == 247
    params = six.calls.last.request.url.params
    assert params["station"] == STATION
    assert params["datum"] == "MLLW"
    assert params["time_zone"] == "gmt"
    assert params["begin_date"] == "20260704 00:00"
    assert params["end_date"] == "20260705 00:00"
