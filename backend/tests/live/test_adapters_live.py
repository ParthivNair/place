"""One real-network sanity test per keyless adapter (marker: live, excluded in CI).

These assert response *shape* and plausibility, not values — feeds move.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from place.evaluator.adapters import noaa_coops, nwac, open_meteo, snotel, usgs_nwis


def _all_tz_aware(readings) -> bool:
    return all(r.observed_at.tzinfo is not None for r in readings)


async def test_usgs_nwis_live() -> None:
    readings = await usgs_nwis.fetch(["14210000", "14137000"])
    ids = {r.feed_id for r in readings}
    assert "usgs_nwis:14210000:00060" in ids
    assert "usgs_nwis:14137000:00060" in ids
    assert _all_tz_aware(readings)
    now = datetime.now(tz=UTC)
    for r in readings:
        assert now - timedelta(days=2) < r.observed_at <= now + timedelta(minutes=30)
        if r.parameter == "00060":
            assert 0 < r.value < 200_000  # cfs, sane for these rivers


async def test_open_meteo_live() -> None:
    readings = await open_meteo.fetch(45.45, -121.65)
    by_param: dict[str, list] = {}
    for r in readings:
        by_param.setdefault(r.parameter, []).append(r)
    assert len(by_param["air_temp_f"]) == 1
    assert -40 < by_param["air_temp_f"][0].value < 120
    assert len(by_param["precip_in"]) >= 48  # ~72 observed hours
    assert _all_tz_aware(readings)
    now = datetime.now(tz=UTC)
    assert all(r.observed_at <= now + timedelta(hours=1) for r in readings)


async def test_noaa_coops_live() -> None:
    readings = await noaa_coops.fetch("9437540", hours=24)  # Garibaldi, OR
    params = {r.parameter for r in readings}
    assert params == {"tide_pred_ft_mllw", "tide_hilo_ft_mllw"}
    assert len(readings) > 100  # 6-min series alone is ~240/day
    assert _all_tz_aware(readings)
    assert all(-6 < r.value < 15 for r in readings)  # ft MLLW, Oregon coast range


async def test_snotel_live() -> None:
    readings = await snotel.fetch()  # Mt Hood Test Site 651:OR:SNTL
    params = {r.parameter for r in readings}
    assert "swe_in" in params
    assert _all_tz_aware(readings)
    assert all(r.value >= 0 for r in readings)
    assert all(r.feed_id.startswith("snotel:651:") for r in readings)


async def test_nwac_live() -> None:
    # Off-season this is legitimately empty (live-but-unrated); in season the
    # values are the 1..5 NAC danger scale. Both are correct shapes.
    readings = await nwac.fetch()
    assert isinstance(readings, list)
    for r in readings:
        assert r.feed_id.startswith("nwac:")
        assert r.parameter == "danger_level"
        assert r.value in {1.0, 2.0, 3.0, 4.0, 5.0}  # never 0/-1 (no-rating)
        assert r.observed_at.tzinfo is not None
