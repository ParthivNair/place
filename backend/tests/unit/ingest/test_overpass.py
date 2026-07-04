"""Overpass parser against a recorded real response (waterfalls, 2026-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from place.ingest.overpass import OsmPlace, build_query, parse_elements

FIXTURE = Path(__file__).parent / "fixtures" / "overpass_waterfalls.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


class TestBuildQuery:
    def test_defaults_cover_all_tag_groups_around_portland(self):
        q = build_query()
        assert "(around:130000,45.512,-122.658)" in q
        assert '"waterway"="waterfall"' in q
        assert '"natural"="waterfall"' in q  # legacy tag still queried
        assert '"natural"="hot_spring"' in q
        assert '"tourism"="viewpoint"' in q
        assert '"leisure"="swimming_area"' in q
        assert '"natural"="peak"' in q
        assert 'relation["route"="hiking"]' in q
        assert q.startswith("[out:json]")
        assert q.rstrip().endswith("out center tags;")

    def test_waterfall_group_pulls_in_legacy_tag(self):
        q = build_query(["waterfall"])
        assert '"waterway"="waterfall"' in q
        assert '"natural"="waterfall"' in q
        assert "viewpoint" not in q

    def test_bbox_replaces_around(self):
        q = build_query(["peak"], bbox=(44.3, -124.3, 46.7, -121.0))
        assert "(44.3,-124.3,46.7,-121.0)" in q
        assert "around:" not in q

    def test_unknown_group_rejected(self):
        with pytest.raises(ValueError, match="unknown overpass tag groups"):
            build_query(["bogus"])

    def test_caller_tag_list_is_not_mutated(self):
        tags = ["waterfall"]
        build_query(tags)
        build_query(tags)  # a second call must not see accumulated appends
        assert tags == ["waterfall"]


class TestParseElements:
    def test_parses_recorded_fixture(self, payload: dict):
        places = parse_elements(payload)
        assert places, "fixture yielded no places"
        assert all(isinstance(p, OsmPlace) for p in places)
        assert all(p.kind == "waterfall" for p in places)
        by_name = {p.name: p for p in places}
        ramona = by_name["Ramona Falls"]
        assert ramona.osm_id == 496619635  # node: raw id
        assert ramona.lat == pytest.approx(45.38, abs=0.01)
        assert ramona.lng == pytest.approx(-121.775, abs=0.1)

    def test_unnamed_elements_skipped(self, payload: dict):
        raw_named = sum(1 for e in payload["elements"] if e.get("tags", {}).get("name"))
        assert len(parse_elements(payload)) == raw_named

    def test_way_ids_offset_encoded(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 42,
                    "center": {"lat": 45.5, "lon": -122.1},
                    "tags": {"waterway": "waterfall", "name": "Way Falls"},
                },
                {
                    "type": "relation",
                    "id": 42,
                    "center": {"lat": 45.5, "lon": -122.2},
                    "tags": {"route": "hiking", "name": "Some Loop Hike"},
                },
            ]
        }
        way, rel = parse_elements(payload)
        assert way.osm_id == 42 + 2_400_000_000
        assert rel.osm_id == 42 + 3_600_000_000
        assert rel.kind == "trail"

    def test_peak_elevation_parsed(self):
        payload = {
            "elements": [
                {
                    "type": "node", "id": 1, "lat": 45.37, "lon": -121.69,
                    "tags": {"natural": "peak", "name": "Mount Hood", "ele": "3428.8"},
                },
                {
                    "type": "node", "id": 2, "lat": 45.4, "lon": -121.7,
                    "tags": {"natural": "peak", "name": "Junk Ele", "ele": "high"},
                },
            ]
        }
        hood, junk = parse_elements(payload)
        assert hood.elev_m == 3429
        assert junk.elev_m is None

    def test_irrelevant_tags_skipped(self):
        payload = {
            "elements": [
                {"type": "node", "id": 3, "lat": 45.5, "lon": -122.6,
                 "tags": {"amenity": "cafe", "name": "Not A Place"}},
            ]
        }
        assert parse_elements(payload) == []
