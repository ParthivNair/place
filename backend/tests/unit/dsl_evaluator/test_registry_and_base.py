"""Feed registry cadences (docs/04 §4 table), the stale-as-unknown rule
(rule 1), adapter loading/skipping, and the FeedAdapter interface."""

from __future__ import annotations

import datetime as dt
import sys
import types

import pytest

from place.config import MissingCredential, Settings
from place.evaluator import registry
from place.evaluator.adapters.base import FeedAdapter, Reading, make_feed_id

NOW = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)


# ---------------------------------------------------------------------------
# cadences
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "minutes"),
    [
        ("usgs_nwis", 15),
        ("nws", 60),
        ("open_meteo", 60),
        ("noaa_coops", 360),
        ("snotel", 360),
        ("nwac", 360),
        ("airnow", 60),
        # astro emits instantaneous local values; it recomputes every sweep so
        # nighttime windows never evaluate against a frozen midday snapshot.
        ("astro", 30),
    ],
)
def test_cadence_table_matches_docs(provider, minutes):
    assert registry.CADENCES[provider] == dt.timedelta(minutes=minutes)
    assert registry.cadence_for(provider) == dt.timedelta(minutes=minutes)


def test_cadence_accepts_feed_ids_and_unknown_providers():
    assert registry.cadence_for("usgs_nwis:14210000:00060") == dt.timedelta(minutes=15)
    assert registry.cadence_for("somethingnew") == registry.DEFAULT_CADENCE
    assert registry.provider_of("nwac:mt_hood:danger_level") == "nwac"


# ---------------------------------------------------------------------------
# rule 1: stale (older than 2x cadence) reads as unknown
# ---------------------------------------------------------------------------


def test_staleness_cutoff_is_twice_cadence():
    assert registry.staleness_cutoff("usgs_nwis") == dt.timedelta(minutes=30)
    assert registry.staleness_cutoff("noaa_coops:x:y") == dt.timedelta(hours=12)
    assert registry.staleness_cutoff("astro") == dt.timedelta(hours=1)


def test_daily_valued_feeds_get_data_cadence_staleness():
    # SNOTEL/NWAC values are daily (anchored at local start of day); 2x the
    # 6 h poll cadence would flip them unknown every afternoon and flap the
    # snow gate. Their staleness bound reflects the data's native cadence.
    assert registry.staleness_cutoff("snotel") == dt.timedelta(hours=36)
    assert registry.staleness_cutoff("nwac:mt_hood:danger_level") == dt.timedelta(hours=36)
    feed = "snotel:mt_hood:swe_in"
    assert registry.is_stale(NOW - dt.timedelta(hours=30), feed, NOW) is False
    assert registry.is_stale(NOW - dt.timedelta(hours=37), feed, NOW) is True


def test_is_stale_boundary():
    feed = "usgs_nwis:14210000:00060"
    assert registry.is_stale(NOW - dt.timedelta(minutes=30), feed, NOW) is False  # exactly 2x: ok
    assert registry.is_stale(NOW - dt.timedelta(minutes=30, seconds=1), feed, NOW) is True
    assert registry.is_stale(NOW - dt.timedelta(minutes=5), feed, NOW) is False


def test_future_dated_predictions_are_never_stale():
    # NOAA CO-OPS tide *predictions* legitimately carry future observed_at
    feed = "noaa_coops:9437540:tide_pred_ft_mllw"
    assert registry.is_stale(NOW + dt.timedelta(days=30), feed, NOW) is False


# ---------------------------------------------------------------------------
# adapter loading: build() factories, skip paths, MissingCredential
# ---------------------------------------------------------------------------


class _FakeAdapter(FeedAdapter):
    async def fetch(self):  # pragma: no cover - never called here
        return []


def _install_fake_module(monkeypatch, name: str, build):
    module = types.ModuleType(f"place.evaluator.adapters.{name}")
    module.build = build
    monkeypatch.setitem(sys.modules, f"place.evaluator.adapters.{name}", module)
    monkeypatch.setitem(registry._ADAPTER_MODULES, "faketest", name)


