"""Sun/moon adapter tests — pure local computation, no network, deterministic."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from place.evaluator.adapters import sunmoon

LAT, LNG = 45.45, -121.65  # Mt Hood area
_PACIFIC = ZoneInfo("America/Los_Angeles")


def _by_param(readings):
    return {r.parameter: r for r in readings}


def test_noon_july_is_daylight() -> None:
    at = datetime(2026, 7, 4, 12, 0, tzinfo=_PACIFIC)
    by = _by_param(sunmoon.compute(LAT, LNG, at=at))
    assert by["is_daylight"].feed_id == "astro:45.45,-121.65:is_daylight"
    assert by["is_daylight"].value == 1.0
    assert by["sun_elevation_deg"].value > 45  # high summer sun
    assert 14.0 < by["daylight_hours"].value < 16.5  # ~15.4 h at this latitude in July
    assert 0.0 <= by["moon_phase"].value < 28.0
    # observed_at is exactly the caller-supplied instant (never now())
    assert all(r.observed_at == at.astimezone(UTC) for r in by.values())


def test_midnight_is_dark() -> None:
    at = datetime(2026, 7, 4, 0, 30, tzinfo=_PACIFIC)
    by = _by_param(sunmoon.compute(LAT, LNG, at=at))
    assert by["is_daylight"].value == 0.0
    assert by["sun_elevation_deg"].value < 0


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        sunmoon.compute(LAT, LNG, at=datetime(2026, 7, 4, 12, 0))


async def test_fetch_wrapper_matches_compute() -> None:
    at = datetime(2026, 12, 21, 12, 0, tzinfo=_PACIFIC)  # winter solstice sanity
    readings = await sunmoon.fetch(LAT, LNG, at=at)
    by = _by_param(readings)
    assert by["is_daylight"].value == 1.0
    assert 8.0 < by["daylight_hours"].value < 9.5  # ~8.7 h at 45.45N
