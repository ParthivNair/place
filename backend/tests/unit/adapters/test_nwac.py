"""NWAC (avalanche.org map-layer) parser tests.

`nwac_map_layer.json` is the REAL response recorded 2026-07-03 — off-season,
every zone at danger_level -1 (no rating). The in-season fixture is the same
real shape with Mt Hood rated 2 and West Slopes South 3 (synthetic values,
clearly labeled in the generator), exercising the rated path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import respx
import yaml

from place.evaluator.adapters import nwac

LAUNCH_YAML = (
    Path(__file__).resolve().parents[3] / "data" / "bindings" / "launch.yaml"
)


def test_parse_off_season_emits_nothing(load_fixture) -> None:
    # SAFETY: unrated zones must NOT emit 0 — that would satisfy `danger <= 2`
    # hazard gates. No readings -> windows read unknown -> gates stay closed.
    assert nwac.parse(load_fixture("nwac_map_layer.json")) == []


def test_parse_in_season_rated_zones(load_fixture) -> None:
    readings = nwac.parse(load_fixture("nwac_map_layer_in_season_synthetic.json"))
    by_id = {r.feed_id: r for r in readings}
    assert set(by_id) == {"nwac:mt_hood:danger_level", "nwac:west_slopes_south:danger_level"}
    hood = by_id["nwac:mt_hood:danger_level"]
    assert hood.value == 2.0
    assert hood.observed_at == datetime(2027, 1, 15, 18, 0,
                                        tzinfo=ZoneInfo("America/Los_Angeles"))
    assert hood.observed_at.astimezone(UTC) == datetime(2027, 1, 16, 2, 0, tzinfo=UTC)


def test_parse_zone_filter(load_fixture) -> None:
    readings = nwac.parse(load_fixture("nwac_map_layer_in_season_synthetic.json"),
                          zones=["mt_hood"])
    assert [r.feed_id for r in readings] == ["nwac:mt_hood:danger_level"]


def test_launch_yaml_nwac_feed_id_round_trips_through_parse(load_fixture) -> None:
    """The binding's station_ref is the adapter's zone filter AND the feed id's
    middle segment: a hyphen/underscore mismatch here means fetch() silently
    returns [] forever (regression test for the mt-hood vs mt_hood bug)."""
    spec = yaml.safe_load(LAUNCH_YAML.read_text())
    nwac_feeds = [f for f in spec["feeds"] if f["provider"] == "nwac"]
    assert nwac_feeds, "launch.yaml declares no nwac feed"
    payload = load_fixture("nwac_map_layer_in_season_synthetic.json")
    for feed in nwac_feeds:
        readings = nwac.parse(payload, zones=[feed["station_ref"]])
        assert readings, f"station_ref {feed['station_ref']!r} matched no zone"
        assert [r.feed_id for r in readings] == [feed["id"]]


@respx.mock
async def test_fetch_hits_avalanche_org(load_fixture) -> None:
    route = respx.get("https://api.avalanche.org/v2/public/products/map-layer/NWAC").mock(
        return_value=httpx.Response(200, json=load_fixture("nwac_map_layer.json"))
    )
    readings = await nwac.fetch(zones=["mt_hood"])
    assert route.called
    assert readings == []  # off-season recorded response: live but unrated
