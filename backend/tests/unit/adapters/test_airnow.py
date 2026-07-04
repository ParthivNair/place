"""AirNow adapter tests.

No AIRNOW_API_KEY exists in this environment, so the fixture follows the
DOCUMENTED response shape (docs.airnowapi.org, observation/latLong/current)
rather than a recorded live payload — noted per the build brief.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from place.config import MissingCredential, get_settings
from place.evaluator.adapters import airnow


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_fetch_without_key_raises_missing_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIRNOW_API_KEY", "")  # overrides any repo .env value
    with pytest.raises(MissingCredential, match="AIRNOW_API_KEY"):
        await airnow.fetch(45.51, -122.66)


def test_parse_documented_shape(load_fixture) -> None:
    readings = airnow.parse(load_fixture("airnow_current_documented_shape.json"))
    # Portland: max(O3 38, PM2.5 54) -> one overall reading; Salem's AQI=-1 skipped.
    assert len(readings) == 1
    (portland,) = readings
    assert portland.feed_id == "airnow:portland:aqi"
    assert portland.value == 54.0
    assert portland.observed_at == datetime(2026, 7, 3, 15, 0,
                                            tzinfo=timezone(timedelta(hours=-8)))


def test_parse_unmapped_timezone_raises() -> None:
    obs = [{"DateObserved": "2026-07-03 ", "HourObserved": 1, "LocalTimeZone": "XYZ",
            "ReportingArea": "Portland", "AQI": 10}]
    with pytest.raises(ValueError, match="XYZ"):
        airnow.parse(obs)


@respx.mock
async def test_fetch_passes_key_and_point(
    monkeypatch: pytest.MonkeyPatch, load_fixture
) -> None:
    monkeypatch.setenv("AIRNOW_API_KEY", "test-key")
    route = respx.get(airnow.BASE_URL).mock(
        return_value=httpx.Response(
            200, json=load_fixture("airnow_current_documented_shape.json")
        )
    )
    readings = await airnow.fetch(45.51, -122.66)
    assert [r.feed_id for r in readings] == ["airnow:portland:aqi"]
    params = route.calls.last.request.url.params
    assert params["API_KEY"] == "test-key"
    assert params["latitude"] == "45.5100"
    assert params["distance"] == "25"