def test_load_adapters_builds_via_module_factory(monkeypatch):
    def build(feed_row, settings):
        return _FakeAdapter(feed_row["id"], unit="cfs")

    _install_fake_module(monkeypatch, "_faketest_ok", build)
    adapters, skipped = registry.load_adapters(
        [{"id": "faketest:1:x", "provider": "faketest"}], Settings()
    )
    assert skipped == []
    assert len(adapters) == 1
    assert adapters[0].feed_id == "faketest:1:x"


def test_load_adapters_skips_unknown_provider():
    adapters, skipped = registry.load_adapters(
        [{"id": "mystery:1:x", "provider": "mystery"}], Settings()
    )
    assert adapters == []
    assert len(skipped) == 1 and "unknown provider" in skipped[0].reason


def test_load_adapters_skips_missing_credential(monkeypatch):
    def build(feed_row, settings):
        raise MissingCredential("AIRNOW_API_KEY")

    _install_fake_module(monkeypatch, "_faketest_keyed", build)
    adapters, skipped = registry.load_adapters(
        [{"id": "faketest:1:x", "provider": "faketest"}], Settings()
    )
    assert adapters == []
    assert len(skipped) == 1 and "AIRNOW_API_KEY" in skipped[0].reason


def test_load_adapters_skips_module_without_build(monkeypatch):
    module = types.ModuleType("place.evaluator.adapters._faketest_nobuild")
    monkeypatch.setitem(sys.modules, "place.evaluator.adapters._faketest_nobuild", module)
    monkeypatch.setitem(registry._ADAPTER_MODULES, "faketest", "_faketest_nobuild")
    adapters, skipped = registry.load_adapters(
        [{"id": "faketest:1:x", "provider": "faketest"}], Settings()
    )
    assert adapters == []
    assert len(skipped) == 1 and "build" in skipped[0].reason


def test_one_bad_feed_does_not_block_the_rest(monkeypatch):
    def build(feed_row, settings):
        return _FakeAdapter(feed_row["id"], unit="x")

    _install_fake_module(monkeypatch, "_faketest_mixed", build)
    adapters, skipped = registry.load_adapters(
        [
            {"id": "mystery:1:x", "provider": "mystery"},
            {"id": "faketest:2:y", "provider": "faketest"},
        ],
        Settings(),
    )
    assert [a.feed_id for a in adapters] == ["faketest:2:y"]
    assert len(skipped) == 1


# ---------------------------------------------------------------------------
# FeedAdapter / Reading interface
# ---------------------------------------------------------------------------


def test_feed_adapter_identity_and_default_cadence():
    adapter = _FakeAdapter("usgs_nwis:14210000:00060", unit="cfs")
    assert adapter.provider == "usgs_nwis"
    assert adapter.station_ref == "14210000"
    assert adapter.parameter == "00060"
    assert adapter.cadence == dt.timedelta(minutes=15)  # from the registry table
    row = adapter.feed_row()
    assert row["id"] == "usgs_nwis:14210000:00060"
    assert row["poll_interval"] == dt.timedelta(minutes=15)


def test_feed_adapter_explicit_cadence_wins():
    adapter = _FakeAdapter("usgs_nwis:1:x", unit="cfs", cadence=dt.timedelta(hours=2))
    assert adapter.cadence == dt.timedelta(hours=2)


def test_feed_adapter_is_abstract():
    with pytest.raises(TypeError):
        FeedAdapter("usgs_nwis:1:x", unit="cfs")  # type: ignore[abstract]


def test_reading_identity_helpers():
    r = Reading(
        feed_id=make_feed_id("noaa_coops", "9437540", "tide_pred_ft_mllw"),
        value=-1.2,
        observed_at=NOW,
    )
    assert r.provider == "noaa_coops"
    assert r.station_ref == "9437540"
    assert r.parameter == "tide_pred_ft_mllw"
