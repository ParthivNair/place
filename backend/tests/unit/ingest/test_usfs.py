"""USFS trailheads parser against a recorded real ArcGIS response."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from place.ingest.usfs import parse_features

FIXTURE = Path(__file__).parent / "fixtures" / "usfs_trailheads.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


class TestParseFeatures:
    def test_parses_recorded_fixture(self, payload):
        ths = parse_features(payload)
        assert len(ths) > 5
        assert all(th.site_cn and th.name for th in ths)
        assert all(44.0 < th.lat < 47.0 and -125.0 < th.lng < -120.0 for th in ths)

    def test_possessive_titlecase_fixed(self, payload):
        names = {th.name for th in parse_features(payload)}
        assert "Angel's Rest Trailhead" in names
        assert not any("'S" in n for n in names)

    def test_known_trailhead_coordinates(self, payload):
        cloud_cap = next(th for th in parse_features(payload) if th.name == "Cloud Cap")
        assert cloud_cap.lat == pytest.approx(45.4022, abs=0.001)
        assert cloud_cap.lng == pytest.approx(-121.5719, abs=0.001)

    def test_all_upper_names_titlecased(self):
        payload = {
            "features": [
                {
                    "attributes": {
                        "site_cn": "1", "public_site_name": None,
                        "site_name": "RAMONA FALLS TRAILHEAD",
                        "latitude": 45.38, "longitude": -121.83,
                        "permit_information": None,
                    },
                    "geometry": {"x": -121.83, "y": 45.38},
                }
            ]
        }
        (th,) = parse_features(payload)
        assert th.name == "Ramona Falls Trailhead"

    def test_nameless_features_dropped(self):
        payload = {
            "features": [
                {"attributes": {"site_cn": "2", "public_site_name": "", "site_name": " ",
                                "latitude": 45.0, "longitude": -122.0},
                 "geometry": {}},
            ]
        }
        assert parse_features(payload) == []

    def test_permit_information_captured(self):
        payload = {
            "features": [
                {"attributes": {"site_cn": "3", "public_site_name": "Dog Mountain Trailhead",
                                "latitude": 45.7095, "longitude": -121.708,
                                "permit_information": "Weekend permit required Apr-Jun."},
                 "geometry": {}},
            ]
        }
        (th,) = parse_features(payload)
        assert th.permit_info == "Weekend permit required Apr-Jun."
