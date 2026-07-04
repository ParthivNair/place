"""Every adapter module exposes build(feed_row, settings) -> FeedAdapter (base.py contract)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from place.config import MissingCredential, Settings
from place.evaluator.adapters import (
    airnow,
    base,
    noaa_coops,
    nwac,
    open_meteo,
    snotel,
    sunmoon,
    usgs_nwis,
)

_ROWS = {
    usgs_nwis: {"id": "usgs_nwis:14210000:00060", "provider": "usgs_nwis",
                "station_ref": "14210000", "parameter": "00060", "unit": "ft3/s"},
    open_meteo: {"id": "open_meteo:45.45,-121.65:air_temp_f", "provider": "open_meteo",
                 "station_ref": "45.45,-121.65", "parameter": "air_temp_f", "unit": "degF"},
    noaa_coops: {"id": "noaa_coops:haystack_rock:tide_pred_ft_mllw", "provider": "noaa_coops",
                 "station_ref": "9437540", "parameter": "tide_pred_ft_mllw", "unit": "ft"},
    snotel: {"id": "snotel:mt_hood:swe_in", "provider": "snotel",
             "station_ref": "651:OR:SNTL", "parameter": "swe_in", "unit": "in"},
    nwac: {"id": "nwac:mt_hood:danger_level", "provider": "nwac",
           "station_ref": "mt_hood", "parameter": "danger_level",
           "unit": "nac_danger_scale"},
    sunmoon: {"id": "astro:45.45,-121.65:is_daylight", "provider": "astro",
              "station_ref": "45.45,-121.65", "parameter": "is_daylight", "unit": "bool"},
}


def _settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def _build(module, row, settings):
    row = {**row, "poll_interval": timedelta(hours=1)}
    try:
        return module.build(row, settings)
    except ImportError:  # pragma: no cover — registry (dsl-evaluator) not landed yet
        pytest.skip("place.evaluator.registry not available yet")


@pytest.mark.parametrize("module", list(_ROWS), ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_build_returns_feed_adapter(module) -> None:
    adapter = _build(module, _ROWS[module], _settings())
    assert isinstance(adapter, base.FeedAdapter)
    assert adapter.feed_id == _ROWS[module]["id"]
    assert adapter.cadence == timedelta(hours=1)
    row = adapter.feed_row()
    assert row["id"] == _ROWS[module]["id"]
    assert row["unit"] == _ROWS[module]["unit"]


def test_airnow_build_is_key_gated() -> None:
    row = {"id": "airnow:portland:aqi", "provider": "airnow", "station_ref": "45.51,-122.66",
           "parameter": "aqi", "unit": "aqi", "poll_interval": timedelta(hours=1)}
    with pytest.raises(MissingCredential, match="AIRNOW_API_KEY"):
        airnow.build(row, _settings())
    try:
        adapter = airnow.build(row, _settings(airnow_api_key="test-key"))
    except ImportError:  # pragma: no cover
        pytest.skip("place.evaluator.registry not available yet")
    assert isinstance(adapter, base.FeedAdapter)
    assert (adapter.lat, adapter.lng) == (45.51, -122.66)
